"""
gpio_handler.py — physical button handling via gpiozero

The button on GPIO17 toggles recording on/off:
  - First press  → start recording
  - Second press → stop recording

Debounce is handled by gpiozero's bounce_time parameter.
A threading.Lock prevents the button callback and the recorder
from entering a race condition.
"""

import logging
import threading

import state
import recorder

logger = logging.getLogger(__name__)

# GPIO pin number (BCM numbering)
BUTTON_PIN: int = 17

# Minimum seconds between accepted button presses (debounce)
DEBOUNCE_TIME: float = 0.3

_button_lock = threading.Lock()
_is_recording: bool = False


def _on_button_pressed() -> None:
    """
    Called by gpiozero on each (debounced) button press.
    Toggles between start and stop recording.
    """
    global _is_recording

    with _button_lock:
        current_status = state.get()["status"]

        # Ignore button presses while the app is already processing audio
        if current_status == state.STATUS_PROCESSING:
            logger.info("[gpio] Button pressed but ignored — currently processing.")
            return

        if not _is_recording:
            logger.info("[gpio] Button pressed — starting recording.")
            try:
                recorder.start_recording()
                _is_recording = True
            except RuntimeError as exc:
                logger.error("[gpio] Could not start recording: %s", exc)
                state.set_error(str(exc))
        else:
            logger.info("[gpio] Button pressed — stopping recording.")
            _is_recording = False
            recorder.stop_recording()


def setup() -> None:
    """
    Initialise the GPIO button.
    Imports gpiozero here so the module can be imported on non-Pi hardware
    without immediately crashing (useful for testing on a desktop).
    """
    try:
        from gpiozero import Button
        from signal import pause  # noqa: F401 — not used here but kept for reference
    except ImportError:
        logger.warning(
            "[gpio] gpiozero is not installed. GPIO button will not be active."
        )
        return
    except Exception as exc:
        logger.warning("[gpio] Could not import gpiozero: %s", exc)
        return

    try:
        button = Button(BUTTON_PIN, bounce_time=DEBOUNCE_TIME)
        button.when_pressed = _on_button_pressed
        logger.info("[gpio] Button initialised on GPIO%d.", BUTTON_PIN)
    except Exception as exc:
        logger.error("[gpio] Failed to initialise GPIO button: %s", exc)
        state.set_error(f"GPIO initialisation failed: {exc}")
