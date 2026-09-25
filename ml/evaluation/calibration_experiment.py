"""
Test whether per-subject calibration fixes the generalisation failure.

The finding this responds to
----------------------------
`subject_analysis.py` showed the production model produces zero correct
Struggling detections for 13 of the 19 test subjects who genuinely struggle,
while firing on 79% and 54% of two other subjects' clips. Measured per
feature, between-subject variation exceeds focused-vs-struggling separation by
2.2x to 22.7x. The model followed identity because that is where the variance
was.

Meanwhile the production system already calibrates per user
(`backend/app/engagement/calibration.py`) - but the model was trained on
uncalibrated features. So identity dominated training, and inference then
hands the model a distribution it never saw.

This script tests the obvious consequence: centre each subject on their own
baseline *during training too*, and retrain.

Faithfulness to production
--------------------------
Production does not subtract a subject's overall mean. It subtracts an offset
measured during a calibration phase, where the learner sits looking normally
at the screen - i.e. a focused baseline - and re-centres them on DAiSEE's
focused reference:

    offset     = user_focused_mean - daisee_focused_reference
    calibrated = raw - offset
               = raw - user_focused_mean + daisee_focused_reference

This reproduces that exactly, using each subject's own focused clips as the
stand-in for their calibration session. Using a subject's *overall* mean
instead would leak label information, because their struggling clips would
shift their own baseline.

Why both arms are retrained
---------------------------
The model card admits only one training run was done per configuration, so the
existing numbers cannot be separated from run-to-run variance. Comparing new
calibrated runs against that single old run would repeat the mistake. Both
arms are therefore retrained here, across the same seeds, and reported with
their spread.

Usage
-----
    python -m ml.evaluation.calibration_experiment --data-dir DIR [--seeds 3]
"""

import argparse
import json
import os
import sys

import numpy as np

FEATURE_NAMES = ["gaze_x", "gaze_y", "blink_rate", "pitch", "yaw",
                 "roll", "eye_openness", "brow_raise", "inter_brow"]
FOCUSED, DRIFTING, STRUGGLING = 0, 1, 2
SUBJECT_ID_LENGTH = 6

# Recovered from the original notebook (see myplanlog 3.8) so the two arms
# differ only in whether the features are per-subject centred.
EPOCHS = 50
BATCH_SIZE = 32
LEARNING_RATE = 0.0005
OVERSAMPLE_TARGETS = {DRIFTING: 2500, STRUGGLING: 2500}
OVERSAMPLE_NOISE_STD = 0.05
EARLY_STOP_PATIENCE = 7

SPLITS = {
    "train": ("Train_9features.json", "X_train_9f.npy", "y_train_9f.npy"),
    "validation": ("Validation_9features.json", "X_val_9f.npy", "y_val_9f.npy"),
    "test": ("Test_9features.json", "X_test_9f.npy", "y_test_9f.npy"),
}


def load_split(data_dir, split):
    json_name, x_name, y_name = SPLITS[split]
    with open(os.path.join(data_dir, json_name)) as handle:
        records = json.load(handle)
    clips = [c for c, d in records.items() if d.get("state") is not None]
    X = np.load(os.path.join(data_dir, x_name))
    y = np.load(os.path.join(data_dir, y_name))
    if len(clips) != len(y):
        raise SystemExit(f"{split}: {len(clips)} clips vs {len(y)} rows - mapping broken")
    subjects = np.array([c[:SUBJECT_ID_LENGTH] for c in clips])
    return X, y, subjects


