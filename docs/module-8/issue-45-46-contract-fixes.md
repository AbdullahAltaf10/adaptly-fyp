# Issues #45 & #46 — Module 8 Contract Fixes (plain-English summary)

These two issues came from Sibtain, who read through the metric engine
carefully while getting ready to build Module 4 (the adaptive-help engine)
against it. One was a small heads-up about fields Module 4 will need soon;
the other was a real, working bug in how "did this help?" gets calculated.
Both are fixed here.

## Issue #45 — two new fields for future escalation sequences (`sequence_id`, `step_index`)

Module 4 is planning something called an "escalation sequence" — if
simplifying the text doesn't seem to help, the app might then suggest a
break, and if that doesn't help either, offer the chatbot. To track that a
group of interventions all belong to the same escalating attempt to help
(rather than being three unrelated, separate events), each one will need a
shared `sequence_id` (which sequence it belongs to) and a `step_index`
(which step in that sequence it was — 1st attempt, 2nd attempt, etc.).

Module 4 isn't built yet, so nothing produces these values today. This
issue just reserves the two field names in the shared intervention format
now, so Module 4 doesn't have to wait on a Module 8 change later. Both
fields are optional and can be left blank ("null") — nothing that already
exists has to be updated because of this.

There's one detail worth calling out because it's an easy mistake to make
in this codebase: adding a field to the shared contract **is not enough on
its own**. The database-writing code keeps its own separate list of "fields
we're allowed to save" (as a privacy safeguard — see the Issue #27 write-up
for why). If a field is added to the contract but not to that allowed list,
it gets **silently thrown away** every time it's saved — no error, no
warning, it just never shows up later. Both lists were updated together
here specifically to avoid that trap.

## Issue #46 — the real bug: recovery numbers were quietly wrong

### What was wrong

Every time the app offers a learner some help (simplify the text, suggest
a break, etc.), Module 8 later asks: "did the learner recover afterward?"
and "how long did that take?" Those two answers feed directly into the
"recovery rate" and "average recovery time" numbers shown on a learner's
summary.

To ask that question, the system first has to decide whether a given piece
of help even counts — whether it's "eligible" to be checked at all. The bug
was in how that eligibility was decided: it looked at the help's **current,
right-now status** ("offered," "displayed," "accepted," "dismissed," etc.)
instead of the simple, permanent fact of **whether it ever actually reached
the learner**.

That status keeps changing over the life of one piece of help. It might go:
offered → displayed → accepted → dismissed. The bug is that "dismissed" was
never in the list of statuses considered eligible. So if a piece of help
was shown, genuinely helped the learner, and *was later dismissed* (which
is completely normal — a learner reads it and closes it), the system would
end up quietly throwing that whole case out of the recovery calculation, as
if it had never happened.

### Why that's worse than just "a missing data point"

This wasn't just losing a random few data points evenly — it was
systematically biased in one direction. Help that worked well and then got
dismissed (a completely normal, positive pattern — "I saw it, it worked, I
closed it") was the exact case getting thrown away. Meanwhile, help that
was left open, ignored, or never actively closed stuck around as "eligible"
in the numbers. That means the interventions most likely to vanish from the
statistics were disproportionately the successful ones being dismissed
normally — which quietly inflated the recovery rate shown to everyone. It
also meant a system that simply never bothered reporting when help was
dismissed would look *better* in the numbers than one that honestly
reported it — exactly backwards from what should happen.

### A concrete before/after example

Say a learner was offered a simplified explanation, it helped them recover,
and afterward they dismissed it (totally normal). Say that happened for
every single piece of help offered this session — 4 out of 4.

**Before the fix:** because every one of those 4 ended in "dismissed,"
every one of them was thrown out of the count entirely. The system would
report **0 eligible interventions**, and `recovery_rate` would be `null`
("not enough information") — hiding four real, successful recoveries.

**After the fix:** all 4 are correctly counted, because delivery genuinely
happened for each one. The system now reports **4 eligible, 4 recovered,
recovery_rate: 100%** — accurate, and no longer punished for the learner
having done something completely normal (closing something after reading
it).

### Why the fix is a real fix, not a patch

The tempting quick fix would have been to just add "dismissed" to the list
of acceptable statuses. That would have been another patch on the same
fragile idea — deciding eligibility from a value that keeps changing over
time. The next status this bug could have hidden behind was always going
to be one bad list away.

Instead, the fix adds one new fact to the record: **`delivered_at`** — the
one moment delivery happened, recorded once, and never touched again
afterward. Eligibility is now decided purely by "was this ever delivered?"
(`delivered_at` is set, yes or no) — a fact that cannot become stale or
change meaning later the way a status field can. The system no longer looks
at `delivery_status` for this decision at all, on purpose, so this specific
category of bug (something that used to be true stops looking true because
an unrelated field moved on) cannot recur here.

There is deliberately no fallback for old data without `delivered_at` set.
Normally a change like this would need to stay compatible with existing
real data — but nothing has produced a real intervention event yet (neither
Module 8's own persistence nor Module 4 is merged into the shared codebase
yet), so there is no real data to protect, and keeping a "just in case"
fallback to the old logic would have quietly reintroduced the exact bug
being fixed for any future event that happened to arrive without the new
field set.

## What was cleaned up alongside the fix

The old status-based logic used two lists tucked away in Module 8's
settings — one describing which statuses counted as "delivered" for
automatic help (like simplified text), and a separate one for help that
needs the learner to actively accept it (like the assistant). Once the fix
removed the status-based logic entirely, both of those lists — and two
related lists they depended on for sorting help into "automatic" vs.
"learner-initiated" categories — had nothing left reading them anywhere in
the codebase. All four were removed rather than left behind as unused,
misleading settings that looked like they still mattered.

## Testing

The fix is proven with a direct test that takes the exact bug scenario —
the same piece of help and the same learner engagement data — and runs it
through five different final statuses (`displayed`, `accepted`,
`completed`, `dismissed`, `failed`), confirming every single one now
produces **identical** eligibility, recovery count, and recovery rate. A
second test confirms the one thing that must **not** change: help that
never actually reached the learner (`delivered_at` never set, e.g. still
"offered") is correctly still left out. Additional tests confirm the two
new fields from Issue #45 survive being saved and re-read from storage
without being silently dropped, and that the shared contract still accepts
intervention events whether the new fields are explicitly blank, filled
in, or left out entirely — so nothing that already exists breaks.

All 117 backend analytics tests pass (114 existing + 3 new), confirming
nothing else was disturbed.

## Known limitations

- **No real intervention events exist yet** to migrate — this fix lands
  cleanly today specifically because Module 4 (the only future producer of
  these events) isn't merged yet. Once it is, Module 4 will need to
  actually set `delivered_at` when it delivers something, or its
  interventions will correctly — but silently — never be counted for
  recovery.
- **`sequence_id`/`step_index` are reserved but unused.** Nothing reads or
  writes them yet; they exist so Module 4's escalation-sequence feature has
  somewhere to put this information when it's built.
