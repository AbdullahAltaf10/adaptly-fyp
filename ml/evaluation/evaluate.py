"""
Reproduce the model card's performance table from the committed artifacts.

Why this exists
---------------
Until now, every number in docs/model/model-card.md was an assertion. The
notebook that produced them was not kept in the repository, so nothing here
could regenerate or re-check them, and a change to the model or the feature
code would not have shown up as a change in any reported metric.

This script closes that gap. It loads the artifacts in ml/artifacts/, runs a
held-out split through the same feature scaling production uses, and prints
the same table the model card publishes - with a pass/fail comparison against
the published figures, so drift is visible without anyone having to remember
what 0.351 was.

What it deliberately does NOT do
--------------------------------
It does not re-extract features from DAiSEE video. That step needs the raw
dataset and several hours of MediaPipe processing, and it is not what this
script is for. It consumes the preprocessed arrays that step produced.

Usage
-----
    python -m ml.evaluation.evaluate --data-dir path/to/arrays

The directory must contain X_test_9f.npy, y_test_9f.npy, X_val_9f.npy and
y_val_9f.npy - the arrays saved by the training work, one clip per row, each
row (10, 9) in the documented feature order.

Interpreting the output
-----------------------
Read per-class recall and macro F1. Do NOT read accuracy: always predicting
"focused" scores 84.7% on this test set, so accuracy measures the class
imbalance rather than the model. The script prints the majority baseline
alongside accuracy for exactly this reason.
"""

import argparse
import os
import sys

import numpy as np

from ml.inference.model import (
    FEATURE_COUNT,
    STATE_LABELS,
    WINDOW_SIZE,
    artifact_path,
    load_model,
    verify_artifacts,
)

# Published in docs/model/model-card.md. Kept here so the script can report
# agreement or drift on its own, rather than relying on the reader to
# remember the target numbers.
PUBLISHED = {
    "test": {"macro_f1": 0.351, "focused": 0.77, "drifting": 0.30, "struggling": 0.10},
    "validation": {"macro_f1": 0.387, "focused": 0.74, "drifting": 0.27, "struggling": 0.18},
}

# How far a recomputed figure may drift before it is worth investigating.
# Chosen to absorb rounding in the published table (given to 2-3 significant
# figures) without absorbing a real regression.
TOLERANCE = 0.02

SPLIT_FILES = {
    "test": ("X_test_9f.npy", "y_test_9f.npy"),
    "validation": ("X_val_9f.npy", "y_val_9f.npy"),
}


def load_scaler():
    """
    Load the scaler from ml/artifacts/, not from wherever the arrays came from.

    This is deliberate: the point of the exercise is to measure what production
    actually runs. Production loads this file, so the evaluation must load the
    same one, even though the training work kept its own copy beside the data.
    """
    import pickle

    with open(artifact_path("scaler_9f.pkl"), "rb") as handle:
        return pickle.load(handle)


def load_split(data_dir: str, split: str):
    x_name, y_name = SPLIT_FILES[split]
    x_path = os.path.join(data_dir, x_name)
    y_path = os.path.join(data_dir, y_name)
    for path in (x_path, y_path):
        if not os.path.exists(path):
            raise SystemExit(
                f"Missing {path}.\n"
                f"This script needs the preprocessed arrays; see the module docstring."
            )

    X = np.load(x_path)
    y = np.load(y_path)

    # A silently misshaped array would still run and still produce numbers -
    # wrong ones. Fail loudly instead.
    if X.ndim != 3 or X.shape[1] != WINDOW_SIZE or X.shape[2] != FEATURE_COUNT:
        raise SystemExit(
            f"{x_name} has shape {X.shape}, expected (n, {WINDOW_SIZE}, {FEATURE_COUNT})."
        )
    if len(X) != len(y):
        raise SystemExit(f"{x_name} has {len(X)} rows but {y_name} has {len(y)}.")

    return X, y


