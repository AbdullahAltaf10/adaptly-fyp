# Module 8 Analytics API (Issue #29)

Four endpoints, implemented in `backend/app/analytics/api/routes.py`. All
responses are derived analytics — none expose raw biometric telemetry
(webcam frames, dense facial landmarks, raw gaze streams) or full chat
transcripts.

## Authentication

**Every endpoint below requires an authenticated caller and resolves the
learner exclusively through the `get_current_user_id` dependency
(`backend/app/api/deps.py`). No endpoint accepts or trusts a client-supplied
`user_id`.**

> **TEMPORARY:** Module 1's real authentication (Firebase-based) is not yet
> merged into `develop`. Until it is, `get_current_user_id` reads a dev-only
> header instead of verifying a real credential:
>
> ```
> X-Dev-User-Id: <user_id>
> ```
>
> Missing this header returns `401 Unauthorized`. This is explicitly a
> placeholder — see Issue #34 for the real integration. Swapping in real
> auth later only requires changing the body of `get_current_user_id`; no
> endpoint code changes, because every endpoint already depends on it rather
> than reading `user_id` from anywhere else.

## Ownership and existence errors

Two endpoints (`GET .../analytics` and `POST .../insight-report/retry`) take
a `session_id`. Both use the same rule: **a session that doesn't exist and a
session that belongs to a different learner return the identical `404`
response.** This is deliberate — returning a different status for "not
yours" vs. "doesn't exist" would let a caller enumerate other learners'
session IDs.

---

### `GET /api/sessions/{session_id}/analytics`

Full post-session analytics payload for one completed session.

**Path parameters:** `session_id` (string, required)

**Response `200`** — the full `session-summary.schema.json`-shaped document
(`schema_version`, `metric_version`, `session_id`, `user_id`, `content_id`,
`duration_seconds`, `completed_at`, `computed_at`, `engagement_distribution`,
`timeline_segments`, `longest_focused_period`, `intervention_metrics`,
`recovery_metrics`, `assistant_usage`, `critical_section_engagement`,
`chunks_completed`, `data_quality`), plus one additional envelope field not
in that schema:

```json
"insight_report": { "status": "pending", "report_text": null }
```

`insight_report.status` mirrors `analytics-report.schema.json`'s status enum
(`pending | generated | fallback_generated | failed`). `report_text` is
always `null` today — Issue #32 is what will ever populate it.

**Errors:**

| Status | Reason code | Meaning |
|---|---|---|
| `404` | — | Session does not exist, or belongs to a different learner. |
| `409` | `session_not_completed` | Session exists and is yours, but hasn't finished yet — active-session analytics are never returned as if final. |
| `409` | `analytics_summary_missing` | Session is marked `completed` but no summary has been computed yet (retry finalization). |
| `401` | — | Missing/invalid auth. |

**Example (`200`):**

```json
{
  "schema_version": "1.0",
  "metric_version": "1.0",
  "session_id": "session-1",
  "user_id": "user-1",
  "content_id": "content-1",
  "duration_seconds": 60,
  "completed_at": "2026-08-17T09:01:00Z",
  "computed_at": "2026-08-17T09:01:00Z",
  "engagement_distribution": { "focused": {"duration_seconds": 45.0, "percentage": 75.0}, "...": "..." },
  "timeline_segments": [ { "started_at": "...", "ended_at": "...", "duration_seconds": 5.0, "state": "focused", "average_confidence": 0.9, "chunk_id": "chunk-1" } ],
  "longest_focused_period": { "started_at": "...", "ended_at": "...", "duration_seconds": 20.0, "chunk_id": "chunk-1" },
  "intervention_metrics": { "total_count": 1, "effective_count": 1, "ineffective_count": 0, "unknown_outcome_count": 0, "effectiveness_rate": 1.0, "by_type": [] },
  "recovery_metrics": { "eligible_intervention_count": 1, "recovered_intervention_count": 1, "recovery_rate": 1.0, "average_recovery_time_seconds": 5.0 },
  "assistant_usage": { "total_event_count": 2, "learner_message_count": 1, "assistant_message_count": 1, "typed_input_count": 1, "voice_input_count": 0, "suggested_question_count": 0, "text_response_count": 1, "voice_response_count": 0, "successful_interaction_count": 1, "error_count": 0 },
  "critical_section_engagement": { "critical_section_count": 1, "engaged_section_count": 1, "engagement_rate": 1.0, "focused_duration_seconds": 30.0 },
  "chunks_completed": 2,
  "data_quality": { "has_sufficient_data": true, "event_coverage_rate": 1.0, "unknown_duration_seconds": 0.0, "flags": [] },
  "insight_report": { "status": "pending", "report_text": null }
}
```

