"""
Module 6 - CV+AI Integration Layer (scope 6.6).

FusionPolicy (policy.py) is a second implementation of
app.intervention.decider.InterventionDecider, combining Module 3's camera
signals with Module 5's chat signals and live mid-session recovery
evidence (app.analytics.domain.metrics.observed_recovery_since, issue #45)
into sequenced intervention decisions.

Nothing in app/intervention/ is modified by this package's own logic (the
one exception - two additive fields on Signals - was made in Task 2, for
identity, not for fusion logic itself). Module 4's delivery code
(useIntervention.js, InterventionHost.jsx, the /intervention/* routes)
never needs to change: it already only knows how to render whatever
Decision the currently-active decider produced.

See docs/superpowers/specs/2026-09-30-module-6-fusion-design.md.
"""
