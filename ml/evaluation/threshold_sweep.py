"""
Measure what lowering the Struggling decision threshold actually buys.

Why
---
`ml/inference/model.py` currently takes `argmax` over the three class
probabilities. With three classes that means Struggling only wins when it is
already the most likely class - roughly p >= 0.34 - and the model's measured
Struggling recall is 0.10 on test, 0.18 on validation.

`argmax` is not a neutral choice. It is the Bayes-optimal rule only when the
cost of a false positive equals the cost of a false negative. Scope section
6.4 says interventions are delivered "without any sound, flash, or alert",
inline and dismissible, so a false alarm costs the learner very little, while
a missed struggling learner gets no help at all. Under that asymmetry the
optimal threshold is:

    tau* = C_FP / (C_FP + C_FN)

which sits well below the level `argmax` implies. This script measures the
real trade-off curve so that number can be chosen from evidence rather than
guessed.

Method
------
The rule swept here is a one-sided override:

    if P(struggling) >= tau:  predict struggling
    else:                     argmax over the remaining classes

Only Struggling gets a lowered bar. Drifting and Focused keep competing
normally, because Struggling is the only class where the downstream cost is
this asymmetric.

**The threshold is selected on VALIDATION and reported on TEST.** Choosing it
on the test set would tune to the set used to report, and the honest number
would be lost.

Usage
-----
    python -m ml.evaluation.threshold_sweep --data-dir path/to/arrays
"""

import argparse
import sys

import numpy as np

from ml.evaluation.evaluate import load_scaler, load_split, normalise
from ml.inference.model import STATE_LABELS, load_model

STRUGGLING = 2

# Swept from "almost never override" down to "override aggressively".
# The top of the range is deliberately above ~0.34, where a three-class argmax
# can already select Struggling, so the curve includes the current behaviour
# as its own baseline rather than assuming it.
THRESHOLDS = np.round(np.arange(0.50, 0.04, -0.01), 2)


def predict_with_threshold(probabilities: np.ndarray, tau: float) -> np.ndarray:
    """Apply the one-sided Struggling override described in the module docstring."""
    others = probabilities.copy()
    others[:, STRUGGLING] = -np.inf          # force argmax to ignore Struggling
    fallback = others.argmax(axis=1)
    return np.where(probabilities[:, STRUGGLING] >= tau, STRUGGLING, fallback)


def metrics_at(probabilities, y, tau=None):
    """
    Metrics at threshold `tau`, or for plain argmax when `tau` is None.

    The argmax case must be computed with argmax, not by passing an
    unreachable threshold: a threshold above 1.0 means Struggling is never
    selected at all, which is a different rule and scores 0 recall. That
    mistake made the baseline column read 0.000 on the first run.
    """
    from sklearn.metrics import f1_score, precision_score, recall_score

    if tau is None:
        predictions = probabilities.argmax(axis=1)
    else:
        predictions = predict_with_threshold(probabilities, tau)
    recalls = recall_score(y, predictions, average=None, zero_division=0,
                           labels=list(STATE_LABELS))
    precisions = precision_score(y, predictions, average=None, zero_division=0,
                                 labels=list(STATE_LABELS))
    return {
        "tau": tau if tau is not None else float("nan"),
        "macro_f1": f1_score(y, predictions, average="macro", zero_division=0),
        "struggling_recall": recalls[STRUGGLING],
        "struggling_precision": precisions[STRUGGLING],
        "focused_recall": recalls[0],
        "drifting_recall": recalls[1],
        # How many interventions this setting would trigger per 100 windows.
        # The cost of the policy is paid in this number, not in recall.
        "flag_rate": float((predictions == STRUGGLING).mean()),
    }


def bayes_threshold(cost_false_positive: float, cost_false_negative: float) -> float:
    """tau* = C_FP / (C_FP + C_FN). See the module docstring."""
    return cost_false_positive / (cost_false_positive + cost_false_negative)


