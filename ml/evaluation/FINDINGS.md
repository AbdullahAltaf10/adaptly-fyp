# Module 3 evaluation — findings

Written up for whoever reviews this branch. It records what was measured, what
each decision rested on, what was traded away to get it, and what is still
broken. Everything here is reproducible with the scripts in this directory.

Companion to [`README.md`](README.md), which describes what can and cannot be
reproduced. That file was partly wrong and this work corrects it — see §2.

---

## 1. What we started with

Module 3 shipped a trained LSTM and a model card reporting:

| | Test | Validation |
|---|---|---|
| Macro F1 | 0.351 | 0.387 |
| Focused recall | 77% | 74% |
| Drifting recall | 30% | 27% |
| Struggling recall | **10%** | **18%** |

Two things were true about those numbers. They were honest — the model card is
careful, warns against quoting accuracy, and states its own limitations. And
they were **unverifiable**: the notebook that produced them was not in the
repo, so nothing here could regenerate or re-check them.

Struggling is the class everything downstream depends on. Module 4's
intervention trigger, Module 8's analytics and the project's central claim all
rest on it, and it was the weakest of the three.

---

## 2. First correction: the "lost" training details were not lost

`README.md` in this directory states that hyperparameters, seeds and the
training notebook are unavailable, and that "a retrain would be a new model
that happens to resemble this one." That is no longer true.

The original Colab notebook was recovered. From it:

```
epochs        50            batch_size   32          seed  42
optimiser     Adam @ 5e-4   loss         sparse categorical crossentropy
EarlyStopping val_macro_recall, patience 7, restore_best_weights
Checkpoint    val_macro_recall, save_best_only
scaler        StandardScaler, fitted on TRAIN only, flattened to (-1, 9)
label map     confusion>=2 or frustration>=2 -> Struggling
              engagement<=1 and boredom>=2   -> Drifting
              engagement>=2                  -> Focused
              otherwise                      -> Drifting
data source   Kaggle: olgaparfenova/daisee
```

Only the per-epoch curves for the production run are genuinely absent, and
even those are visible in the notebook's own cell outputs.

**Every model card figure was then verified against the notebook's recorded
outputs and reproduced independently by `evaluate.py`.** Macro F1 0.351/0.387,
Struggling recall 0.10/0.18, the 84.7% majority baseline, the ~1% figure for
the 7-feature variant — all exact matches, worst drift 0.004. Subject
disjointness is verified in code in the notebook (empty set intersections).
The fatigue threshold is confirmed as measured from the data, not guessed.

**The model card is trustworthy.** The problem was never accuracy of
reporting; it was that nobody could check it. `evaluate.py` fixes that.

### Also corrected

The model card says the 9-feature variant was chosen over the 11-feature one
because 9f was "stable" (Struggling recall 10% → 18% across splits) while 11f
was "inconsistent" (10% → 6%). Measured properly, 9f's swing is the *larger*
of the two in relative terms; it is simply unstable in the flattering
direction. 11f also had the best test macro F1 of any variant, 0.411 against
0.351, which the summary does not mention. The model card is honest that one
run per configuration establishes nothing — but the wording implies a
confidence the numbers do not support and should be softened.

---

## 3. The core problem: the model learned faces, not behaviour

This is the finding that reframed everything.

### 3.1 Threshold moving bought nothing

The obvious first lever — lower the Struggling decision threshold, trading
precision for recall — does nothing on the shipped model. At the best
validation threshold, test macro F1 goes 0.351 → 0.351 and Struggling recall
0.099 → 0.099.

`threshold_sweep.py` shows why. **Struggling precision on test is 0.091
against a class base rate of 0.114 — 0.80x.** When the shipped model says a
learner is struggling, on unseen data you would do better ignoring it and
picking a window at random. There was no signal to re-weight.

That is a much stronger statement than "recall is 10%". Low recall with decent
precision is a cautious detector. Precision below base rate is close to
nothing.

### 3.2 The variants are mirror images

`compare_variants.py`, measuring precision against base rate:

| variant | split | Struggling precision | base rate | lift |
|---|---|---|---|---|
| 7-feature | test / val | 0.115 / 0.170 | 0.114 / 0.153 | 1.01x / 1.11x |
| **9-feature (production)** | test / val | 0.091 / 0.240 | | **0.80x** / 1.56x |
| **11-feature** | test / val | 0.304 / 0.136 | | **2.67x** / **0.89x** |

