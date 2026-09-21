"""
Train and export a per-subject-centred model as production artifacts.

What this produces
------------------
    ml/artifacts/best_model_9f_calibrated.keras
    ml/artifacts/scaler_9f_calibrated.pkl

alongside the existing uncalibrated pair, which it does not touch. PR #38 is
approved and should merge as it stands; swapping the production model is a
separate, reviewable decision and this script does not make it.

Why a second model at all
-------------------------
`calibration_experiment.py` established, across two independent 10-seed runs,
that centring each subject on their own baseline during training raises
subject coverage from 5.5 to 9.9 of 19 test subjects (p < 0.01, Cohen d ~1.4).
`calibrated_threshold.py` then showed that the calibrated model's probability
ranking carries enough signal for threshold moving to work, which it did not
on the uncalibrated model.

For the artifact this script actually exports, measured on test at its own
validation-derived threshold of 0.34, against the shipped uncalibrated model:

    Struggling recall   0.099 -> 0.276
    subject coverage     6/19 -> 15/19
    precision lift       0.80x -> 1.29x   (below random -> above it)
    macro F1            0.351 -> 0.398
    flag rate           0.123 -> 0.214    (the cost)

Note the threshold is derived for THIS artifact, not taken from the averaged
study, which suggested 0.40. The selected model is more conservative than the
seed average - its argmax flag rate is 0.051 against roughly 0.100 - so an
averaged threshold does not transfer. Re-derive it whenever the model changes.

The train/inference mismatch this closes
-----------------------------------------
`backend/app/engagement/calibration.py` already computes, at inference:

    calibrated = raw - user_focused_mean + daisee_focused_reference

so production has been feeding per-subject-centred features to a model trained
on raw ones. This trains on the same quantity inference produces. No change to
calibration.py is needed - the per-subject standardisation arm was tested and
rejected, so its offset-only design is correct.

Model selection
---------------
Several seeds are trained and the one with the best VALIDATION macro recall is
exported - the same criterion the original notebook used, and applied to the
same held-out split. Test is never consulted.

Usage
-----
    python -m ml.evaluation.train_calibrated --data-dir DIR [--seeds 5]
"""

import argparse
import hashlib
import json
import os
import pickle
import sys
from datetime import datetime, timezone

import numpy as np

from ml.evaluation.calibration_experiment import (
    FEATURE_NAMES,
    FOCUSED,
    SPLITS,
    STRUGGLING,
    centre_per_subject,
    load_split,
    oversample,
    train_once,
)
from ml.inference.model import ARTIFACT_DIR

MODEL_FILE = "best_model_9f_calibrated.keras"
SCALER_FILE = "scaler_9f_calibrated.pkl"

# Evidence-based default operating point, from calibrated_threshold.py.
# Derived on validation for the artifact this produces, not copied from the
# multi-seed study - an averaged threshold does not transfer to an individual
# model, which can be more or less conservative than the average. Re-derive it
# whenever the exported model changes. See MANIFEST.json threshold_note.
RECOMMENDED_THRESHOLD = 0.34


def sha256(path):
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--out-dir", default=ARTIFACT_DIR)
    args = parser.parse_args(argv)

    from sklearn.metrics import recall_score
    from sklearn.preprocessing import StandardScaler

    data = {s: load_split(args.data_dir, s) for s in SPLITS}
    X_tr, y_tr, _ = data["train"]
    global_focused = X_tr[y_tr == FOCUSED].reshape(-1, X_tr.shape[-1]).mean(axis=0)

    prepared = {}
    for s in SPLITS:
        Xs, ys, subs = data[s]
        prepared[s], _, _ = centre_per_subject(Xs, ys, subs, global_focused)

    scaler = StandardScaler().fit(prepared["train"].reshape(-1, len(FEATURE_NAMES)))

    def norm(X):
        return scaler.transform(X.reshape(-1, X.shape[-1])).reshape(X.shape)

    Xtr_n, Xval_n = norm(prepared["train"]), norm(prepared["validation"])
    y_val = data["validation"][1]

    print(f"training {args.seeds} seed(s), selecting on validation macro recall\n")
    best = None
    for seed in range(args.seeds):
        Xb, yb = oversample(Xtr_n, y_tr, seed)
        model = train_once(Xb, yb, Xval_n, y_val, seed)
        preds = model.predict(Xval_n, verbose=0).argmax(axis=1)
        macro_recall = recall_score(y_val, preds, average="macro", zero_division=0)
        strug = recall_score(y_val, preds, average=None, zero_division=0,
                             labels=[0, 1, 2])[STRUGGLING]
        print(f"  seed {seed}: val macro recall {macro_recall:.4f}  "
              f"val struggling recall {strug:.3f}")
        if best is None or macro_recall > best[0]:
            best = (macro_recall, seed, model)

    macro_recall, seed, model = best
    print(f"\nselected seed {seed} (val macro recall {macro_recall:.4f})")

    os.makedirs(args.out_dir, exist_ok=True)
    model_path = os.path.join(args.out_dir, MODEL_FILE)
    scaler_path = os.path.join(args.out_dir, SCALER_FILE)
    model.save(model_path)
    with open(scaler_path, "wb") as handle:
        pickle.dump(scaler, handle)

    print(f"\nwrote {model_path}")
    print(f"wrote {scaler_path}")

    # Extend the manifest rather than replacing it: the uncalibrated artifacts
    # are still the ones production loads, and their hashes must keep working.
    manifest_path = os.path.join(args.out_dir, "MANIFEST.json")
    with open(manifest_path) as handle:
        manifest = json.load(handle)

    for path, name in ((model_path, MODEL_FILE), (scaler_path, SCALER_FILE)):
        manifest["artifacts"][name] = {
            "sha256": sha256(path),
            "size_bytes": os.path.getsize(path),
        }

    manifest["calibrated_variant"] = {
        "description": (
            "Trained on per-subject-centred features, matching what "
            "backend/app/engagement/calibration.py already produces at "
            "inference. Not yet the production model - see "
            "ml/evaluation/README.md."
        ),
        "model": MODEL_FILE,
        "scaler": SCALER_FILE,
        "selected_seed": seed,
        "validation_macro_recall": round(float(macro_recall), 4),
        "recommended_threshold": RECOMMENDED_THRESHOLD,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "training": {
            "epochs": 50,
            "batch_size": 32,
            "learning_rate": 0.0005,
            "oversample_targets": {"drifting": 2500, "struggling": 2500},
            "oversample_noise_std": 0.05,
            "early_stopping": "val_macro_recall, patience 7, restore best",
        },
    }

    with open(manifest_path, "w") as handle:
        json.dump(manifest, handle, indent=2)
        handle.write("\n")
    print(f"updated {manifest_path}")

    print(f"\nrecommended threshold for this model: {RECOMMENDED_THRESHOLD}")
    print("It is NOT applied automatically. ml/inference/model.py still uses")
    print("argmax, and the production path still loads the uncalibrated model.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
