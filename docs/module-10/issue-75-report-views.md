# Issue #75 — Module 10 Attestation Report Views (plain-English summary)

## What this does

This gives Module 10's compliance report somewhere to actually be seen: a
view for an employee's own report, and a minimal `hr_admin`-only list/detail
view — the full HR completion-tracking dashboard (manual assignment,
completion tracking) is Module 9's job, not this issue's.

## Where this lives

Module 8's `AnalyticsDashboard.jsx` is deliberately not wired into
`App.jsx`'s routing today — its own comment explains why: `App.jsx` is a
documented placeholder pending Module 1's real frontend migration, and
nothing else should build on top of it. `ComplianceReportPage.jsx` and
`HrComplianceReportsPage.jsx` follow the exact same convention: standalone
components, reachable the same way `AnalyticsDashboard` already is, not
wired into `App.jsx`. No new app-wide routing infrastructure was invented
for this issue.

## What was built

- `frontend/src/compliance/ComplianceReportView.jsx` — the shared
  presentational component both the employee page and the HR detail view
  render. Shows the Engagement Quality Score (or the insufficient-data
  state, never a fabricated number), each score component with its plain
  label, any excluded component's reason shown plainly rather than hidden,
  and the critical-section list with calm, non-clinical verdict labels.
- `frontend/src/compliance/labels.js` / `format.js` — the same
  "translate contract vocabulary into calm wording" and "missing is never
  zero" rules Module 8's own `analytics/labels.js`/`format.js` establish,
  duplicated in a small Module 10-owned copy rather than imported (see the
  files' own docstrings for why — same reasoning as the backend's
  persistence-layer duplication).
- `frontend/src/compliance/api.js` — the three endpoints, using the shared
  `frontend/src/api/client.js`, the same pattern
  `engagement/api.js`/`intervention/api.js` already use.
- `frontend/src/compliance/useComplianceReport.js` — a fetch hook mirroring
  Module 8's own `useSessionAnalytics`, including the same mock-data
  default and single swap point for wiring in the real endpoint later.
- `frontend/src/pages/ComplianceReportPage.jsx` — the employee's own report
  page.
- `frontend/src/pages/HrComplianceReportsPage.jsx` — the minimal HR list +
  detail view: a table of every report (session, learner, generated date,
  score) with a "View" button per row that renders the same
  `ComplianceReportView` used by the employee page.

## Wording

Verdict and status labels, matching the issue's own spec exactly:

| Value | Label |
|---|---|
| `sustained_engagement` | "Stayed engaged" |
| `difficulty_then_recovered` | "Found it tricky, then got back on track" |
| `difficulty_not_recovered` | "Found it tricky" |
| `not_reached` | "Not reached" |
| `insufficient_data` | "Not enough data" |

An excluded score component is shown with its reason in the same plain
tone — e.g. "Not counted this time — No critical sections were tagged for
this session." — never as a warning or a missing-data alarm, since it is
almost always the normal, expected state (no critical sections exist in any
real session yet, since Module 9 doesn't exist).

## What was deliberately not built

- **Route-level "only a signed-in hr_admin can reach this page" guarding.**
  There is no app-wide routing yet (see "Where this lives" above) for any
  module to guard a route within, Module 8's dashboard included. Access
  control is enforced where it actually matters — server-side, in Issue
  #74's endpoints (`require_hr_admin`, the owner-or-hr_admin check). This
  component trusts whatever data it's handed, the same way
  `AnalyticsDashboard.jsx` does.
- **No new UI libraries.** Everything here is plain JSX/CSS-in-JS-via-style-prop,
  matching `SummaryCard.jsx`'s own minimal styling approach.
- **The full HR dashboard** (assignment, completion tracking) — Module 9's
  scope, not this issue's.

## Testing

`frontend/src/compliance/ComplianceReportView.test.jsx` — 6 tests: the
no-report state; a complete report's score and components; an excluded
component's reason shown, not hidden; the insufficient-data state with no
fabricated score; an empty critical-sections list; and critical-section
verdicts rendering with calm labels (with explicit assertions that no
clinical/blaming words like "fail," "poor," or "abnormal" appear anywhere).

`frontend/src/pages/ComplianceReportPage.test.jsx` — 2 tests: loading then
ready, and an error state.

`frontend/src/pages/HrComplianceReportsPage.test.jsx` — 4 tests: loading
then the list; an empty state when there are no reports yet; an error
state; and clicking "View" revealing the full report detail.

Command: `npx vitest run` (from `frontend/`)
Result: **114 passed** (102 pre-existing + 12 new: 6 + 2 + 4).

### Manual test steps performed

1. Ran `npm run test -- --run` from `frontend/` with the new files present;
   confirmed all 114 tests pass, no pre-existing test broken.
2. Rendered `ComplianceReportPage` and `HrComplianceReportsPage` with each
   of the three mock scenarios (`MOCK_COMPLETE_REPORT`,
   `MOCK_INSUFFICIENT_DATA_REPORT`, `MOCK_REPORT_WITH_CRITICAL_SECTIONS`)
   via the test suite's `render()` calls and visually reviewed the rendered
   text output for each, confirming the wording table above is followed
   exactly and no numeric field silently renders as `0`, `null`, or
   `undefined` when a component is excluded.
3. Did not perform a live browser check against a running backend, since
   Issue #74's endpoints are not wired into the real app yet (see that
   issue's doc) — there is nothing live to point a browser at yet. This is
   the same situation Module 8's own dashboard shell was tested under
   before its own API issue landed.

## Known limitations

- Not reachable from Module 8's real dashboard yet in the literal sense of
  a clickable link — there is no real navigation in `App.jsx` for either
  dashboard to link from. Both pages are ready to be rendered directly
  (e.g. passed a `sessionId` prop) once real navigation exists.
- `useComplianceReport`'s default fetcher is still the mock layer; wiring
  in `getComplianceReport` from `compliance/api.js` is a one-line change
  whenever Issue #74's endpoints are registered into the live app.
