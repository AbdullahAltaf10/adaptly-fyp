# Model Card — Adaptly Engagement Classifier

## What it is

An LSTM that reads 10 seconds of facial measurements and reports one of three
engagement states.

| | |
|---|---|
| Input shape | `(10, 9)` — 10 one-second windows, 9 features each |
| Output | 3 classes with a confidence |
| Class mapping | `0 → focused`, `1 → drifting`, `2 → struggling` |
| Framework | TensorFlow / Keras |
| Artifacts | `ml/artifacts/` — hashes in `MANIFEST.json` |

### Feature order — load-bearing

```
[gaze_x, gaze_y, blink_rate, pitch, yaw, roll, eye_openness, brow_raise, inter_brow]
```

This order must match everywhere: training, `ml/inference/features.py`,
`focused_reference_means.json`, and `MANIFEST.json`. Reordering produces
confident nonsense rather than an error.

## Performance — the honest numbers

| Metric | Test | Validation |
|---|---|---|
| Macro F1 | 0.351 | 0.387 |
| Focused recall | 77% | 74% |
| Drifting recall | 30% | 27% |
| **Struggling recall** | **10%** | **18%** |

**Do not quote raw accuracy for this model.** A classifier that always guessed
"focused" scores **84.7%** on the same test set. Accuracy measures the class
imbalance, not the model. Judge it on per-class recall and macro F1.

For context: the original DAiSEE paper benchmarked at 51.07%, and published
deep-learning results on this dataset commonly fall in the 46–58% range.

Train, test and validation splits contain **zero subject overlap** (verified),
so these figures reflect generalisation to genuinely unseen people.

## Training data

**DAiSEE** — 9,068 video clips, ~2.7M frames, from IIT Gandhinagar. Labels cover
Boredom, Engagement, Confusion and Frustration on a four-point scale.

Mapped to three states:

```
confusion >= 2 or frustration >= 2   ->  struggling
engagement <= 1 and boredom >= 2     ->  drifting
engagement >= 2                      ->  focused
otherwise                            ->  drifting
```

### Known dataset limitations

- **Severely imbalanced.** Published analysis puts low and very-low engagement
  at roughly 0.7% and 5.1% of the data. Systems trained on it are described in
  the literature as achieving "deceptively high benchmark accuracy by defaulting
  to the majority class."
- **Demographically narrow.** 80% male, predominantly Asian, recorded in
  controlled settings. Generalisation to other populations and to home
  environments is **unvalidated**.
- **Crowdsourced labels**, whose quality has been questioned in several
  published studies.

## Known limitations of this implementation

### `blink_rate` is not a blink rate

It holds the **same eye-aspect-ratio value as `eye_openness`** — the two are
byte-identical in `focused_reference_means.json` (both `0.36906…`).

A blink lasts 100–400 ms; frames are sampled once per second. A genuine blink
rate cannot be measured from this input at all. Correcting it needs both a
higher sampling rate and a retrain, since the model was fitted on the duplicated
value.

### Head pose is not `solvePnP` for the model

The scope document specifies `solvePnP`, and it **is** implemented
(`ml/inference/head_pose.py`) — but it is used only by the rule-based detectors.
The model and scaler were fitted on a simplified geometric estimate
(`(nose_y − chin_y) × 100`), which lives on a completely different numeric
scale. Feeding real degrees to the model would supply out-of-distribution input.
Switching requires recomputing features across the dataset and retraining.

**Consequence worth knowing:** because the simplified estimate uses the chin,
**opening your mouth registers as head movement**. Mouth-open reliably produces
a "struggling" reading — but for that reason, not because confusion was
detected. It should not be presented as confusion detection.

### 9 features, not the 7 specified

The scope document lists 7. Trained on those alone, Struggling recall was about
**1%** — the model essentially never detected a struggling learner, which is the
most product-critical signal because it triggers intervention.

All 7 specified features are eye- and head-based, and confusion shows in the
eyebrows. Adding `brow_raise` and `inter_brow` raised Struggling recall from
~1% to 10–18%.

An 11-feature version adding mouth features was tested and **rejected**: better
on the test set, but inconsistent between test and validation (10% vs 6%), where
the 9-feature version was stable (10% vs 18%). Chosen for consistency, not
headline numbers.

### 10-second window, not 30

DAiSEE clips are 10 seconds. A true 30-second window would mean concatenating
three separate clips, teaching the model artificial joins as if they were
behaviour. The stability the 30-second window was intended to provide is
delivered by the smoothing layer instead.

## Training provenance — partially unavailable

**Recorded:** the dataset, preprocessing approach (MediaPipe landmark extraction
across 8,570 clips with disconnect-safe checkpointing), feature engineering and
its justification, the label mapping, the subject-disjoint split, and the
comparison against the 7- and 11-feature variants.

**Not recorded, and should be treated as unavailable:**

- Exact hyperparameters — layer sizes, learning rate, batch size, epochs
- Random seeds
- The training notebook as executed
- Per-epoch training curves

**Only one training run was performed per configuration.** The 9-feature
advantage has therefore **not** been shown to exceed run-to-run variation.
Repeated runs or k-fold cross-validation would be needed to claim that.

This is a genuine reproducibility gap. Anyone retraining should treat the
current numbers as a baseline to reproduce, not as an established result.

## Rule-based states

Two of the five states the product reports do not come from the model:

| State | Source | Why |
|---|---|---|
| `fatigued` | rule | DAiSEE has no fatigue dimension |
| `recovered` | rule | A comparison across time; a single clip cannot express it |

`source` on each engagement event records which produced it — `lstm`, `rule`, or
`hybrid`.

**Fatigued** fires when median eye-openness sits below `0.369 − 1.0 × 0.068 =
0.301` for ≥80% of the last 45 windows, and is grounded in DAiSEE's measured
Focused distribution. Windows where the learner is looking down are skipped,
because looking down lowers eye-openness identically to tiredness.

**Deep Thinking** thresholds are **estimates, not measurements**. There is no
published reference distribution for "stillness", so the constants were reasoned
from feature scales. Treat a firing as a hypothesis.

## What has not been validated on real people

- **Recovered** — unit-tested, never observed firing in a live session
- **Deep Thinking** — same
- Everything above is measured against DAiSEE, not against this system's own
  users. No evaluation on the target population has been carried out.

## Verifying the artifacts

```python
from ml.inference.model import verify_artifacts
verify_artifacts()   # {filename: True/False}
```

A model or scaler that changes silently produces plausible but wrong output,
which is far harder to notice than a crash.
