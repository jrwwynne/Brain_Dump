"""
recorder.py — audio recording and transcription workflow

Handles:
  1. Starting and stopping arecord via subprocess
  2. Running whisper.cpp to transcribe the recorded audio
  3. Calling ai_formatter to extract tasks from the transcript
  4. Persisting extracted tasks to SQLite via db

All paths and device names are taken from environment variables so they
can be overridden without editing source code.

Environment variables
---------------------
AUDIO_DEVICE        ALSA device string for arecord  (default: plughw:3,0)
WHISPER_BINARY      Path to the whisper-cli binary   (default: /home/james/whisper.cpp/build/bin/whisper-cli)
WHISPER_MODEL       Path to the ggml model file      (default: /home/james/whisper.cpp/models/ggml-base.en.bin)
AUDIO_FILE          Temporary WAV file path          (default: /tmp/brain_dump.wav)
"""

import logging
import os
import subprocess
import tempfile
import threading

import ai_formatter
import db
import state

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUDIO_DEVICE: str = os.getenv("AUDIO_DEVICE", "plughw:3,0")
WHISPER_BINARY: str = os.getenv("WHISPER_BINARY", "/home/james/whisper.cpp/build/bin/whisper-cli")
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "/home/james/whisper.cpp/models/ggml-base.en.bin")
AUDIO_FILE: str = os.getenv("AUDIO_FILE", "/tmp/brain_dump.wav")

# ---------------------------------------------------------------------------
# Internal state — the arecord subprocess handle
# ---------------------------------------------------------------------------

_record_process: subprocess.Popen | None = None
_process_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Recording control
# ---------------------------------------------------------------------------

def start_recording() -> None:
    """
    Launch arecord in the background.
    Raises RuntimeError if a recording is already in progress or if arecord fails to start.
    """
    global _record_process

    with _process_lock:
        if _record_process is not None:
            raise RuntimeError("A recording is already in progress.")

        cmd = [
            "arecord",
            "-D", AUDIO_DEVICE,
            "-f", "S16_LE",   # signed 16-bit little-endian
            "-r", "16000",    # 16 kHz — what whisper.cpp expects
            "-c", "1",        # mono
            AUDIO_FILE,
        ]

        logger.info("[recorder] Starting arecord: %s", " ".join(cmd))

        try:
            _record_process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "arecord not found. Install it with: sudo apt install alsa-utils"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to start arecord: {exc}") from exc

    state.set_status(state.STATUS_RECORDING)
    logger.info("[recorder] Recording started.")


def stop_recording() -> None:
    """
    Stop arecord and kick off the transcription+task-extraction pipeline
    in a background thread so the GPIO callback returns quickly.
    """
    global _record_process

    with _process_lock:
        proc = _record_process
        _record_process = None

    if proc is None:
        logger.warning("[recorder] stop_recording called but no recording was in progress.")
        return

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()

    logger.info("[recorder] Recording stopped.")
    state.set_status(state.STATUS_PROCESSING)

    # Run the slow pipeline (transcription + Ollama + DB) in a background thread
    thread = threading.Thread(target=_process_audio, daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# Audio processing pipeline
# ---------------------------------------------------------------------------

def _process_audio() -> None:
    """Transcribe the recorded file, call Ollama, and store tasks."""
    try:
        transcript = _transcribe()
    except RuntimeError as exc:
        logger.error("[recorder] Transcription failed: %s", exc)
        state.set_error(str(exc))
        return

    state.set_transcript(transcript)
    logger.info("[recorder] Transcript: %s", transcript)

    try:
        tasks = ai_formatter.extract_tasks(transcript)
    except RuntimeError as exc:
        logger.error("[recorder] Task extraction failed: %s", exc)
        state.set_error(str(exc))
        return

    if tasks:
        try:
            for task_text in tasks:
                db.insert_task(task_text, source_transcript=transcript)
            logger.info("[recorder] Inserted %d task(s) into the database.", len(tasks))
        except Exception as exc:
            logger.error("[recorder] Database insert failed: %s", exc)
            state.set_error(f"Database error: {exc}")
            return
    else:
        logger.info("[recorder] No actionable tasks found in transcript.")

    state.set_status(state.STATUS_IDLE)
    state.clear_error()


def _transcribe() -> str:
    """
    Run whisper-cli on the recorded audio file and return the transcript text.
    Raises RuntimeError on any failure.
    """
    if not os.path.isfile(WHISPER_BINARY):
        raise RuntimeError(
            f"whisper-cli binary not found at {WHISPER_BINARY}. "
            "Set WHISPER_BINARY to the correct path."
        )

    if not os.path.isfile(WHISPER_MODEL):
        raise RuntimeError(
            f"Whisper model not found at {WHISPER_MODEL}. "
            "Set WHISPER_MODEL to the correct path."
        )

    if not os.path.isfile(AUDIO_FILE):
        raise RuntimeError(
            f"Audio file not found at {AUDIO_FILE}. Recording may have failed."
        )

    cmd = [
        WHISPER_BINARY,
        "-m", WHISPER_MODEL,
        "-f", AUDIO_FILE,
        "--no-timestamps",
        "-otxt",         # output plain text to stdout
        "--output-file", "/tmp/brain_dump",  # whisper appends .txt automatically
    ]

    logger.info("[recorder] Running whisper: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        raise RuntimeError(f"whisper-cli binary not found at {WHISPER_BINARY}.")
    except subprocess.TimeoutExpired:
        raise RuntimeError("whisper-cli timed out after 120 seconds.")

    if result.returncode != 0:
        raise RuntimeError(
            f"whisper-cli exited with code {result.returncode}. "
            f"stderr: {result.stderr.strip()}"
        )

    # whisper-cli writes a .txt file alongside the audio file; read it back
    txt_path = "/tmp/brain_dump.txt"
    if os.path.isfile(txt_path):
        with open(txt_path, "r") as fh:
            transcript = fh.read().strip()
    else:
        # Fall back to stdout if the file wasn't written
        transcript = result.stdout.strip()

    if not transcript:
        raise RuntimeError("Transcription produced an empty result.")

    return transcript