9f works on validation and is below chance on test. 11f works on test and is
below chance on validation. **Each works on exactly the split the other fails
on** — the signature of fitting split-specific subjects, not behaviour.

### 3.3 Per-subject scoring

DAiSEE's splits are subject-disjoint, so `subject_analysis.py` scores each
held-out person separately:

| | test | validation |
|---|---|---|
| subjects who actually struggle | 19 | 18 |
| **subjects the model gets ANY correct detection on** | **6** | **8** |
| struggling subjects with zero correct detections | **13** | 10 |

```
subject   clips  true S  pred S  correct
510047       83      28       0        0   <- 28 struggling clips, never fires
826412       84      18       0        0
882654       91      14       0        0
987736       98       9      77        7   <- fires on 79% of this person's clips
500044      119       6      64        2   <- fires on 54% of this person's clips
```

Two subjects generate most of both the true and false positives. For most
people the model never fires at all.

### 3.4 Measured cause

For every feature, how much it varies **between people** against how much it
separates **focused from struggling**:

| feature | ratio |
|---|---|
| gaze_y | **22.7x** |
| brow_raise | **5.9x** |
| yaw / pitch / inter_brow / gaze_x | 3.0–4.4x |
| roll / blink_rate / eye_openness | 2.2–2.5x |

**Every feature carries more identity than signal**, by 2.2x to 22.7x.
`brow_raise` — added specifically to detect confusion — carries almost 6x more
identity than signal. A model trained on raw per-subject values will follow
identity, because that is where the variance is.

---

## 4. The fix, and why it was already half-built

`backend/app/engagement/calibration.py` already computes, at inference:

```
offset     = user_focused_mean - daisee_focused_reference
calibrated = raw - offset
```

**But the model was trained on uncalibrated features** — a single global
scaler, no per-subject step anywhere in the notebook. So:

```
TRAINING    raw per-subject features  ->  global scaler  ->  LSTM
INFERENCE   raw  ->  subtract THIS user's baseline  ->  global scaler  ->  LSTM
```

Identity dominated training, and inference then handed the model a
distribution it had never seen — the same class of train/inference mismatch
the model card already documents for `solvePnP`, which nobody had noticed
applies to calibration too.

`calibration_experiment.py` centres each subject on their own baseline during
training as well, reproducing production's formula faithfully: each DAiSEE
subject's **focused** clips stand in for their calibration session. Their
overall mean is deliberately not used — that would leak, since their
struggling clips would shift the baseline those same clips are measured
against.

### Result

Both arms retrained across the same seeds, because comparing new runs against
the single old run would repeat the mistake the model card admits to.

| arm | run 1 (n=10) | run 2, baseline held out (n=10) |
|---|---|---|
| uncalibrated | 5.5 ± 3.03 (2–10) | 5.5 ± 3.03 (2–10) |
| **per-subject centred** | **9.3 ± 2.36 (6–14)** | **9.9 ± 2.92 (7–15)** |

Mann-Whitney one-sided p = 0.0074 and 0.0097, Cohen d = 1.40 and 1.48.
Replicated, significant, large effect — and it **survives** the holdout fix, so
it was not produced by leakage.

---

## 5. Challenges, and what went wrong on the way

**Two selection rules produced absurd operating points.** The Bayes-optimal
threshold for the cost asymmetry scope 6.4 implies gives tau = 0.11, which
flags 91–95% of windows. Later, "maximise recall subject to lift > 1.0"
selected tau = 0.10, flagging 94%. Both rules are correct; both were applied
without a margin. Selection now requires `lift >= 1.15` **and**
`flag_rate <= 0.25`, the second encoding scope 6.4 rather than leaving
"infrequent" undefined.

**A leakage flaw in the first experiment design.** Production calibrates
*before* studying, so calibration data is not part of what gets classified.
The first version computed each subject's baseline from the same focused clips
it then evaluated. `--holdout-baseline` reserves half of them and excludes
those clips from evaluation **in every arm**, so the comparison stays on
identical clips. Masking only one arm would have changed its evaluation set.

That check earned its keep: **the macro F1 improvement did not survive it.**
Run 1 showed 0.389 vs 0.373 (p = 0.032); run 2 showed 0.388 vs 0.390 —
identical. Only the subject coverage improvement is real.

**An averaged threshold does not transfer to an individual model.** The
multi-seed study suggested tau = 0.40. The exported artifact is more
conservative than the seed average — argmax flag rate 0.051 against roughly
0.100 — so its own threshold had to be re-derived on validation, giving 0.34.
Re-derive it whenever the exported model changes.

