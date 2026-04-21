"""
state.py — shared in-memory application state

Holds the current status, latest transcript, last error, and a
timestamp so all modules can read and write a single source of truth
without importing Flask's application context.

Thread safety: all mutations go through the helper functions below,
which acquire a lock so the Flask request thread and the recording
thread never clobber each other.
"""

import threading
from datetime import datetime

_lock = threading.Lock()

# Possible status values
STATUS_IDLE = "Idle"
STATUS_RECORDING = "Recording"
STATUS_PROCESSING = "Processing"
STATUS_ERROR = "Error"

_state = {
    "status": STATUS_IDLE,
    "transcript": "",
    "last_error": "",
    "last_updated": datetime.now().isoformat(),
}


def get() -> dict:
    """Return a shallow copy of the current state."""
    with _lock:
        return dict(_state)


def set_status(status: str) -> None:
    with _lock:
        _state["status"] = status
        _state["last_updated"] = datetime.now().isoformat()


def set_transcript(text: str) -> None:
    with _lock:
        _state["transcript"] = text
        _state["last_updated"] = datetime.now().isoformat()


def set_error(message: str) -> None:
    with _lock:
        _state["last_error"] = message
        _state["status"] = STATUS_ERROR
        _state["last_updated"] = datetime.now().isoformat()


def clear_error() -> None:
    with _lock:
        _state["last_error"] = ""
