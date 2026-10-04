"""
The "every 60 seconds" gate scope 6.6 asks for.

Not a new polling loop: Module 3 already calls in roughly every second via
/engagement/analyze. This is a pure, in-memory accumulator FusionPolicy
consults on every one of those calls - "has a full window passed since my
last actual decision for this session?" - matching the same
per-(uid, session_id), in-memory, dies-on-restart, single-worker-only
pattern already accepted and documented in engagement/smoothing.py and
intervention/cooldown.py. This is not a new limitation.
"""

FUSION_WINDOW_SECONDS = 60.0


class FusionWindow:
    def __init__(self) -> None:
        self._last_decided: dict[tuple[str, str], float] = {}

    def ready(self, uid: str, session_id: str, now: float) -> bool:
        last = self._last_decided.get((uid, session_id))
        if last is None:
            return True
        return now - last >= FUSION_WINDOW_SECONDS

    def mark_decided(self, uid: str, session_id: str, now: float) -> None:
        self._last_decided[(uid, session_id)] = now
