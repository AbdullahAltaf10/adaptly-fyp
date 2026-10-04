# Engagement Model Accuracy — Phase 1: Real Head Pose + Real Blink Rate

## 1. Why this phase, and why only these two

The user reported the live engagement state getting stuck in `drifting` and
never showing `recovered`, and asked for proper research into why, with
"200%" accuracy as the aspiration (acknowledged as unrealistic, treated here
as "meaningfully better than today, honestly measured").

Investigation (this session) found no bug in the live pipeline — smoothing,
recovery detection, and the route wiring are all correct and already
covered by tests. The actual limitation is the model itself, and it is
already honestly documented in `docs/model/model-card.md`:

- Drifting recall: 30% (test) / 27% (validation).
- Struggling recall: 10% (test) / 18% (validation).
- Trained on DAiSEE: 80% male, predominantly one ethnicity, lab-controlled
  lighting/camera. Generalization to this app's real users is explicitly
  **unvalidated**.
- Two features are known-broken rather than measuring what their names
  claim:
  - `blink_rate` is byte-identical to `eye_openness` — not a rate at all,
    because frames are sampled at 1 fps and a blink lasts 100-400ms.
  - Head pose is `(nose_y − chin_y) × 100`, not real 3D pose — chosen only
    because the model was trained on it; real `solvePnP` pose already
    exists (`ml/inference/head_pose.py`) but is used only by the rule-based
    gates (fatigue, deep thinking, furrow), never by the model.

Three further levers exist (glasses robustness, WebGazer/gaze-fusion
changes, combining with a second dataset) and were explicitly deferred by
the user to a later phase — this spec covers only the two the user chose to
go first: **real head pose, real blink rate**, both fixing a feature the
model card already names as broken, both achievable from the existing
DAiSEE dataset alone (no new dataset needed), and both isolating "does
feature quality alone move recall" before adding any other variable.

## 2. What stays exactly the same (deliberately)

To isolate the effect of the two feature changes from every other variable:

- **Architecture**: `LSTM(64, return_sequences=True) → Dropout(0.3) →
  LSTM(32) → Dropout(0.3) → Dense(16, relu) → Dense(3, softmax)` — the exact
  shape that produced `best_model_9f.keras`, confirmed from the original
  training notebook (`sibtain-workspace/Adaptly (2).ipynb`, cell 111).
- **Hyperparameters**: Adam, lr=0.0005, batch_size=32, early stopping on
  `val_macro_recall` (custom callback — not plain `val_accuracy`, which the
  model card explains would just reward the majority class), patience=7.
- **Label mapping, train/val/test split, class balancing**: unchanged —
  same DAiSEE subject-disjoint split, same
  `confusion>=2 or frustration>=2 -> struggling`,
  `engagement<=1 and boredom>=2 -> drifting`, `engagement>=2 -> focused`
  mapping documented in the model card.
- **Feature count and order**: still 9 features, same
  `[gaze_x, gaze_y, blink_rate, pitch, yaw, roll, eye_openness, brow_raise,
  inter_brow]` order (`ml/inference/features.py:FEATURE_NAMES` is
  load-bearing and does not change).
- **10 frames per clip, evenly spaced** for every feature except blink
  detection (see §4) — matches the existing `extract_landmarks_from_video`
  convention (`np.linspace(0, total_frames-1, 10)`), so pitch/yaw/roll,
  gaze, eye-openness and brow features are computed from the exact same
  sampled frames as today, changed only in HOW pitch/yaw/roll are computed.

Only two things change: how `pitch, yaw, roll` are computed, and what
`blink_rate` actually measures.

## 3. Real head pose

`ml/inference/features.py::estimate_head_pose` currently does:

```python
yaw = (nose[0] - (left_eye[0] + right_eye[0]) / 2) * 100
pitch = (nose[1] - chin[1]) * 100
roll = math.degrees(math.atan2(right_eye[1] - left_eye[1], right_eye[0] - left_eye[0]))
```

