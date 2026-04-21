"""
ai_formatter.py — sends the transcript to an Ollama server and parses tasks

Environment variables
---------------------
OLLAMA_BASE_URL   Base URL of the Ollama server, e.g. http://192.168.1.100:11434
OLLAMA_MODEL      Model name to use,             e.g. llama3.1:8b

The module calls the Ollama /api/generate endpoint, asks for a strict
JSON response, and parses the returned list of tasks.

If the model returns extra prose around the JSON the code attempts to
extract the first JSON object it finds before giving up.
"""

import json
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration — read from environment with sensible defaults
# ---------------------------------------------------------------------------

OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

# How long to wait for Ollama to respond (seconds)
OLLAMA_TIMEOUT: int = int(os.getenv("OLLAMA_TIMEOUT", "60"))

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a task extraction assistant. "
    "Convert raw speech into a list of clear, actionable tasks. "
    "Rules:\n"
    "- Keep each task concise.\n"
    "- Use imperative phrasing (e.g. 'Buy bolts', 'Email James').\n"
    "- Only include actionable tasks — ignore filler words and non-tasks.\n"
    "- Return ONLY valid JSON in this exact format: "
    '{"tasks": ["Task one", "Task two"]}\n'
    "- If there are no actionable tasks, return: {\"tasks\": []}\n"
    "- Do NOT include any explanation, markdown, or extra text."
)


def _build_prompt(transcript: str) -> str:
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Transcript:\n{transcript}\n\n"
        "JSON response:"
    )


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """
    Try to parse the text as JSON directly.
    If that fails, search for the first {...} block and try again.
    Raises ValueError if nothing parseable is found.
    """
    text = text.strip()

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from Ollama response: {text!r}")


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def extract_tasks(transcript: str) -> list[str]:
    """
    Send the transcript to Ollama and return a list of task strings.

    Returns an empty list if the transcript contains no actionable tasks.
    Raises RuntimeError on connection failure, timeout, or unparseable response.
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": _build_prompt(transcript),
        "stream": False,
        "format": "json",  # ask Ollama to constrain output to JSON
    }

    logger.info("[ai_formatter] Sending transcript to Ollama at %s (model: %s)", url, OLLAMA_MODEL)

    try:
        response = requests.post(url, json=payload, timeout=OLLAMA_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(
            f"Could not connect to Ollama at {OLLAMA_BASE_URL}. "
            "Check that the server is running and OLLAMA_BASE_URL is correct."
        ) from exc
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Ollama did not respond within {OLLAMA_TIMEOUT} seconds. "
            "Try increasing OLLAMA_TIMEOUT or using a smaller model."
        )
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"Ollama returned an HTTP error: {exc}") from exc

    # Ollama's /api/generate response has a 'response' field containing the model output
    try:
        body = response.json()
        raw_text = body.get("response", "")
    except Exception as exc:
        raise RuntimeError(f"Could not decode Ollama API response body: {exc}") from exc

    logger.debug("[ai_formatter] Raw Ollama response: %s", raw_text)

    try:
        parsed = _extract_json(raw_text)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    tasks = parsed.get("tasks", [])

    if not isinstance(tasks, list):
        raise RuntimeError(
            f"Expected 'tasks' to be a list, got {type(tasks).__name__}: {tasks!r}"
        )

    # Filter out any non-string items and strip whitespace
    cleaned = [str(t).strip() for t in tasks if str(t).strip()]
    logger.info("[ai_formatter] Extracted %d task(s)", len(cleaned))
    return cleaned
