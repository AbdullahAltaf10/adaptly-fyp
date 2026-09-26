# Issue #74 — Module 10 Compliance Report Storage and API (plain-English summary)

## What this does

This wires Issue #72/#73's pure report builder into storage and a real API,
following Module 8's own conventions exactly: a repository for the
`compliance_reports` collection, a service layer that decides *when* to
generate a report (never *how* — that's still #72/#73's pure functions),
and three endpoints.

## Where this fits

```
Module 8 -- finalize_session() --> one saved session summary
                                          |
                    Issue #74 (THIS issue): generate_report()
                    - owns this session?           (401/403-shaped 404)
                    - session finalized yet?       (409 if not)
                    - report already exists?       (return unchanged)
                    - otherwise: call #73's build_compliance_report(),
                      passing in Module 8's own chunk-progress and
                      intervention-event repositories (read-only reuse)
                                          |
                          ComplianceReportRepository.save()
                                          |
                    GET/POST /api/sessions/{id}/compliance-report
                    GET /api/compliance/reports (hr_admin only)
```

## Endpoints

- `POST /api/sessions/{session_id}/compliance-report` — generate. Owner
  only. Idempotent: a second call returns the existing report unchanged,
  never recalculated (`outcome: "already_exists"`). A session with no
  finalized Module 8 summary yet returns `409` with reason code
  `analytics_summary_missing` — a compliance attestation is never derived
  from partial or missing analytics.
- `GET /api/sessions/{session_id}/compliance-report` — fetch. Owner or
  `hr_admin`. A report that hasn't been generated yet returns `409` with
  reason code `compliance_report_missing`, distinct from "session not
  found."
- `GET /api/compliance/reports` — list, with optional `user_id`/
  `content_id` filters. `hr_admin` only, via the existing
  `require_hr_admin` dependency (`app/auth/authorization.py`) — this issue
  does not invent a new authorization mechanism.

Every case where a session exists but doesn't belong to the caller returns
the same `404` a genuinely missing session would — the identical
non-existence-leak pattern Module 8's own `analytics/api/routes.py` already
uses.

## Why an idempotent, never-recalculated report

An attestation is a record of what was observed at a point in time, not a
live dashboard figure. If Module 10 silently recalculated a report every
time someone asked for it, two calls made minutes apart against the same
underlying data could theoretically diverge if the scoring config changed
between them — an attestation that isn't stable isn't evidence of
anything. Regenerating deliberately (a new report_id, a new generation
call) is future work, not something this issue does implicitly.

## HR-admin access without breaking owner access

`require_hr_admin` (Module 1's existing dependency) hard-requires a
registered profile — a caller with none gets a `404 Profile not found`.
That's fine for the HR-only list endpoint (an HR admin obviously has a
profile, since `corporate_role` lives on it), but using it as a hard gate
on the single-report `GET` would have meant a learner with no registered
Module 1 profile row could be locked out of *their own* report — an
outcome none of Module 8's own endpoints risk, since they never require a
profile at all. This issue's `GET` endpoint instead does its own soft
check: owner access never touches the profile lookup at all; only a
*non-owner* caller is checked against `corporate_role == "hr_admin"`, and a
caller with no profile there is simply treated as "not HR" rather than
erroring.

## Router registration

**Not registered in `backend/app/api/router.py` or `app/main.py`.** This
matches Module 8's own analytics router exactly: `analytics/api/routes.py`
is never included in the real app either (confirmed by grep — it only
appears wired into a standalone `FastAPI()` instance inside Module 8's own
tests). Since Module 10 directly extends a router that isn't live-wired
yet, following that same convention here is a decision, not an oversight
— wiring both in together is future work for whoever finishes Module 8's
own live integration (Issue #34).

## Testing

`backend/tests/compliance/test_persistence.py` — 5 tests: save-then-get
round-trips the contract-shaped report; a missing session returns `None`;
save is an upsert (never duplicates); list filters by `user_id`/
`content_id`; list with no filters returns everything.

`backend/tests/compliance/test_api.py` — 10 tests: owner can generate;
generation is idempotent; generation without a finalized summary returns a
clear `409`; a non-owner cannot generate; owner can fetch their own report;
a different, non-HR employee is denied; an `hr_admin` can fetch any report;
a missing report returns a clear `409`; `hr_admin` can list; a non-HR user
is denied the list endpoint.

Command: `python -m pytest backend/tests/compliance/ -q`
Result: **50 passed** (35 carried over from Issues #72/#73, plus 5 new
persistence tests and 10 new API tests).

Full backend suite: `python -m pytest backend/tests/ -q` (same 5 files
excluded for the pre-existing, documented `cv2`/`tensorflow` environment
gap Module 8's own PRs already excluded) — **390 passed**, 3 skipped, the
same 2 pre-existing failures, no regressions.

## Known limitations

- **Not wired into the live app**, as explained above — matches Module 8's
  own current state.
- **No re-generation path.** Once a report exists, nothing currently lets
  it be recomputed (e.g. after a scoring-config change). Deliberately out
  of scope; flagged for a future issue if it's ever needed.
- Issue #76 (auto-generation at session end) remains blocked on Module 8's
  own Issue #34 and Sibtain's agreement, as filed.
