/**
 * One compliance attestation report, rendered identically for a learner
 * viewing their own report and for an hr_admin viewing someone else's (the
 * backend decides who may fetch which report; this component only renders
 * whatever it's given).
 *
 * Follows Module 8's learner-safe, non-clinical wording rule exactly (see
 * `src/analytics/labels.js`'s own docstring) -- an excluded score component
 * or a critical section showing difficulty is normal information, never a
 * verdict on the learner.
 */

import {
  COMPLIANCE_STATUS_LABELS,
  CRITICAL_SECTION_VERDICT_LABELS,
  SCORE_COMPONENT_LABELS,
} from "./labels";
import { formatDate, formatScore } from "./format";

function ScoreComponentRow({ component }) {
  const label = SCORE_COMPONENT_LABELS[component.key] ?? component.key;
  const isExcluded = component.status === "not_applicable";

  return (
    <li>
      <strong>{label}:</strong>{" "}
      {isExcluded ? (
        <span>
          Not counted this time
          {component.reason ? ` — ${component.reason}` : ""}
        </span>
      ) : (
        <span>{formatScore(component.score)}</span>
      )}
    </li>
  );
}

function CriticalSectionRow({ section }) {
  const label = CRITICAL_SECTION_VERDICT_LABELS[section.verdict] ?? section.verdict;
  return (
    <li>
      <strong>{section.chunk_id}:</strong> {label}
    </li>
  );
}

export default function ComplianceReportView({ report }) {
  if (!report) {
    return (
      <p role="status">No compliance report is available for this session yet.</p>
    );
  }

  const isInsufficientData = report.status === "insufficient_data";

  return (
    <article aria-labelledby="compliance-report-heading">
      <h2 id="compliance-report-heading">Compliance attestation report</h2>
      <p>Generated {formatDate(report.generated_at)}</p>

      <section aria-labelledby="score-heading">
        <h3 id="score-heading">Engagement Quality Score</h3>
        <p role="status">
          {isInsufficientData ? (
            COMPLIANCE_STATUS_LABELS.insufficient_data
          ) : (
            <strong>{formatScore(report.engagement_quality_score)}</strong>
          )}
        </p>
        {isInsufficientData && (
          <p>
            There wasn&apos;t enough reliable data from this session to
            calculate a score. This isn&apos;t a reflection of the learner —
            it usually means several signals were unavailable at once.
          </p>
        )}
        <ul aria-label="Score breakdown">
          {report.components.map((component) => (
            <ScoreComponentRow key={component.key} component={component} />
          ))}
        </ul>
      </section>

      <section aria-labelledby="critical-sections-heading">
        <h3 id="critical-sections-heading">Key sections</h3>
        {report.critical_sections.length === 0 ? (
          <p>No sections have been marked as key for this content yet.</p>
        ) : (
          <ul aria-label="Key section engagement">
            {report.critical_sections.map((section) => (
              <CriticalSectionRow key={section.chunk_id} section={section} />
            ))}
          </ul>
        )}
      </section>

      {report.data_quality && !report.data_quality.has_sufficient_data && (
        <p role="note">
          Some data from this session was incomplete, which may affect how
          complete this report is.
        </p>
      )}
    </article>
  );
}
