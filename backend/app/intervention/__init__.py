"""
Module 4 — Adaptive Intervention.

Decides what response to give when Module 3 reports a problem, and delivers it.

The decision is behind an interface (decider.py) rather than hard-coded,
because scope 6.6 gives Module 6 the job of deciding "what type of support is
most likely to help" and of planning sequences. Module 6 arrives as a second
implementation of that interface instead of a rewrite of this one.

Current state: P1 - decision logic only. Nothing is wired to the engagement
stream yet, no Gemini call, no delivery. See ml/evaluation/trigger_fusion.py
for the measurements the policy's tiers come from.
"""