def print_curve(title: str, rows: list) -> None:
    print(f"\n{'=' * 78}")
    print(title)
    print("=" * 78)
    print(f"{'tau':>6}{'strug recall':>14}{'strug prec':>12}{'macro F1':>11}"
          f"{'focused R':>11}{'flag rate':>11}")
    print("-" * 78)
    for r in rows:
        print(f"{r['tau']:>6.2f}{r['struggling_recall']:>14.3f}"
              f"{r['struggling_precision']:>12.3f}{r['macro_f1']:>11.3f}"
              f"{r['focused_recall']:>11.3f}{r['flag_rate']:>11.3f}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument(
        "--cost-ratio",
        type=float,
        default=8.0,
        help="How many redundant interventions are worth one caught struggling "
             "learner (C_FN / C_FP). Default 8 is a starting point for "
             "discussion, NOT a measured value - see the note in the output.",
    )
    args = parser.parse_args(argv)

    model, _ = load_model()
    scaler = load_scaler()

    probabilities = {}
    labels = {}
    for split in ("validation", "test"):
        X, y = load_split(args.data_dir, split)
        probabilities[split] = model.predict(normalise(X, scaler), verbose=0)
        labels[split] = y

    curves = {
        split: [metrics_at(probabilities[split], labels[split], t) for t in THRESHOLDS]
        for split in ("validation", "test")
    }

    print_curve("VALIDATION - the set the threshold is CHOSEN on", curves["validation"])

    # tau* from the stated cost asymmetry.
    tau_star = bayes_threshold(1.0, args.cost_ratio)
    nearest = min(THRESHOLDS, key=lambda t: abs(t - tau_star))

    print(f"\n{'-' * 78}")
    print(f"Bayes-optimal threshold for a {args.cost_ratio:g}:1 cost ratio "
          f"(one missed struggling learner costs {args.cost_ratio:g} redundant "
          f"interventions):")
    print(f"    tau* = 1 / (1 + {args.cost_ratio:g}) = {tau_star:.3f}"
          f"   -> nearest swept value {nearest:.2f}")
    print("\nNOTE: the cost ratio is an assumption, not a measurement. It is the")
    print("one number here that has to be agreed deliberately rather than")
    print("derived. Re-run with --cost-ratio to see other choices.")

    print_curve("TEST - held out, reported only, never used to choose", curves["test"])

    # Precision is unreadable without the base rate beside it. A "struggling"
    # precision of 0.12 sounds poor in isolation; against a base rate of 0.114
    # it means the prediction carries almost no information at all. This is
    # the single most important line in the output.
    print(f"\n{'=' * 78}")
    print("BASE RATES - precision must be read against these")
    print("=" * 78)
    base = {}
    for split in ("validation", "test"):
        base[split] = float((labels[split] == STRUGGLING).mean())
        print(f"  {split:<12} struggling is {base[split]:.3f} of all windows "
              f"({int((labels[split] == STRUGGLING).sum())} of {len(labels[split])})")
    print("\n  A struggling precision at or below the base rate means the "
          "prediction is\n  no more informative than flagging windows at random.")

    # Where each split would put the threshold if macro F1 were the only
    # criterion. If these disagree, the choice is not stable.
    print(f"\n{'=' * 78}")
    print("BEST THRESHOLD BY MACRO F1, PER SPLIT")
    print("=" * 78)
    best = {}
    for split in ("validation", "test"):
        best[split] = max(curves[split], key=lambda r: r["macro_f1"])
        argmax_f1 = metrics_at(probabilities[split], labels[split])["macro_f1"]
        print(f"  {split:<12} tau={best[split]['tau']:.2f}  "
              f"macro F1 {best[split]['macro_f1']:.3f}  "
              f"(argmax gives {argmax_f1:.3f})")
    if abs(best["validation"]["tau"] - best["test"]["tau"]) > 0.03:
        print("\n  The two splits disagree about the best threshold. Treat any "
              "single\n  chosen value as weakly supported.")

    comparisons = [("argmax", None), (f"tau={nearest:.2f} (Bayes)", nearest),
                   (f"tau={best['validation']['tau']:.2f} (best val F1)",
                    best["validation"]["tau"])]

    print(f"\n{'=' * 78}")
    print("CANDIDATE OPERATING POINTS")
    print("=" * 78)
    print(f"{'rule':<26}{'split':<12}{'strug R':>9}{'strug P':>9}"
          f"{'macro F1':>10}{'flag rate':>11}")
    print("-" * 78)
    for name, tau in comparisons:
        for split in ("validation", "test"):
            m = metrics_at(probabilities[split], labels[split], tau)
            flag = "  <-- flags most of the session" if m["flag_rate"] > 0.5 else ""
            print(f"{name:<26}{split:<12}{m['struggling_recall']:>9.3f}"
                  f"{m['struggling_precision']:>9.3f}{m['macro_f1']:>10.3f}"
                  f"{m['flag_rate']:>11.3f}{flag}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