def centre_per_subject(X, y, subjects, global_focused_mean,
                       holdout_baseline=False, seed=0):
    """
    Subtract each subject's own focused-clip mean, re-centre on the global one.

    `holdout_baseline` controls a real methodological difference:

      False - the baseline is the mean of ALL the subject's focused clips,
              including ones later evaluated. Struggling clips never enter a
              baseline, so Struggling detection is unaffected, but focused
              clips partly normalise themselves, which can flatter Focused
              recall and therefore macro F1.

      True  - half the subject's focused clips are reserved for the baseline
              and excluded from evaluation. This matches production more
              closely: a learner calibrates first, then studies, so the
              calibration data is not part of what gets classified.

    Returns (centred X, keep mask, fallback count). The mask is all-True
    unless baseline clips were held out.

    Falls back to a subject's overall mean when they have no focused clips at
    all, and reports how often - a weaker stand-in, worth surfacing rather
    than hiding.
    """
    rng = np.random.default_rng(seed)
    centred = X.copy()
    keep = np.ones(len(y), dtype=bool)
    fallbacks = 0

    for subject in np.unique(subjects):
        rows = np.where(subjects == subject)[0]
        focused = rows[y[rows] == FOCUSED]

        if len(focused) == 0:
            baseline_rows = rows
            fallbacks += 1
        elif holdout_baseline and len(focused) >= 2:
            shuffled = rng.permutation(focused)
            baseline_rows = shuffled[: len(shuffled) // 2]
            keep[baseline_rows] = False        # never evaluated
        else:
            baseline_rows = focused

        baseline = X[baseline_rows].reshape(-1, X.shape[-1]).mean(axis=0)
        centred[rows] = X[rows] - baseline + global_focused_mean

    return centred, keep, fallbacks


def standardise_per_subject(X, y, subjects, global_focused_mean,
                            global_focused_std, holdout_baseline=False, seed=0):
    """
    Like centre_per_subject, but also divides by the subject's own spread.

    Centring removes a subject's offset; it does not remove differences in how
    much a subject's features MOVE. Two learners can share a mean brow_raise
    while one has twice the range. If that is also identity rather than
    behaviour, scaling should help on top of centring.

    Production does not currently do this - calibration.py stores an offset
    only - so a win here would be an argument for extending it to a scale as
    well, not just a training change.
    """
    rng = np.random.default_rng(seed)
    out = X.copy()
    keep = np.ones(len(y), dtype=bool)
    fallbacks = 0

    for subject in np.unique(subjects):
        rows = np.where(subjects == subject)[0]
        focused = rows[y[rows] == FOCUSED]

        if len(focused) == 0:
            baseline_rows = rows
            fallbacks += 1
        elif holdout_baseline and len(focused) >= 2:
            shuffled = rng.permutation(focused)
            baseline_rows = shuffled[: len(shuffled) // 2]
            keep[baseline_rows] = False
        else:
            baseline_rows = focused

        flat = X[baseline_rows].reshape(-1, X.shape[-1])
        mean = flat.mean(axis=0)
        # Guard against a subject with no variation in some feature.
        std = np.where(flat.std(axis=0) < 1e-8, 1.0, flat.std(axis=0))
        out[rows] = (X[rows] - mean) / std * global_focused_std + global_focused_mean

    return out, keep, fallbacks


def focal_loss(gamma=2.0):
    """
    Class-balanced focal loss, as an alternative to the oversampling already used.

    The literature reviewed in myplanlog 3.3 ranks focal loss above plain
    class weighting under severe imbalance, because it down-weights examples
    the model already gets right instead of relying on a hand-picked weight
    ratio. The original work used noise-augmented oversampling instead; this
    tests the other branch on the same split.
    """
    import tensorflow as tf

    def loss(y_true, y_pred):
        y_true = tf.cast(tf.reshape(y_true, [-1]), tf.int32)
        probs = tf.clip_by_value(y_pred, 1e-7, 1.0 - 1e-7)
        picked = tf.gather(probs, y_true, batch_dims=1)
        return -tf.reduce_mean(tf.pow(1.0 - picked, gamma) * tf.math.log(picked))

    return loss


def oversample(X, y, seed):
    """The notebook's oversampling, unchanged, so the arms stay comparable."""
    rng = np.random.default_rng(seed)
    X_parts, y_parts = [X], [y]
    for label, target in OVERSAMPLE_TARGETS.items():
        idx = np.where(y == label)[0]
        if len(idx) >= target:
            continue
        picked = rng.choice(idx, size=target - len(idx), replace=True)
        noisy = X[picked] + rng.normal(0, OVERSAMPLE_NOISE_STD, X[picked].shape)
        X_parts.append(noisy)
        y_parts.append(np.full(target - len(idx), label))
    X_all = np.concatenate(X_parts)
    y_all = np.concatenate(y_parts)
    order = rng.permutation(len(y_all))
    return X_all[order], y_all[order]


def build_model(seed, use_focal=False):
    import tensorflow as tf
    from tensorflow.keras import layers, models

    tf.keras.utils.set_random_seed(seed)
    model = models.Sequential([
        layers.Input(shape=(10, len(FEATURE_NAMES))),
        layers.Masking(mask_value=0.0),
        layers.LSTM(64, return_sequences=True),
        layers.Dropout(0.3),
        layers.LSTM(32),
        layers.Dropout(0.3),
        layers.Dense(16, activation="relu"),
        layers.Dense(3, activation="softmax"),
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=LEARNING_RATE),
        loss=focal_loss() if use_focal else "sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )
    return model


def macro_recall_callback(X_val, y_val):
    import tensorflow as tf
    from sklearn.metrics import recall_score

    class MacroRecall(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            preds = self.model.predict(X_val, verbose=0).argmax(axis=1)
            logs["val_macro_recall"] = recall_score(
                y_val, preds, average="macro", zero_division=0
            )

    return MacroRecall()


def train_once(X_tr, y_tr, X_val, y_val, seed, use_focal=False):
    import tensorflow as tf

    model = build_model(seed, use_focal=use_focal)
    # The callback that COMPUTES val_macro_recall must come first, or the two
    # that consume it cannot see it. The original notebook got this wrong in
    # one run (see myplanlog 3.8).
    callbacks = [
        macro_recall_callback(X_val, y_val),
        tf.keras.callbacks.EarlyStopping(
            monitor="val_macro_recall", mode="max",
            patience=EARLY_STOP_PATIENCE, restore_best_weights=True,
        ),
    ]
    model.fit(X_tr, y_tr, validation_data=(X_val, y_val),
              epochs=EPOCHS, batch_size=BATCH_SIZE,
              callbacks=callbacks, verbose=0)
    return model


def score(model, X, y):
    from sklearn.metrics import f1_score, precision_score, recall_score

    preds = model.predict(X, verbose=0).argmax(axis=1)
    base = float((y == STRUGGLING).mean())
    precision = precision_score(y, preds, average=None, zero_division=0,
                                labels=[0, 1, 2])[STRUGGLING]
    return {
        "macro_f1": f1_score(y, preds, average="macro", zero_division=0),
        "strug_recall": recall_score(y, preds, average=None, zero_division=0,
                                     labels=[0, 1, 2])[STRUGGLING],
        "strug_precision": precision,
        "lift": precision / base if base else float("nan"),
        "flag_rate": float((preds == STRUGGLING).mean()),
    }


def subjects_detected(model, X, y, subjects):
    """How many struggling subjects the model gets at least one hit on."""
    preds = model.predict(X, verbose=0).argmax(axis=1)
    hit = total = 0
    for subject in np.unique(subjects):
        rows = subjects == subject
        if (y[rows] == STRUGGLING).sum() == 0:
            continue
        total += 1
        if ((preds[rows] == STRUGGLING) & (y[rows] == STRUGGLING)).sum() > 0:
            hit += 1
    return hit, total



def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument(
        "--holdout-baseline",
        action="store_true",
        help="Reserve half of each subject's focused clips for computing their "
             "baseline and exclude those clips from evaluation in ALL arms. "
             "Closer to production, where a learner calibrates before studying "
             "rather than being scored on their own calibration data.",
    )
    parser.add_argument(
        "--arms",
        default="uncalibrated,centred",
        help="Comma-separated: uncalibrated, centred, standardised, "
             "focal, centred+focal",
    )
    args = parser.parse_args(argv)

    from sklearn.preprocessing import StandardScaler

    data = {s: load_split(args.data_dir, s) for s in SPLITS}
    X_tr, y_tr, subj_tr = data["train"]

    # Global focused statistics, from TRAIN only - the same quantity
    # focused_reference_means.json holds for production.
    focused_flat = X_tr[y_tr == FOCUSED].reshape(-1, X_tr.shape[-1])
    global_focused_mean = focused_flat.mean(axis=0)
    global_focused_std = np.where(focused_flat.std(axis=0) < 1e-8, 1.0,
                                  focused_flat.std(axis=0))

    # One mask, computed once, applied to every arm - otherwise the arms would
    # be scored on different clips and the comparison would be meaningless.
    mask = {}
    prepared_centred, prepared_std = {}, {}
    for s in SPLITS:
        Xs, ys, subs = data[s]
        prepared_centred[s], mask[s], fb = centre_per_subject(
            Xs, ys, subs, global_focused_mean,
            holdout_baseline=args.holdout_baseline)
        prepared_std[s], _, _ = standardise_per_subject(
            Xs, ys, subs, global_focused_mean, global_focused_std,
            holdout_baseline=args.holdout_baseline)
        if fb:
            print(f"  note: {s} had {fb} subject(s) with no focused clips; "
                  f"used their overall mean")
        if args.holdout_baseline and (~mask[s]).sum():
            print(f"  note: {s} reserved {(~mask[s]).sum()} focused clips for "
                  f"baselines; excluded from evaluation in ALL arms")

    raw = {s: data[s][0] for s in SPLITS}
    ARMS = {
        "uncalibrated":   (raw, False),
        "centred":        (prepared_centred, False),
        "standardised":   (prepared_std, False),
        "focal":          (raw, True),
        "centred+focal":  (prepared_centred, True),
    }
    chosen = [a.strip() for a in args.arms.split(",") if a.strip()]
    unknown = [a for a in chosen if a not in ARMS]
    if unknown:
        raise SystemExit(f"unknown arm(s): {unknown}. Known: {list(ARMS)}")

    print(f"\ntrain {len(y_tr)} clips / {len(np.unique(subj_tr))} subjects, "
          f"{args.seeds} seed(s) x {len(chosen)} arm(s)"
          f"{' , baseline clips held out' if args.holdout_baseline else ''}\n")

    results, coverage = {}, {}
    for arm in chosen:
        prepared, use_focal = ARMS[arm]
        scaler = StandardScaler().fit(
            prepared["train"].reshape(-1, len(FEATURE_NAMES)))

        def norm(X):
            return scaler.transform(X.reshape(-1, X.shape[-1])).reshape(X.shape)

        Xtr_n, Xval_n, Xte_n = (norm(prepared[s])
                                for s in ("train", "validation", "test"))
        mv, mt = mask["validation"], mask["test"]
        y_val, y_te, subj_te = data["validation"][1], data["test"][1], data["test"][2]

        results[arm], coverage[arm] = [], []
        for seed in range(args.seeds):
            # Focal loss replaces oversampling rather than stacking on it:
            # doing both would address the same imbalance twice and make the
            # comparison uninterpretable.
            if use_focal:
                Xb, yb = Xtr_n, y_tr
            else:
                Xb, yb = oversample(Xtr_n, y_tr, seed)
            model = train_once(Xb, yb, Xval_n, y_val, seed, use_focal=use_focal)
            results[arm].append({
                "validation": score(model, Xval_n[mv], y_val[mv]),
                "test": score(model, Xte_n[mt], y_te[mt]),
            })
            coverage[arm].append(
                subjects_detected(model, Xte_n[mt], y_te[mt], subj_te[mt]))
            t = results[arm][-1]["test"]
            print(f"  {arm:<16} seed {seed}: test macro F1 {t['macro_f1']:.3f}  "
                  f"lift {t['lift']:.2f}x  "
                  f"subjects {coverage[arm][-1][0]}/{coverage[arm][-1][1]}")

    print(f"\n{'=' * 82}")
    print(f"RESULT - mean +/- sd over {args.seeds} seed(s)")
    print("=" * 82)
    print(f"{'arm':<18}{'split':<12}{'macro F1':>14}{'strug R':>13}"
          f"{'lift':>9}{'flag rate':>11}")
    print("-" * 82)
    for arm in chosen:
        for split in ("validation", "test"):
            v = {k: np.array([r[split][k] for r in results[arm]])
                 for k in ("macro_f1", "strug_recall", "lift", "flag_rate")}
            print(f"{arm:<18}{split:<12}"
                  f"{v['macro_f1'].mean():>9.3f}+-{v['macro_f1'].std():<4.2f}"
                  f"{v['strug_recall'].mean():>9.3f}+-{v['strug_recall'].std():<4.2f}"
                  f"{v['lift'].mean():>8.2f}x{v['flag_rate'].mean():>11.3f}")
        print()

    print("=" * 82)
    print("SUBJECT COVERAGE ON TEST - struggling subjects with at least one hit")
    print("=" * 82)
    total = coverage[chosen[0]][0][1]
    for arm in chosen:
        hits = np.array([h for h, _ in coverage[arm]])
        print(f"  {arm:<18}{hits.mean():>5.1f} +- {hits.std():.1f} of {total}"
              f"   (range {hits.min()}-{hits.max()})")
    print("\n  This is the metric that decides it. Recall can be bought by")
    print("  flagging more windows; covering more PEOPLE cannot. Read the")
    print("  range: overlapping ranges mean the difference is not established.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