def normalise(X, scaler):
    """Flatten to (n*10, 9), scale, reshape back - the training-time order."""
    original_shape = X.shape
    flat = X.reshape(-1, X.shape[-1])
    return scaler.transform(flat).reshape(original_shape)


def evaluate_split(model, scaler, X, y):
    from sklearn.metrics import confusion_matrix, f1_score, recall_score

    predictions = model.predict(normalise(X, scaler), verbose=0).argmax(axis=1)

    return {
        "macro_f1": f1_score(y, predictions, average="macro", zero_division=0),
        "recall": recall_score(y, predictions, average=None, zero_division=0),
        "accuracy": float((predictions == y).mean()),
        # The number accuracy must always be read against: what a classifier
        # that always guessed the majority class would score on this same split.
        "majority_baseline": float((y == 0).mean()),
        "confusion": confusion_matrix(y, predictions),
        "support": np.bincount(y, minlength=len(STATE_LABELS)),
    }


def print_report(split: str, result: dict) -> bool:
    """Print one split's table. Returns True if it matches the published figures."""
    published = PUBLISHED[split]
    labels = [STATE_LABELS[i] for i in range(len(STATE_LABELS))]

    print(f"\n{'=' * 62}")
    print(f"{split.upper()} SET   (n = {int(result['support'].sum())})")
    print("=" * 62)

    print(f"{'metric':<20}{'measured':>10}{'published':>11}{'delta':>9}   status")
    print("-" * 62)

    rows = [("macro F1", result["macro_f1"], published["macro_f1"])]
    for index, label in enumerate(labels):
        rows.append((f"{label} recall", result["recall"][index], published[label]))

    ok = True
    for name, measured, target in rows:
        delta = measured - target
        matches = abs(delta) <= TOLERANCE
        ok = ok and matches
        print(f"{name:<20}{measured:>10.3f}{target:>11.3f}{delta:>+9.3f}   "
              f"{'ok' if matches else 'DRIFT'}")

    print("-" * 62)
    print(f"{'accuracy':<20}{result['accuracy']:>10.3f}"
          f"   (majority baseline {result['majority_baseline']:.3f} - do not quote accuracy)")

    print("\nconfusion matrix (rows = true, columns = predicted)")
    header = " " * 12 + "".join(f"{label:>12}" for label in labels)
    print(header)
    for index, label in enumerate(labels):
        row = "".join(f"{count:>12}" for count in result["confusion"][index])
        print(f"{label:>12}{row}")

    return ok


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Directory holding X_test_9f.npy, y_test_9f.npy, X_val_9f.npy, y_val_9f.npy",
    )
    parser.add_argument(
        "--skip-verify",
        action="store_true",
        help="Evaluate even if artifact hashes do not match the manifest (not recommended)",
    )
    args = parser.parse_args(argv)

    # Refuse to evaluate artifacts that are not the ones the manifest records.
    # Measuring a silently-changed model produces plausible but meaningless
    # numbers, which is worse than producing none.
    print("verifying artifacts against ml/artifacts/MANIFEST.json")
    results = verify_artifacts()
    for filename, matched in sorted(results.items()):
        print(f"  {'ok   ' if matched else 'FAIL '} {filename}")
    if not all(results.values()):
        if not args.skip_verify:
            print("\nArtifact hashes do not match the manifest. Refusing to evaluate.\n"
                  "Re-run with --skip-verify only if you know why they differ.")
            return 2
        print("\nContinuing despite hash mismatch because --skip-verify was given.")

    model, _ = load_model()
    scaler = load_scaler()

    all_ok = True
    for split in ("test", "validation"):
        X, y = load_split(args.data_dir, split)
        all_ok &= print_report(split, evaluate_split(model, scaler, X, y))

    print(f"\n{'=' * 62}")
    if all_ok:
        print(f"All figures agree with the model card within +/-{TOLERANCE}.")
    else:
        print("At least one figure has drifted from the model card.\n"
              "Investigate before trusting any downstream measurement.")
    print("=" * 62)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