---

### `GET /api/analytics/sessions`

Paginated history of the authenticated learner's own completed sessions.
Compact summaries only — no raw event streams.

**Query parameters:**

| Name | Type | Default | Constraints |
|---|---|---|---|
| `limit` | integer | `20` | `1`–`100` (else `422`) |
| `offset` | integer | `0` | `>= 0` (else `422`) |
| `content_id` | string | none | optional filter to one piece of content |

**Ordering:** `completed_at` descending (most recent session first), with
`session_id` descending as a tiebreaker — deterministic regardless of
insertion order.

**Response `200`:**

```json
{
  "items": [
    {
      "schema_version": "1.0",
      "metric_version": "1.0",
      "session_id": "session-3",
      "user_id": "user-1",
      "content_id": "content-1",
      "duration_seconds": 60,
      "completed_at": "2026-08-17T09:04:20Z",
      "computed_at": "2026-08-17T09:04:20Z",
      "engagement_distribution": { "...": "..." },
      "longest_focused_period": { "...": "..." },
      "intervention_metrics": { "...": "..." },
      "recovery_metrics": { "...": "..." },
      "assistant_usage": { "...": "..." },
      "critical_section_engagement": { "...": "..." },
      "chunks_completed": 2,
      "data_quality": { "...": "..." },
      "insight_report_status": "pending"
    }
  ],
  "pagination": { "limit": 20, "offset": 0, "returned_count": 1, "total_count": 3 }
}
```

Note: `timeline_segments` is intentionally omitted from history items (it's
the one genuinely large/raw-ish field in the summary); use the single-session
analytics endpoint for the full timeline.

**Errors:**

| Status | Meaning |
|---|---|
| `422` | Invalid `limit`/`offset` (out of range). |
| `401` | Missing/invalid auth. |

An empty history is **not** an error — it returns `200` with `"items": []`
and `"total_count": 0`.

---

### `GET /api/analytics/learning-profile`

Cross-session learning trends for the authenticated learner.

**Response `200`** — a `learning-profile.schema.json`-shaped document.

Until Issue #33 computes real multi-session profiles, this returns a
contract-shaped **placeholder** (`sessions_analyzed: 0`,
`focus_trend`/`recovery_trend: "insufficient_data"`, empty arrays, `null`
where the schema allows it, `data_quality.flags: ["insufficient_sessions"]`).
The response shape will not change when #33 lands — this endpoint already
prefers a real stored profile over the placeholder whenever one exists.

**Errors:** `401` only (missing/invalid auth). This endpoint never 404s —
"no profile yet" is represented by the placeholder body, not an error.

---

### `POST /api/sessions/{session_id}/insight-report/retry`

Stub. Real Gemini insight-report generation is Issue #32's scope; this
endpoint exists so the API shape is stable ahead of that, and **never**
recomputes or re-saves the session summary.

**Path parameters:** `session_id` (string, required)

**Response `200`:**

```json
{
  "session_id": "session-1",
  "insight_report_status": "pending",
  "retried": false,
  "message": "Insight report generation is not implemented yet (see Issue #32). The numeric analytics summary is unaffected and was not recomputed."
}
```

If a report already exists (`generated` or `fallback_generated`), the same
shape is returned with a message noting there's nothing to retry, and
`insight_report_status` reflecting the existing value.

**Errors:**

| Status | Reason code | Meaning |
|---|---|---|
| `404` | — | Session does not exist, or belongs to a different learner. |
| `409` | `session_not_completed` | Session isn't finished yet. |
| `409` | `analytics_summary_missing` | Session is completed but has no summary to attach a report to. |
| `401` | — | Missing/invalid auth. |
