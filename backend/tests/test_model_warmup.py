"""
Loading the engagement models at start-up, in the background.

The study screen tells the learner the backend has usually finished loading
TensorFlow before they arrive. Nothing did that loading until this existed, so
the first reading of the first session paid a 13+ second wait. These tests pin
the three things that make it safe: it really loads both variants, it can be
switched off, and it can never take the server down or load anything twice.

Run from backend/:   python -m pytest tests/test_model_warmup.py -v
"""

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.engagement import warmup  # noqa: E402
from ml.inference import model as ml_model  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    """Every test starts with nothing loaded and puts the real cache back."""
    monkeypatch.setattr(ml_model, "_loaded", {})
    monkeypatch.delenv(warmup.ENV_SWITCH, raising=False)


def test_it_loads_both_variants(monkeypatch):
    loaded = []
    monkeypatch.setattr(ml_model, "load_model", lambda calibrated=False: loaded.append(calibrated))

    thread = warmup.warm_models_in_background()
    thread.join(timeout=5)

    assert sorted(loaded) == [False, True], "one server serves both kinds of learner"


def test_it_runs_on_a_daemon_thread_so_start_up_is_not_held_up(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(ml_model, "load_model", lambda calibrated=False: release.wait(5))

    started = time.monotonic()
    thread = warmup.warm_models_in_background()
    returned_after = time.monotonic() - started

    assert thread.daemon is True
    assert returned_after < 1.0, "the call must return while the load is still running"
    assert thread.is_alive()
    release.set()
    thread.join(timeout=5)


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE"])
def test_it_can_be_switched_off(monkeypatch, value):
    monkeypatch.setenv(warmup.ENV_SWITCH, value)
    called = []
    monkeypatch.setattr(ml_model, "load_model", lambda calibrated=False: called.append(1))

    assert warmup.warm_models_in_background() is None
    assert called == []


def test_a_failed_warm_up_never_raises(monkeypatch):
    def boom(calibrated=False):
        raise RuntimeError("model file missing")

    monkeypatch.setattr(ml_model, "load_model", boom)

    thread = warmup.warm_models_in_background()
    thread.join(timeout=5)  # would surface the exception if it escaped

    assert not thread.is_alive()


def test_two_callers_loading_at_once_load_the_model_only_once(monkeypatch):
    """The warm-up and the first learner's request can arrive together."""
    import tensorflow as tf

    calls = []

    def slow_load(path):
        calls.append(path)
        time.sleep(0.3)
        return object()

    monkeypatch.setattr(tf.keras.models, "load_model", slow_load)

    results = []
    threads = [
        threading.Thread(target=lambda: results.append(ml_model.load_model(calibrated=False)))
        for _ in range(2)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert len(calls) == 1, "the second caller must wait for the first, not load its own copy"
    assert results[0] is results[1]


def test_the_app_starts_the_warm_up_when_it_starts(monkeypatch):
    from app import main

    started = []
    monkeypatch.setattr(main, "warm_models_in_background", lambda: started.append(1))

    with TestClient(main.app):
        pass

    assert started == [1]