`ml/inference/head_pose.py::solve_head_pose` already implements real
`cv2.solvePnP` against a 6-point anthropometric face model, already measured
against synthetic ground truth (0.00° error recovering a known 20° tilt,
exact distance invariance), already used in production by the rule-based
gates. Phase 1 makes the **feature-extraction path for training and live
inference** call this instead of the simplified formula.

Consequence worth stating up front (already true today for the rule gates,
now also true for the model): `solve_head_pose` can return `None` when the
geometry is degenerate. The simplified formula never failed. `extract_
features` must decide what a `None` pose means for a frame already headed
into a 10-frame training/inference window — treated as a missing frame
(same handling `validate_landmarks`/the `Masking` layer already gives a
dropped frame), not a crash and not a silent zero.

## 4. Real blink rate

A blink lasts 100-400ms. Today's extraction samples 10 frames across a
~10-second clip — roughly 1 fps — so no sampled frame is reliably able to
catch a blink in progress, and the current code does not try; it just
copies `eye_openness` into the `blink_rate` slot.

**Redefinition, not a true continuous rate:** within each of the 10
one-second windows, sample `BLINK_SUBSAMPLE_COUNT = 5` additional frames
(≈5 fps within that window — enough to have a good chance of catching a
100-400ms closure without requiring a full video-rate re-extraction of
every clip). For each sub-frame, compute eye-aspect-ratio exactly as
`eye_aspect_ratio` already does. A **blink event** is recorded when a
sub-frame's EAR drops below `BLINK_EAR_RATIO * window_max_ear` (threshold
relative to that window's own peak openness, not an absolute value — a
person's resting EAR varies with face geometry and camera distance, the
same reasoning `inter_ocular_distance` normalization already uses
elsewhere in this codebase). `blink_rate` for the window is the blink
event count (0, 1, or rarely 2 — physiologically, more than one blink per
second is uncommon, so this is already close to a true rate at this
timescale, not merely a cruder proxy of one).