**Two things the literature predicted that did not hold here.** Focal loss
replacing the oversampling collapses completely — flag rate 0.000, it never
predicts Struggling at all, despite the literature ranking it above class
weighting under severe imbalance. And per-subject *standardisation* (dividing
by each subject's spread as well as centring) is not significantly better than
baseline (p = 0.10) and significantly worse than plain centring (p = 0.022).

That second negative result is useful: **`calibration.py` storing an offset
only is the correct design.** There is no argument for extending it to a
scale.

---

## 6. Tradeoffs taken

**Coverage was bought at the cost of recall, until it wasn't.** Per-subject
centring alone raised coverage from 5.5 to 9.9 of 19 while Struggling recall
*fell*, 0.142 → 0.121. The model made fewer detections spread across more
people. That is a trade, not a gain, and it was only resolved by the next
step: on the calibrated model, threshold moving works, so recall and coverage
improve together.

**Flag rate is the real price.** At the recommended threshold the exported
model interrupts on 21.4% of windows against the shipped model's 12.3%.
Scope 6.4 asks for "infrequent targeted support". Whether one window in five
qualifies is a **product decision, not an ML one**, and it should be taken
deliberately with these numbers in front of whoever takes it.

**A more conservative threshold was chosen over the one the rule picked.** The
selection rule chose 0.32. On validation its flag rate is 0.246, inside the
ceiling; on test it drifts to 0.271, outside it. 0.34 stays inside on both, at
almost the same benefit.

**The production path was left alone.** `predict()` gains an opt-in
`struggling_threshold` that defaults to `None` — the argmax that has always
shipped. `ml/inference/model.py` still loads the uncalibrated artifacts. All
141 pre-existing tests pass unchanged. Switching is a separate, reviewable
decision and this branch does not take it.

---

## 7. Where we ended up

Test split, exported artifact at its validation-derived threshold of 0.34,
against the shipped model:

| | shipped | **calibrated** |
|---|---|---|
| Struggling recall | 0.099 | **0.276** |
| subject coverage | 6/19 | **15/19** |
| precision lift | **0.80x** (below random) | **1.29x** |
| macro F1 | 0.351 | **0.398** |
| flag rate | 0.123 | 0.214 |

Recall 2.8x, coverage 2.5x, and precision moves from worse-than-random to
meaningfully better than chance.

---

## 8. What is still broken

- **Roughly one struggling learner in five is still never detected.** 15/19 is
  an improvement on 6/19, not a solution.
- **The validation-to-test gap persists.** Precision is higher on validation
  than test throughout. What changed is that lift now stays above 1.0 on test
  instead of falling to 0.80x. The model generalises imperfectly across
  people; it is no longer anti-correlated.
- **One train/test split.** Leave-one-subject-out cross-validation would be a
  substantially stronger basis for every figure here.
- **A per-user rule beats the LSTM.** `brow_rule.py` shows a hand-written
  per-subject brow threshold reaching 12 of 19 subjects at a *lower* flag rate
  than the model's 6 of 19, catching 18 struggling clips the model missed
  entirely — with no training at all. Its precision is at chance (0.99x), so
  it is not a fix either, but it is strong evidence that the per-user
  principle is the right direction and that `furrow.py` deserves the live
  threshold session it has been waiting for.
- **`blink_rate` is still a duplicate of `eye_openness`**, so the model has
  eight distinct inputs, not nine. Unchanged by this work.
- **Nothing has been validated on a real user.** Every figure here is DAiSEE.

---

## 9. Reproducing any of this

```bash
# Requires the preprocessed DAiSEE arrays; see README.md.
python -m ml.evaluation.evaluate              --data-dir DIR   # model card table
python -m ml.evaluation.threshold_sweep       --data-dir DIR   # why it failed before
python -m ml.evaluation.compare_variants      --data-dir DIR   # 7f / 9f / 11f
python -m ml.evaluation.subject_analysis      --data-dir DIR   # per-subject scoring
python -m ml.evaluation.calibration_experiment --data-dir DIR --seeds 10 --holdout-baseline
python -m ml.evaluation.calibrated_threshold  --data-dir DIR   # threshold on calibrated
python -m ml.evaluation.brow_rule             --data-dir DIR   # per-user rule
python -m ml.evaluation.train_calibrated      --data-dir DIR   # export artifacts
```

`backend/tests/test_ml_evaluation.py` guards the harness. Six of its tests need
no data and run on a fresh clone; the rest switch on when `ADAPTLY_EVAL_DATA`
points at the arrays.
