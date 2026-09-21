"""
Can the calibrated model's threshold be lowered to buy REAL Struggling recall?

Why this is worth re-asking
---------------------------
`threshold_sweep.py` found that lowering the Struggling threshold on the
*production* model bought nothing: Struggling precision on test was already
below the class base rate (0.80x), so every extra detection the lower
threshold produced was essentially random. There was no signal to re-weight.

`calibration_experiment.py` then showed why - the model had learned faces
rather than behaviour - and that per-subject centring fixes a large part of
it: subject coverage rose from 5.5 to 9.9 of 19 test subjects, p < 0.01 across
two independent 10-seed runs.

But that came with a real cost: **Struggling recall went DOWN**, 0.142 to
0.121. The calibrated model spreads its detections across more people while
making fewer of them. Coverage improved; recall did not.

So the question this script asks is the obvious follow-up: now that the
calibrated model demonstrably carries signal on unseen subjects, does lowering
its threshold add *correct* detections rather than noise? If it does, recall
and coverage can improve together instead of trading off.

What it reports
---------------
At each threshold, for the calibrated model:

  recall     - the number the earlier work lost and this is trying to recover
  precision  - against the base rate, so "more detections" cannot masquerade
               as "better detections"
  coverage   - subjects reached, so a recall gain concentrated on two faces
               is visible as such rather than counted as progress
  flag rate  - what the policy would actually cost in interruptions

Threshold is chosen on validation and reported on test, as before.

Usage
-----
    python -m ml.evaluation.calibrated_threshold --data-dir DIR [--seeds 5]
"""

import argparse
import sys

import numpy as np

from ml.evaluation.calibration_experiment import (
    FEATURE_NAMES,
    FOCUSED,
    STRUGGLING,
    SPLITS,
    centre_per_subject,
    load_split,
    oversample,
    train_once,
)

THRESHOLDS = np.round(np.arange(0.50, 0.09, -0.02), 2)


def predict_with_threshold(probabilities, tau):
    others = probabilities.copy()
    others[:, STRUGGLING] = -np.inf
    fallback = others.argmax(axis=1)
    return np.where(probabilities[:, STRUGGLING] >= tau, STRUGGLING, fallback)


