"""
Compare the 7-, 9- and 11-feature model variants on the same splits.

Why
---
The model card rejects the 11-feature variant as "better on the test set, but
inconsistent between test and validation (10% vs 6%), where the 9-feature
version was stable (10% vs 18%)". Two problems with that reasoning:

  - The 9-feature variant's Struggling recall nearly doubles between test and
    validation (0.10 -> 0.18). That is a *larger* relative swing than the
    11-feature variant's (0.10 -> 0.06). Both are unstable; one is unstable in
    the flattering direction.
  - The 11-feature variant had the best test macro F1 of any variant by a
    clear margin (0.411 vs 0.351), which the summary does not mention.

The model card is honest that only one training run was done per
configuration, so none of this is hidden - but the wording implies a
confidence the numbers do not support. This script settles it by putting all
three variants through identical evaluation, including the precision-against-
base-rate check that turned out to matter more than recall.

This is a diagnostic, not part of the production path. It reads variant
artifacts from a directory rather than from ml/artifacts/, because only the
9-feature model is committed.

Usage
-----
    python -m ml.evaluation.compare_variants --data-dir path/to/arrays
"""

import argparse
import os
import pickle
import sys

import numpy as np

STRUGGLING = 2
CLASS_NAMES = ("focused", "drifting", "struggling")

# name -> (feature count, model file, scaler file, array suffix)
VARIANTS = {
    "7-feature": (7, "best_model_7f_v3.keras", "scaler_7f.pkl", "7f"),
    "9-feature (production)": (9, "best_model_9f.keras", "scaler_9f.pkl", "9f"),
    "11-feature (+mouth)": (11, "best_model_11f.keras", "scaler_11f.pkl", "11f"),
}

SPLITS = {"test": "test", "validation": "val"}


def load_variant(data_dir, model_file, scaler_file):
    import tensorflow as tf

    model = tf.keras.models.load_model(os.path.join(data_dir, model_file))
    with open(os.path.join(data_dir, scaler_file), "rb") as handle:
        scaler = pickle.load(handle)
    return model, scaler


def evaluate(model, scaler, X, y):
    from sklearn.metrics import f1_score, precision_score, recall_score

    flat = X.reshape(-1, X.shape[-1])
    normalised = scaler.transform(flat).reshape(X.shape)
    predictions = model.predict(normalised, verbose=0).argmax(axis=1)

    labels = [0, 1, 2]
    recalls = recall_score(y, predictions, average=None, zero_division=0, labels=labels)
    precisions = precision_score(y, predictions, average=None, zero_division=0, labels=labels)
    base_rate = float((y == STRUGGLING).mean())

    return {
        "macro_f1": f1_score(y, predictions, average="macro", zero_division=0),
        "recall": recalls,
        "precision": precisions,
        "base_rate": base_rate,
        # The ratio that actually matters: at or below 1.0, a "struggling"
        # prediction carries no more information than a coin weighted to the
        # class frequency.
        "precision_lift": (precisions[STRUGGLING] / base_rate) if base_rate else float("nan"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    args = parser.parse_args(argv)

    results = {}
    for name, (n_features, model_file, scaler_file, suffix) in VARIANTS.items():
        model_path = os.path.join(args.data_dir, model_file)
        if not os.path.exists(model_path):
            print(f"skipping {name}: {model_file} not present")
            continue
        model, scaler = load_variant(args.data_dir, model_file, scaler_file)

        results[name] = {}
        for split, tag in SPLITS.items():
            X = np.load(os.path.join(args.data_dir, f"X_{tag}_{suffix}.npy"))
            y = np.load(os.path.join(args.data_dir, f"y_{tag}_{suffix}.npy"))
            assert X.shape[-1] == n_features, f"{name} {split}: expected {n_features} features"
            results[name][split] = evaluate(model, scaler, X, y)

    print(f"\n{'=' * 84}")
    print("VARIANT COMPARISON - identical splits, identical evaluation")
    print("=" * 84)
    print(f"{'variant':<24}{'split':<12}{'macro F1':>10}{'strug R':>9}"
          f"{'strug P':>9}{'base':>8}{'lift':>8}")
    print("-" * 84)
    for name, splits in results.items():
        for split, r in splits.items():
            warn = "  <-- at/below chance" if r["precision_lift"] <= 1.0 else ""
            print(f"{name:<24}{split:<12}{r['macro_f1']:>10.3f}"
                  f"{r['recall'][STRUGGLING]:>9.3f}{r['precision'][STRUGGLING]:>9.3f}"
                  f"{r['base_rate']:>8.3f}{r['precision_lift']:>8.2f}x{warn}")
        print()

    print("=" * 84)
    print("READING THIS TABLE")
    print("=" * 84)
    print("  lift = struggling precision / struggling base rate.")
    print("  lift <= 1.0 means the model's struggling prediction is no better")
    print("  than flagging windows at the class's own frequency. Recall is")
    print("  meaningless without it: a model can reach high recall purely by")
    print("  flagging everything.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
