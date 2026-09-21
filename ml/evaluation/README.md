# Evaluation — what exists, and what does not

The issue that produced this migration says: *"do not claim full completion
without reproducible evaluation."* This file records exactly where that line
falls, so nobody has to guess which numbers can be defended.

## What is available

The figures in [`docs/model/model-card.md`](../../docs/model/model-card.md) are
real measurements taken during the prototype's training work:

| Metric | Test | Validation |
|---|---|---|
| Macro F1 | 0.351 | 0.387 |
| Focused recall | 77% | 74% |
| Drifting recall | 30% | 27% |
| Struggling recall | 10% | 18% |

They were computed on a subject-disjoint split of DAiSEE — no person appears in
more than one split, which was verified — so they describe generalisation to
unseen people rather than memorisation.

**Do not quote raw accuracy.** Always predicting "focused" scores 84.7% on the
same test set. Accuracy here measures the class imbalance, not the model.

## What is missing

> **Partly resolved.** The three items struck through below were closed by the
> work in [`FINDINGS.md`](FINDINGS.md). The rest of this file still stands.

**~~The evaluation script itself.~~** `evaluate.py` now reproduces the table
above from the committed artifacts, printing a measured-against-published delta
per figure and refusing to run if the artifact hashes do not match
`MANIFEST.json`. Every figure reproduces within 0.004.

**~~Hyperparameters and seeds.~~** Recovered from the original Colab notebook:
50 epochs, batch 32, seed 42, Adam at 5e-4, early stopping on
`val_macro_recall` with patience 7, `StandardScaler` fitted on train only. A
retrain is now a reproduction rather than a resemblance.

**~~The 7f / 9f / 11f comparison.~~** Redone under identical evaluation by
`compare_variants.py`. The answer turned out to be more interesting than "not
statistically established": the variants succeed on opposite splits, which is
the signature of fitting subjects rather than behaviour. See `FINDINGS.md` §3.

**Repeated runs for the original variant choice.** The 9-feature version was
still chosen over 7- and 11-feature on one run each. Later work in this
directory uses multiple seeds with significance tests; that original comparison
does not.

**Per-epoch curves for the production run.** Not saved as a file, though they
are visible in the recovered notebook's own cell outputs.

**Leave-one-subject-out cross-validation.** Every figure here, including the
improvements reported in `FINDINGS.md`, rests on a single train/test split.
LOSO would be a substantially stronger basis and has not been done.

**Any evaluation on this system's own users.** Everything above is measured
against DAiSEE. DAiSEE is 80% male, predominantly Asian, and recorded in
controlled conditions. Nothing has been measured on the population this system
is for, in the conditions it will actually run in.

**The rule-based states are entirely unevaluated.** `fatigued`, `recovered` and
Deep Thinking do not come from the model and have no benchmark behind them.
`fatigued` has been observed firing correctly in live use. `recovered` and Deep
Thinking have unit tests but have never been observed firing in a real session.
Deep Thinking's thresholds are reasoned estimates — there is no published
reference distribution for "stillness" — and a firing should be read as a
hypothesis, not a measurement.

## What would close the gap

In rough order of value per unit of effort:

1. **An evaluation script that loads `ml/artifacts/` and reproduces the table
   above from held-out data.** Without this, every number in the model card is
   an assertion. This is the only item that makes the others checkable.
2. **A held-out set committed or scripted for download**, so step 1 runs the
   same way on anyone's machine.
3. **A recorded training run** — script, hyperparameters, seed, and the curves
   it produced.
4. **Repeated runs or k-fold cross-validation** across the 7-, 9- and
   11-feature variants, so the feature choice rests on more than one sample.
5. **A small labelled set collected from real sessions**, which is the only way
   to learn whether DAiSEE performance transfers at all.

## Verifying the artifacts have not changed

Evaluation numbers only describe the files they were measured on. The hashes in
`ml/artifacts/MANIFEST.json` pin those exact files:

```python
from ml.inference.model import verify_artifacts
verify_artifacts()   # {filename: True/False}
```

A model that changes silently produces plausible but wrong output, which is far
harder to notice than a crash. `backend/tests/test_ml_inference.py` runs this
check on every test run.
