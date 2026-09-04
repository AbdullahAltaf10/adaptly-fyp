"""
Re-reading / comprehension-regression detection.

STATUS: NOT IMPLEMENTED. Explicitly pending, as the issue's acceptance criteria
allow ("re-reading status is either implemented or explicitly marked pending").

What it is meant to do
----------------------
Scope section 6.3: a separate binary classifier inspects the gaze X-coordinate
time series every 10 seconds. Normal forward reading produces a steadily
increasing gaze X; comprehension difficulty produces a sudden leftward jump as
the reader goes back over a line. That regression pattern is a measurable signal
of reading difficulty, independent of the engagement model.

Why it is not implemented
-------------------------
It needs a model trained on the OneStop Eye Movements dataset — a separate
machine-learning sub-project comparable in size to the DAiSEE work, including
data access, preprocessing, training and evaluation. None of that has started.

Two things constrain it even once built, and both are worth knowing before
anyone plans around it:

  * Scope section 7 records webcam gaze accuracy at roughly 2-3 cm on screen,
    against 3-5 mm line spacing. So this can never identify WHICH line is being
    re-read - it operates at paragraph and pattern level only.
  * The engagement pipeline currently samples once per second. A regression
    saccade lasts tens of milliseconds. Detecting the pattern reliably will
    need a higher gaze sampling rate than the engagement loop uses, so this is
    likely a separate stream rather than another feature on the existing one.

Until then `detect_rereading` returns a clearly-marked "pending" result rather
than a fabricated one, so no downstream module mistakes silence for a negative.
The shared engagement-event contract already reserves
`gaze_regression_detected`, and Module 8's `reason_code` reserves
`reading_difficulty`, so neither needs a schema change when this lands.
"""

STATUS_PENDING = "pending"
STATUS_AVAILABLE = "available"


def is_available() -> bool:
    """Whether re-reading detection can produce a real answer. Currently never."""
    return False


def detect_rereading(gaze_x_series) -> dict:
    """
    gaze_x_series: horizontal gaze positions over time.

    Returns a result marked pending. `detected` is False, but callers should
    check `status` — False here means "not measured", not "measured and absent".
    """
    return {
        "status": STATUS_PENDING,
        "detected": False,
        "confidence": None,
        "reason": "Re-reading detection requires the OneStop classifier, which is not built.",
    }
