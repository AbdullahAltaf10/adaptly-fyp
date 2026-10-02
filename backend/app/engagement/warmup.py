"""
Load the engagement models in the background when the server starts.

Importing TensorFlow takes 13+ seconds, so `ml/inference/model.py` does it on
first use rather than at import - which is right for start-up time (0.6 s) and
wrong for the first learner, whose first reading would wait for it. The study
screen even tells them so ("Analysing your first reading...") and says the
backend has usually finished loading before anybody gets there. Nothing did
that loading, so that sentence was not true.

This makes it true without giving back the fast start: the load runs on a
daemon thread, so the server accepts connections immediately and the models
arrive a few seconds later. A request that comes in before then simply waits
on the same lock the warm-up holds (see `load_model`), it does not load them a
second time.

Never raises. A failed warm-up costs the first learner the wait they would
have had anyway, and the real error surfaces on their first request, where it
can be reported properly.

Set ADAPTLY_WARM_MODELS=0 to skip it - for a machine short on memory, or for
anything that imports the app without wanting TensorFlow loaded.
"""

import logging
import os
import threading

log = logging.getLogger(__name__)

ENV_SWITCH = "ADAPTLY_WARM_MODELS"


def enabled() -> bool:
    return os.getenv(ENV_SWITCH, "1").strip().lower() not in ("0", "false", "no", "off")


def _load_both() -> None:
    try:
        from ml.inference import model

        # Both variants: one server serves calibrated and uncalibrated
        # learners, and the second would otherwise pay the wait itself.
        model.load_model(calibrated=False)
        model.load_model(calibrated=True)
        log.info("engagement models warmed")
    except Exception:  # noqa: BLE001 - see module docstring
        log.warning("engagement model warm-up failed", exc_info=True)


def warm_models_in_background() -> threading.Thread | None:
    """Start the warm-up and return its thread, or None when switched off."""
    if not enabled():
        return None
    thread = threading.Thread(target=_load_both, name="engagement-model-warmup", daemon=True)
    thread.start()
    return thread
