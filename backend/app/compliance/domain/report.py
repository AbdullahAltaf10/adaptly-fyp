"""Pure Module 10 compliance-report builder (Issue #73).

Combines Issue #72's Engagement Quality Score (``score.py``) with this
issue's critical-section evidence (``critical_sections.py``) into one
complete, ``compliance-report.schema.json``-shaped document. Still
infrastructure-free: no MongoDB, no FastAPI, no ``report_id``/timestamp
generation beyond what the caller passes in. Issue #74's service layer owns
generating a real ``report_id`` and deciding ``generated_at``.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from .critical_sections import build_critical_section_evidence
from .score import DEFAULT_CONFIG, ScoreConfig, build_engagement_quality_score

SCHEMA_VERSION = "1.0"


def build_compliance_report(
    summary: Mapping[str, Any],
    *,
    report_id: str,
    generated_at: str,
    chunk_context: Sequence[Mapping[str, Any]] | None = None,
    intervention_events: Sequence[Mapping[str, Any]] = (),
    config: ScoreConfig = DEFAULT_CONFIG,
) -> dict[str, Any]:
    """Build one complete, contract-shaped compliance report from a
    finalized Module 8 session summary.

    ``report_id`` and ``generated_at`` are injected rather than generated
    here, mirroring ``build_session_summary``'s own ``computed_at``
    injection (Issue #26) -- this keeps the function deterministic and
    trivially testable.
    """

    score_result = build_engagement_quality_score(summary, config=config)
    critical_sections = build_critical_section_evidence(
        summary["timeline_segments"], chunk_context, intervention_events
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "score_version": score_result["score_version"],
        "report_id": report_id,
        "session_id": summary["session_id"],
        "user_id": summary["user_id"],
        "content_id": summary["content_id"],
        "generated_at": generated_at,
        "source_summary": {
            "metric_version": summary["metric_version"],
            "computed_at": summary["computed_at"],
        },
        "status": score_result["status"],
        "engagement_quality_score": score_result["engagement_quality_score"],
        "components": score_result["components"],
        "excluded_components": score_result["excluded_components"],
        "critical_sections": critical_sections,
        "data_quality": summary["data_quality"],
    }
