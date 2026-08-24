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

**The evaluation script itself.** The numbers above were produced in a notebook
that was not kept. There is no command in this repository that regenerates
them, which means they cannot currently be reproduced or re-checked after a
change.

**Hyperparameters and seeds.** Layer sizes, learning rate, batch size, epoch
count and random seeds were not recorded. A retrain would be a new model that
happens to resemble this one, not a reproduction of it.

**Repeated runs.** Exactly one training run was performed per feature
configuration. The 9-feature version was chosen over the 7- and 11-feature
versions on a single run each, so **the difference between them has not been
shown to exceed run-to-run variation.** The choice is defensible on reasoning
(consistency between test and validation) but is not statistically established.

**Per-epoch curves.** Not saved, so overfitting cannot be inspected after the
fact.

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
