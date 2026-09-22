"""
Module 4 - Adaptive Intervention.

Decides what response to give when Module 3 reports a problem, delivers it, and
records what became of it.

    decider.py     the interface: Signals in, Decision or silence out
    policy.py      DefaultPolicy - the tiered rules, measured not argued
    cooldown.py    per-session quiet period, 120s to match Module 8's window
    contracts.py   event building, the lifecycle, and what Module 8 measures
    store.py       persistence - a stand-in for Module 8's repository
    service.py     the live path, called from /engagement/analyze
    routes.py      /intervention/* - where delivery is reported back

The decision is behind an interface rather than hard-coded, because scope 6.6
gives Module 6 the job of deciding "what type of support is most likely to
help" and of planning sequences. Module 6 registers a second implementation
through service.set_decider and nothing in the delivery path changes.

The half that is easy to get wrong is the lifecycle, not the decision. Module 8
only begins measuring recovery from certain delivery statuses, and `offered` is
not one of them - so an intervention that is fired and forgotten produces a
full event collection and an empty dashboard. See contracts.py.

Current state: P1 and P2. No content simplification yet (P3 - Gemini), no
frontend (P4 - blocked on the content viewer, issue #12), and `outcome` and
`helped` are still filled in only post-session (P5 - blocked on issue #45).
"""
