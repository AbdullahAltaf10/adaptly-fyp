"""
Guards for the evaluation harness.

The harness exists so the model card's numbers can be re-checked. These tests
exist so the harness itself cannot quietly stop doing that - by loading the
wrong scaler, by accepting a misshaped array, or by reporting agreement when
a figure has actually drifted.

The full end-to-end reproduction needs the preprocessed DAiSEE arrays, which
are large derived data and are not committed. Those tests skip cleanly when
the arrays are absent, so a fresh clone still passes, and run for anyone who
has them. Point ADAPTLY_EVAL_DATA at the directory to enable them.
"""

import os

import numpy as np
import pytest

from ml.evaluation import evaluate
from ml.inference.model import FEATURE_COUNT, STATE_LABELS, WINDOW_SIZE

DATA_DIR = os.environ.get("ADAPTLY_EVAL_DATA")
needs_arrays = pytest.mark.skipif(
    not DATA_DIR or not os.path.isdir(DATA_DIR),
    reason="set ADAPTLY_EVAL_DATA to the directory holding the preprocessed arrays",
)


# --------------------------------------------------------------------------
# Things that must hold without any data at all
# --------------------------------------------------------------------------

def test_published_figures_cover_every_class_and_split():
    """
    The comparison table is only meaningful if it covers everything reported.

    A missing entry here would silently drop a class from the drift check
    rather than fail, which is the failure mode this guards against.
    """
    labels = set(STATE_LABELS.values())
    for split in ("test", "validation"):
        published = evaluate.PUBLISHED[split]
        assert "macro_f1" in published
        assert labels <= set(published), f"{split} is missing a class"


def test_published_figures_match_the_model_card():
    """Pinned so an edit to one must be a deliberate edit to both."""
    assert evaluate.PUBLISHED["test"]["macro_f1"] == 0.351
    assert evaluate.PUBLISHED["test"]["struggling"] == 0.10
    assert evaluate.PUBLISHED["validation"]["macro_f1"] == 0.387
    assert evaluate.PUBLISHED["validation"]["struggling"] == 0.18


def test_scaler_is_loaded_from_the_committed_artifacts():
    """
    Not from beside the data.

    The harness measures what production runs, and production loads
    ml/artifacts/scaler_9f.pkl. Loading the training copy instead would make
    the numbers describe something nobody deploys.
    """
    scaler = evaluate.load_scaler()
    assert scaler.n_features_in_ == FEATURE_COUNT


def test_misshaped_array_is_rejected(tmp_path):
    """A wrong-shaped array would still produce numbers. It must not."""
    np.save(tmp_path / "X_test_9f.npy", np.zeros((4, WINDOW_SIZE, FEATURE_COUNT - 1)))
    np.save(tmp_path / "y_test_9f.npy", np.zeros(4, dtype=int))
    with pytest.raises(SystemExit):
        evaluate.load_split(str(tmp_path), "test")


def test_mismatched_lengths_are_rejected(tmp_path):
    np.save(tmp_path / "X_test_9f.npy", np.zeros((4, WINDOW_SIZE, FEATURE_COUNT)))
    np.save(tmp_path / "y_test_9f.npy", np.zeros(3, dtype=int))
    with pytest.raises(SystemExit):
        evaluate.load_split(str(tmp_path), "test")


def test_missing_arrays_give_a_clear_message(tmp_path):
    with pytest.raises(SystemExit) as exc:
        evaluate.load_split(str(tmp_path), "test")
    assert "X_test_9f.npy" in str(exc.value)


# --------------------------------------------------------------------------
# The reproduction itself - only when the arrays are present
# --------------------------------------------------------------------------