def measure(probabilities, y, subjects, tau=None):
    from sklearn.metrics import f1_score, precision_score, recall_score

    preds = (probabilities.argmax(axis=1) if tau is None
             else predict_with_threshold(probabilities, tau))

    base = float((y == STRUGGLING).mean())
    precision = precision_score(y, preds, average=None, zero_division=0,
                                labels=[0, 1, 2])[STRUGGLING]

    covered = total = 0
    for subject in np.unique(subjects):
        rows = subjects == subject
        if (y[rows] == STRUGGLING).sum() == 0:
            continue
        total += 1
        if ((preds[rows] == STRUGGLING) & (y[rows] == STRUGGLING)).sum() > 0:
            covered += 1

    return {
        "recall": recall_score(y, preds, average=None, zero_division=0,
                               labels=[0, 1, 2])[STRUGGLING],
        "precision": precision,
        "lift": precision / base if base else float("nan"),
        "macro_f1": f1_score(y, preds, average="macro", zero_division=0),
        "coverage": covered,
        "subjects": total,
        "flag_rate": float((preds == STRUGGLING).mean()),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args(argv)

    from sklearn.preprocessing import StandardScaler

    data = {s: load_split(args.data_dir, s) for s in SPLITS}
    X_tr, y_tr, _ = data["train"]
    focused_flat = X_tr[y_tr == FOCUSED].reshape(-1, X_tr.shape[-1])
    global_focused_mean = focused_flat.mean(axis=0)

    prepared, mask = {}, {}
    for s in SPLITS:
        Xs, ys, subs = data[s]
        prepared[s], mask[s], _ = centre_per_subject(
            Xs, ys, subs, global_focused_mean, holdout_baseline=True)

    scaler = StandardScaler().fit(prepared["train"].reshape(-1, len(FEATURE_NAMES)))

    def norm(X):
        return scaler.transform(X.reshape(-1, X.shape[-1])).reshape(X.shape)

    Xtr_n, Xval_n, Xte_n = (norm(prepared[s]) for s in ("train", "validation", "test"))
    mv, mt = mask["validation"], mask["test"]
    y_val, y_te, subj_te = data["validation"][1], data["test"][1], data["test"][2]
    subj_val = data["validation"][2]

    print(f"\ntraining {args.seeds} calibrated model(s)\n")
    val_probs, test_probs = [], []
    for seed in range(args.seeds):
        Xb, yb = oversample(Xtr_n, y_tr, seed)
        model = train_once(Xb, yb, Xval_n, y_val, seed)
        val_probs.append(model.predict(Xval_n[mv], verbose=0))
        test_probs.append(model.predict(Xte_n[mt], verbose=0))
        print(f"  seed {seed} done")

    yv, sv = y_val[mv], subj_val[mv]
    yt, st = y_te[mt], subj_te[mt]

    def averaged(probs_list, y, subjects, tau):
        runs = [measure(p, y, subjects, tau) for p in probs_list]
        return {k: np.mean([r[k] for r in runs]) for k in runs[0]}

    print(f"\n{'=' * 84}")
    print("VALIDATION - threshold chosen here")
    print("=" * 84)
    print(f"{'tau':>7}{'recall':>10}{'precision':>12}{'lift':>8}"
          f"{'coverage':>11}{'macro F1':>11}{'flag rate':>11}")
    print("-" * 84)

    argmax_v = averaged(val_probs, yv, sv, None)
    print(f"{'argmax':>7}{argmax_v['recall']:>10.3f}{argmax_v['precision']:>12.3f}"
          f"{argmax_v['lift']:>8.2f}x{argmax_v['coverage']:>10.1f}"
          f"{argmax_v['macro_f1']:>11.3f}{argmax_v['flag_rate']:>11.3f}")

    val_rows = {}
    for tau in THRESHOLDS:
        m = averaged(val_probs, yv, sv, tau)
        val_rows[tau] = m
        print(f"{tau:>7.2f}{m['recall']:>10.3f}{m['precision']:>12.3f}"
              f"{m['lift']:>8.2f}x{m['coverage']:>10.1f}"
              f"{m['macro_f1']:>11.3f}{m['flag_rate']:>11.3f}")

    # Selection needs two constraints, not one.
    #
    # lift > 1.0 alone is far too weak: on the calibrated model lift stays at
    # 1.00-1.01x all the way down to tau=0.10, so "maximise recall subject to
    # lift > 1.0" picks 0.10 and flags 94% of windows. That is the same
    # failure the Bayes threshold produced in threshold_sweep.py - a correct
    # rule applied without a margin.
    #
    # LIFT_FLOOR demands a real margin over chance. FLAG_CEILING encodes scope
    # 6.4's "infrequent targeted support": interrupting more than a quarter of
    # windows is not infrequent by any reading.
    LIFT_FLOOR, FLAG_CEILING = 1.15, 0.25
    usable = {t: m for t, m in val_rows.items()
              if m["lift"] >= LIFT_FLOOR and m["flag_rate"] <= FLAG_CEILING}
    chosen = max(usable, key=lambda t: usable[t]["recall"]) if usable else None
    print(f"\nselection: lift >= {LIFT_FLOOR}, flag rate <= {FLAG_CEILING}, "
          f"then maximise recall"
          + (f" -> tau={chosen:.2f}" if chosen else " -> nothing qualifies"))

    print(f"\n{'=' * 84}")
    print("TEST - held out, reported only")
    print("=" * 84)
    argmax_t = averaged(test_probs, yt, st, None)
    print(f"{'rule':<22}{'recall':>10}{'precision':>12}{'lift':>8}"
          f"{'coverage':>11}{'flag rate':>11}")
    print("-" * 84)
    print(f"{'argmax (calibrated)':<22}{argmax_t['recall']:>10.3f}"
          f"{argmax_t['precision']:>12.3f}{argmax_t['lift']:>8.2f}x"
          f"{argmax_t['coverage']:>10.1f}{argmax_t['flag_rate']:>11.3f}")

    if chosen is None:
        print("\nNo threshold on validation kept precision above the base rate.")
        print("Lowering it would buy recall indistinguishable from noise.")
        return 0

    for tau in (0.40, 0.36, 0.34, 0.32, 0.30):
        r = averaged(test_probs, yt, st, tau)
        star = "  <- selected" if chosen is not None and abs(tau - chosen) < 1e-9 else ""
        print(f"{'tau=' + f'{tau:.2f}':<22}{r['recall']:>10.3f}"
              f"{r['precision']:>12.3f}{r['lift']:>8.2f}x"
              f"{r['coverage']:>10.1f}{r['flag_rate']:>11.3f}{star}")
    m = averaged(test_probs, yt, st, chosen)

    print(f"\n{'=' * 84}")
    print("DID RECALL ACTUALLY IMPROVE, OR JUST SPREAD?")
    print("=" * 84)
    print(f"  uncalibrated argmax (from calibration_experiment): "
          f"recall 0.142, coverage 5.5")
    print(f"  calibrated   argmax: recall {argmax_t['recall']:.3f}, "
          f"coverage {argmax_t['coverage']:.1f}")
    print(f"  calibrated   tau={chosen:.2f}: recall {m['recall']:.3f}, "
          f"coverage {m['coverage']:.1f}, lift {m['lift']:.2f}x")
    print("\n  A real improvement needs recall ABOVE 0.142 with lift still")
    print("  above 1.0 and coverage still above 5.5. Anything less is a trade,")
    print("  not a gain.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
