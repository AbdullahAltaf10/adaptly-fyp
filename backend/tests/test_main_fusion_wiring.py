"""
The feature flag that turns Module 6 on. Off by default - a policy that
has never run against a live session should not become everyone's
default the moment it merges (same reasoning ml/inference/model.py uses
for why the calibrated model pair only activates for a learner who has
actually calibrated).
"""
import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.intervention import service  # noqa: E402
from app.intervention.policy import DefaultPolicy  # noqa: E402


def _reload_main():
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    else:
        importlib.import_module("app.main")


def test_default_policy_is_used_when_the_flag_is_unset(monkeypatch):
    monkeypatch.delenv("ADAPTLY_FUSION_POLICY", raising=False)
    service.set_decider(DefaultPolicy())  # known starting state
    _reload_main()
    assert isinstance(service.get_decider(), DefaultPolicy)


def test_fusion_policy_is_used_when_the_flag_is_set(monkeypatch):
    from app.fusion.policy import FusionPolicy

    monkeypatch.setenv("ADAPTLY_FUSION_POLICY", "1")
    service.set_decider(DefaultPolicy())  # known starting state
    _reload_main()
    assert isinstance(service.get_decider(), FusionPolicy)
    # Cleanup: leave the global decider as DefaultPolicy for every other
    # test file in the same process, and re-import app.main with the flag
    # unset again so later test files see the default wiring.
    service.set_decider(DefaultPolicy())
    monkeypatch.delenv("ADAPTLY_FUSION_POLICY", raising=False)
    _reload_main()