`BLINK_EAR_RATIO` is a to-be-chosen constant (starting estimate 0.7,
tuned against a handful of manually-labeled clips before the full
re-extraction run — not claimed as measured until that happens, matching
this codebase's own standard for every other unmeasured threshold).

**Cost this adds:** re-extraction now reads up to 5x more frames per clip
than before (10 anchor frames, each needing up to 5 nearby sub-frames for
blink detection only — pitch/yaw/roll/gaze/eye-openness/brow still use
only the original 10 anchor frames). Across ~8,570 clips this is the
dominant driver of how long re-extraction takes; checkpointing (see §6)
exists because of this.

**Live inference impact:** `useEngagementCapture.js`'s `CAPTURE_INTERVAL_MS
= 1000` (1 fps) is the frontend's own sampling rate, separate from
training-time extraction. Computing a genuine per-window blink rate live
would need the frontend to sample faces at ~5fps too, a frontend capture
change out of scope for this phase — matching the user's own prioritization
to fix retraining features without touching the live protocol first. **This
means Phase 1's retrained model will be trained on a blink_rate the live
system cannot yet supply at inference time.** Flagged here as the one real
tension in doing head-pose and blink-rate together: head pose does not
have this problem (every frame already available at inference carries
what solvePnP needs), blink rate does.

**Decided (user, 2026-10-03):** ship real head pose alone in this phase
(clean win, no training/inference mismatch). Real blink-rate is NOT
abandoned — it is explicitly committed as **Phase 1b**, to be scoped once
the frontend capture-rate question (bump `CAPTURE_INTERVAL_MS` toward
~5fps, vs. a coarser 1fps-derived proxy, vs. something else) is
deliberately decided rather than defaulted. Phase 1b's own spec is where
that decision gets made; this document commits to doing it, not to
skipping it.

Rejected for the record: retraining with real blink-rate now but feeding a
fixed default value at live inference time (still only 1fps there) would
train the model on real variation in that feature and then serve it a
constant — a worse train/serve mismatch than today's "duplicate value" bug,
not a better one.

## 5. Evaluation gate — do not ship a worse model

Phase 1 is "retrain and measure", not "retrain and assume better". Before
any new artifact replaces `ml/artifacts/best_model_9f.keras` /
`scaler_9f.pkl`:

- Run the exact same evaluation the model card already reports (per-class
  recall via `sklearn.metrics.recall_score(..., average=None)`, macro F1,
  confusion matrix) against the **same held-out test split** (subject-
  disjoint, unchanged).
- The new model ships only if Drifting and/or Struggling recall improves
  without Focused recall collapsing (a model that "detects" drifting by
  flagging everything as drifting is not an improvement — same reasoning
  the model card's own "accuracy measures the class imbalance, not the
  model" warning already makes).
- If it is not better, the honest outcome is: document the negative result
  (model card gets a new dated entry either way), keep shipping the
  current artifacts, and treat "real head pose alone is not sufficient"
  as a real, useful finding for Phase 2 planning — not a failure to hide.

## 6. Execution split (this machine cannot run the retrain itself)

This machine has no usable GPU for TensorFlow (confirmed: CUDA 13.1
driver present, but "TensorFlow GPU support is not available on native
Windows for TensorFlow >= 2.11" without WSL2/DirectML) and no way to drive
a Google Colab notebook interactively. The original model was trained on
Colab, mounting the user's Google Drive
(`/content/drive/MyDrive/Adaptly_Engagement_Model/`, containing
`raw_dataset/` — confirmed present via the shared Drive link — and
`processed_features/`).

Split of work:

- **Claude (this repo, locally testable, no dataset needed):**
  - `ml/inference/features.py`: swap `estimate_head_pose` for
    `head_pose.solve_head_pose`, handle its `None` case.
  - A new `blink_events` helper (only if blink-rate is in scope per §4's
    resolution), unit-tested against synthetic EAR sequences (same
    synthetic-ground-truth testing style `head_pose.py` already uses) —
    real accuracy numbers can only come from the actual retrain, but the
    extraction *logic* is fully unit-testable without DAiSEE itself.
  - A new, clean Colab-ready notebook/script (not an edit to the 128-cell
    experimental notebook) that: mounts the same Drive paths, re-extracts
    features for Train/Validation/Test using the updated
    `ml/inference/features.py`, trains with the exact architecture/
    hyperparameters from §2, evaluates per §5, and saves
    `best_model_9f_v2.keras` / `scaler_9f_v2.pkl` plus an updated
    evaluation report — with checkpointing (resumable feature extraction,
    matching the existing notebook's own `load_split_checkpointed`
    pattern, since a crashed Colab runtime losing hours of re-extraction
    would be a real cost here) built in from the start, not bolted on
    after a failure.
  - Once the user has run it and has the resulting files: update
    `ml/artifacts/MANIFEST.json` with new hashes, wire the new artifact in
    behind the same `calibrated`-style opt-in pattern `model.py` already
    uses for the calibrated pair (so this does not silently replace the
    production model for every learner the moment it lands - mirrors this
    session's own Module 6 feature-flag discipline), and update
    `docs/model/model-card.md` with the new, honestly-measured numbers.
- **User (Colab, has the GPU/runtime and Drive access):** runs the
  notebook/script Claude writes, reports back progress/errors between
  long-running cells (feature re-extraction, training) so Claude can keep
  debugging remotely without needing to execute it directly.

## 7. Explicitly out of scope for this phase

- Real blink-rate — committed as **Phase 1b**, not abandoned (see §4).
- Glasses-robustness preprocessing.
- WebGazer/gaze-fusion changes (already handled separately, this session).
- Combining with a second dataset (DIPSER or otherwise).
- Any change to the live frontend capture rate (belongs to Phase 1b).
- Any architecture or hyperparameter change (see §2 — deliberately held
  constant to isolate the feature-quality effect).
