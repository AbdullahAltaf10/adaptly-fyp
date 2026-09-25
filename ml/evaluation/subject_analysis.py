"""
Ask whether the Struggling signal is a property of behaviour or of people.

Why
---
The variant comparison produced a result that neither the model card nor any
recall figure explains. Measuring precision against the class base rate
("lift"), the 9-feature and 11-feature models are mirror images:

    9-feature   validation 1.56x   test 0.80x
    11-feature  validation 0.89x   test 2.67x

Each works on exactly one split and falls to chance on the other. A model that
had genuinely learned what struggling looks like would not behave that way.
The obvious alternative explanation is that it learned what struggling looks
like *on particular faces*, and DAiSEE's splits are subject-disjoint - so a
model tuned to one split's people has nothing to apply to the other's.

This script tests that directly, by scoring each held-out subject separately.
If the signal is behavioural, performance should be spread across subjects. If
it is subject-specific, it will be concentrated in a few and absent in most.

Row-to-clip mapping
-------------------
The arrays were built by iterating `{clip_id: {...}}` in file order and
skipping nothing (the notebook reports 0 skipped for every split), so array
row i corresponds to the i-th key of the features JSON. DAiSEE clip ids begin
with their six-digit subject id.

Usage
-----
    python -m ml.evaluation.subject_analysis --data-dir path/to/arrays
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import numpy as np

STRUGGLING = 2
SUBJECT_ID_LENGTH = 6

SPLITS = {
    "test": ("Test_9features.json", "X_test_9f.npy", "y_test_9f.npy"),
    "validation": ("Validation_9features.json", "X_val_9f.npy", "y_val_9f.npy"),
}


def clip_ids_in_array_order(json_path: str) -> list:
    with open(json_path, "r") as handle:
        records = json.load(handle)
    # Mirrors build_arrays_9f: iterate in order, skip rows with no label.
    return [clip for clip, data in records.items() if data.get("state") is not None]


def subject_of(clip_id: str) -> str:
    return clip_id[:SUBJECT_ID_LENGTH]


def analyse(data_dir: str, split: str, model, scaler):
    json_name, x_name, y_name = SPLITS[split]
    clips = clip_ids_in_array_order(os.path.join(data_dir, json_name))
    X = np.load(os.path.join(data_dir, x_name))
    y = np.load(os.path.join(data_dir, y_name))

    if len(clips) != len(y):
        raise SystemExit(
            f"{split}: {len(clips)} clips in JSON but {len(y)} rows in arrays. "
            "The row-to-clip mapping assumption does not hold; do not trust "
            "per-subject numbers until this is resolved."
        )

    flat = X.reshape(-1, X.shape[-1])
    predictions = model.predict(
        scaler.transform(flat).reshape(X.shape), verbose=0
    ).argmax(axis=1)

    per_subject = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "n": 0})
    for clip, true, pred in zip(clips, y, predictions):
        s = per_subject[subject_of(clip)]
        s["n"] += 1
        if pred == STRUGGLING and true == STRUGGLING:
            s["tp"] += 1
        elif pred == STRUGGLING:
            s["fp"] += 1
        elif true == STRUGGLING:
            s["fn"] += 1
    return per_subject


def report(split: str, per_subject: dict) -> None:
    rows = []
    for subject, c in sorted(per_subject.items()):
        predicted = c["tp"] + c["fp"]
        actual = c["tp"] + c["fn"]
        precision = c["tp"] / predicted if predicted else None
        recall = c["tp"] / actual if actual else None
        rows.append((subject, c["n"], actual, predicted, c["tp"], precision, recall))

    total_tp = sum(r[4] for r in rows)
    with_struggling = [r for r in rows if r[2] > 0]
    carrying = [r for r in rows if r[4] > 0]

    print(f"\n{'=' * 78}")
    print(f"{split.upper()} - per subject")
    print("=" * 78)
    print(f"{'subject':<10}{'clips':>7}{'true S':>8}{'pred S':>8}{'correct':>9}"
          f"{'prec':>8}{'recall':>8}")
    print("-" * 78)
    for subject, n, actual, predicted, tp, precision, recall in rows:
        p = f"{precision:.2f}" if precision is not None else "  -"
        r = f"{recall:.2f}" if recall is not None else "  -"
        mark = "  *" if tp > 0 else ""
        print(f"{subject:<10}{n:>7}{actual:>8}{predicted:>8}{tp:>9}{p:>8}{r:>8}{mark}")

    print("-" * 78)
    print(f"subjects in split                     : {len(rows)}")
    print(f"subjects that actually struggle       : {len(with_struggling)}")
    print(f"subjects the model gets ANY right on  : {len(carrying)}")
    if total_tp:
        share = max(r[4] for r in carrying) / total_tp
        print(f"largest single subject's share of all correct detections: {share:.0%}")
    print("\n  A behavioural signal would spread correct detections across most")
    print("  subjects who struggle. Concentration in a few means the model has")
    print("  learned faces, not behaviour.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args(argv)

    import pickle

    import tensorflow as tf

    model = tf.keras.models.load_model(os.path.join(args.data_dir, "best_model_9f.keras"))
    with open(os.path.join(args.data_dir, "scaler_9f.pkl"), "rb") as handle:
        scaler = pickle.load(handle)

    for split in ("test", "validation"):
        report(split, analyse(args.data_dir, split, model, scaler))
    return 0


if __name__ == "__main__":
    sys.exit(main())
