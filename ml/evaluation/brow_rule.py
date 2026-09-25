"""
Does a per-user brow rule catch Struggling clips the model misses?

Why
---
The calibration experiment raised subject coverage from 5.5 to 9.9 of 19 test
subjects, but Struggling **recall fell**, 0.142 to 0.121. Coverage improved by
spreading fewer detections across more people. That is a trade, not a gain,
and recall still needs to improve on its own terms.

`backend/app/engagement/furrow.py` already exists - 206 lines of working brow
detector - and `routes.py` computes it on every request and then discards it:
the state precedence chain never reads `furrow_result`. It is advisory only.

The argument for wiring it in is stronger after 7.6 than before it. A brow
rule compares a user against **their own** calibrated baseline, so it never
has to generalise across faces - which is precisely where the model failed.
And `brow_raise` was measured carrying 5.9x more identity than signal, so a
per-user comparison is not a fallback for that feature, it is the only correct
way to use it.

This script asks whether that argument survives contact with data, before any
live threshold session: taking each subject's own focused clips as their
baseline, does a brow rule fire on Struggling clips the model does not?

What a brow furrow looks like in these features
------------------------------------------------
Furrowing lowers the brows toward the eyes and pulls them together, so
relative to a user's own baseline:

    brow_raise  decreases   (brow-to-eye distance shrinks)
    inter_brow  decreases   (brows draw together)

The rule fires when either drops more than `k` standard deviations below that
subject's own baseline, with the deviation measured on their focused clips.

Usage
-----
    python -m ml.evaluation.brow_rule --data-dir DIR
"""

import argparse
import sys

import numpy as np

from ml.evaluation.calibration_experiment import (
    FEATURE_NAMES,
    FOCUSED,
    STRUGGLING,
    SPLITS,
    load_split,
)

BROW_RAISE = FEATURE_NAMES.index("brow_raise")
INTER_BROW = FEATURE_NAMES.index("inter_brow")


def brow_rule_predictions(X, y, subjects, k):
    """
    Per-subject brow rule. Returns a boolean array: True = rule says struggling.

    The baseline and the spread both come from the subject's own FOCUSED
    clips, mirroring what a calibration session provides in production. A
    subject's struggling clips never enter their own baseline.
    """
    fires = np.zeros(len(y), dtype=bool)

    for subject in np.unique(subjects):
        rows = np.where(subjects == subject)[0]
        focused = rows[y[rows] == FOCUSED]
        if len(focused) < 2:
            continue                      # no usable calibration for this person

        baseline = X[focused].reshape(-1, X.shape[-1])
        for index in (BROW_RAISE, INTER_BROW):
            mean = baseline[:, index].mean()
            std = baseline[:, index].std()
            if std < 1e-9:
                continue
            # Clip-level mean of the feature, against this subject's own scale.
            clip_values = X[rows][:, :, index].mean(axis=1)
            fires[rows] |= clip_values < (mean - k * std)

    return fires


def scores(pred_struggling, y, subjects):
    tp = int(((pred_struggling) & (y == STRUGGLING)).sum())
    predicted = int(pred_struggling.sum())
    actual = int((y == STRUGGLING).sum())

    covered = total = 0
    for subject in np.unique(subjects):
        rows = subjects == subject
        if (y[rows] == STRUGGLING).sum() == 0:
            continue
        total += 1
        if (pred_struggling[rows] & (y[rows] == STRUGGLING)).sum() > 0:
            covered += 1

    base = actual / len(y)
    precision = tp / predicted if predicted else 0.0
    return {
        "recall": tp / actual if actual else 0.0,
        "precision": precision,
        "lift": precision / base if base else float("nan"),
        "coverage": covered,
        "subjects": total,
        "flag_rate": predicted / len(y),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--model", default="best_model_9f.keras")
    parser.add_argument("--scaler", default="scaler_9f.pkl")
    args = parser.parse_args(argv)

    import os
    import pickle

    import tensorflow as tf

    X, y, subjects = load_split(args.data_dir, "test")

    model = tf.keras.models.load_model(os.path.join(args.data_dir, args.model))
    with open(os.path.join(args.data_dir, args.scaler), "rb") as handle:
        scaler = pickle.load(handle)
    normalised = scaler.transform(X.reshape(-1, X.shape[-1])).reshape(X.shape)
    model_struggling = model.predict(normalised, verbose=0).argmax(axis=1) == STRUGGLING

    model_scores = scores(model_struggling, y, subjects)

    print(f"\n{'=' * 86}")
    print("PER-USER BROW RULE vs THE MODEL, on the test split")
    print("=" * 86)
    print(f"{'rule':<26}{'recall':>9}{'precision':>11}{'lift':>8}"
          f"{'coverage':>11}{'flag rate':>11}{'new TPs':>10}")
    print("-" * 86)
    print(f"{'model (argmax)':<26}{model_scores['recall']:>9.3f}"
          f"{model_scores['precision']:>11.3f}{model_scores['lift']:>8.2f}x"
          f"{model_scores['coverage']:>8}/{model_scores['subjects']:<2}"
          f"{model_scores['flag_rate']:>11.3f}{'-':>10}")

    best = None
    for k in (1.0, 1.5, 2.0, 2.5, 3.0):
        rule = brow_rule_predictions(X, y, subjects, k)
        rule_scores = scores(rule, y, subjects)
        union = rule | model_struggling
        union_scores = scores(union, y, subjects)

        # Struggling clips the rule catches that the model missed entirely.
        new_tp = int((rule & (y == STRUGGLING) & ~model_struggling).sum())

        print(f"{'  brow rule k=' + f'{k}':<26}{rule_scores['recall']:>9.3f}"
              f"{rule_scores['precision']:>11.3f}{rule_scores['lift']:>8.2f}x"
              f"{rule_scores['coverage']:>8}/{rule_scores['subjects']:<2}"
              f"{rule_scores['flag_rate']:>11.3f}{new_tp:>10}")
        print(f"{'  model OR rule k=' + f'{k}':<26}{union_scores['recall']:>9.3f}"
              f"{union_scores['precision']:>11.3f}{union_scores['lift']:>8.2f}x"
              f"{union_scores['coverage']:>8}/{union_scores['subjects']:<2}"
              f"{union_scores['flag_rate']:>11.3f}{'':>10}")
        if union_scores["lift"] > 1.0:
            if best is None or union_scores["recall"] > best[1]["recall"]:
                best = (k, union_scores, new_tp)

    print(f"\n{'=' * 86}")
    print("VERDICT")
    print("=" * 86)
    if best is None:
        print("  No setting of the rule keeps precision above the base rate when")
        print("  combined with the model. On this evidence the brow rule adds")
        print("  noise, not detections, and wiring it in would not be justified.")
    else:
        k, s, new_tp = best
        print(f"  Best union: k={k}")
        print(f"    recall   {model_scores['recall']:.3f} -> {s['recall']:.3f}")
        print(f"    coverage {model_scores['coverage']}/{model_scores['subjects']}"
              f" -> {s['coverage']}/{s['subjects']}")
        print(f"    lift     {model_scores['lift']:.2f}x -> {s['lift']:.2f}x")
        print(f"    {new_tp} struggling clips caught that the model missed entirely")
        print("\n  A genuine recall gain needs recall up, lift still above 1.0,")
        print("  and coverage not falling. Check all three before acting on it.")

    print("\n  NOTE: this uses brow_raise and inter_brow from the extracted")
    print("  features, not furrow.py's own landmark geometry. It tests whether")
    print("  the SIGNAL is there, which is the question worth answering before")
    print("  spending a live session measuring furrow.py's actual threshold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