@needs_arrays
@pytest.mark.parametrize("split", ["test", "validation"])
def test_model_card_figures_reproduce(split):
    """
    The point of the whole exercise: the published table is checkable.

    If this fails, either the artifacts changed or the model card is wrong.
    Both are worth stopping for.
    """
    from ml.inference.model import load_model

    model, _ = load_model()
    X, y = evaluate.load_split(DATA_DIR, split)
    result = evaluate.evaluate_split(model, evaluate.load_scaler(), X, y)

    published = evaluate.PUBLISHED[split]
    assert result["macro_f1"] == pytest.approx(published["macro_f1"], abs=evaluate.TOLERANCE)
    for index, label in STATE_LABELS.items():
        assert result["recall"][index] == pytest.approx(
            published[label], abs=evaluate.TOLERANCE
        ), f"{split} {label} recall drifted"


# --------------------------------------------------------------------------
# The opt-in Struggling threshold on predict()
#
# These live here rather than in test_ml_inference.py so that the change to
# ml/inference/model.py stays a single additive edit, easy to review on its
# own. The behaviour they pin is that nothing changes unless a caller asks.
# --------------------------------------------------------------------------

def _probabilities(monkeypatch, values):
    """Stub the model so these tests exercise the decision rule, not the LSTM."""
    from ml.inference import model as ml_model

    class FakeModel:
        def predict(self, _batch, verbose=0):
            return np.array([values])

    class FakeScaler:
        def transform(self, array):
            return array

    monkeypatch.setattr(ml_model, "load_model", lambda: (FakeModel(), FakeScaler()))
    return ml_model


def _window():
    return [[0.0] * FEATURE_COUNT for _ in range(WINDOW_SIZE)]


def test_default_is_still_argmax(monkeypatch):
    """No threshold passed must mean exactly the behaviour that shipped."""
    ml_model = _probabilities(monkeypatch, [0.5, 0.2, 0.3])
    assert ml_model.predict(_window())["state"] == "focused"


def test_threshold_promotes_struggling_when_it_clears(monkeypatch):
    """0.30 is not the argmax, but it clears a 0.25 bar."""
    ml_model = _probabilities(monkeypatch, [0.5, 0.2, 0.3])
    result = ml_model.predict(_window(), struggling_threshold=0.25)
    assert result["state"] == "struggling"
    assert result["confidence"] == pytest.approx(0.3)


def test_threshold_leaves_other_classes_alone(monkeypatch):
    """Below the bar, the ordinary argmax still decides - including drifting."""
    ml_model = _probabilities(monkeypatch, [0.3, 0.6, 0.1])
    assert ml_model.predict(_window(), struggling_threshold=0.25)["state"] == "drifting"


def test_confidence_reports_the_reported_class(monkeypatch):
    """
    A promoted Struggling must report ITS probability, not the argmax class's.

    Getting this wrong would put a confidence in the engagement event that
    describes a different state than the one beside it - the same defect
    already logged against rule-sourced states (G5).
    """
    ml_model = _probabilities(monkeypatch, [0.55, 0.15, 0.30])
    result = ml_model.predict(_window(), struggling_threshold=0.25)
    assert result["state"] == "struggling"
    assert result["confidence"] == pytest.approx(0.30)


def test_threshold_of_one_never_promotes(monkeypatch):
    """A probability cannot reach 1.01, so the override can be switched off."""
    ml_model = _probabilities(monkeypatch, [0.4, 0.2, 0.4])
    assert ml_model.predict(_window(), struggling_threshold=1.01)["state"] == "focused"


@needs_arrays
def test_accuracy_is_reported_against_its_baseline():
    """
    Accuracy alone is misleading on this dataset and must never stand alone.

    Always predicting "focused" scores about 84.7% on the test split, so the
    baseline has to travel with the number.
    """
    from ml.inference.model import load_model

    model, _ = load_model()
    X, y = evaluate.load_split(DATA_DIR, "test")
    result = evaluate.evaluate_split(model, evaluate.load_scaler(), X, y)

    assert result["majority_baseline"] == pytest.approx(0.847, abs=0.01)
    assert result["accuracy"] <= result["majority_baseline"] + 0.05
