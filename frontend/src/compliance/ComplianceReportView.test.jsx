import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ComplianceReportView from "./ComplianceReportView";
import {
  MOCK_COMPLETE_REPORT,
  MOCK_INSUFFICIENT_DATA_REPORT,
  MOCK_REPORT_WITH_CRITICAL_SECTIONS,
} from "./mockData";

describe("ComplianceReportView", () => {
  it("renders nothing-yet state when no report is available", () => {
    render(<ComplianceReportView report={null} />);
    expect(
      screen.getByText(/no compliance report is available/i)
    ).toBeInTheDocument();
  });

  it("renders the score and included components for a complete report", () => {
    render(<ComplianceReportView report={MOCK_COMPLETE_REPORT} />);
    expect(screen.getByText("78/100")).toBeInTheDocument();
    expect(screen.getByText(/time spent focused/i)).toBeInTheDocument();
  });

  it("shows excluded components with their plain-language reason, not hidden", () => {
    render(<ComplianceReportView report={MOCK_COMPLETE_REPORT} />);
    expect(screen.getByText(/engagement with key sections/i)).toBeInTheDocument();
    expect(screen.getByText(/no critical sections were tagged/i)).toBeInTheDocument();
    expect(screen.getByText(/not counted this time/i)).toBeInTheDocument();
  });

  it("renders the insufficient-data state without a fabricated score", () => {
    render(<ComplianceReportView report={MOCK_INSUFFICIENT_DATA_REPORT} />);
    expect(screen.getByText(/not enough data for a score yet/i)).toBeInTheDocument();
    expect(screen.queryByText("null/100")).not.toBeInTheDocument();
  });

  it("renders an empty critical-sections list without an error", () => {
    render(<ComplianceReportView report={MOCK_COMPLETE_REPORT} />);
    expect(
      screen.getByText(/no sections have been marked as key/i)
    ).toBeInTheDocument();
  });

  it("renders critical-section verdicts using calm, non-clinical labels", () => {
    render(<ComplianceReportView report={MOCK_REPORT_WITH_CRITICAL_SECTIONS} />);
    expect(screen.getByText(/stayed engaged/i)).toBeInTheDocument();
    expect(screen.getByText(/found it tricky, then got back on track/i)).toBeInTheDocument();
    expect(screen.getByText(/not reached/i)).toBeInTheDocument();
    expect(screen.queryByText(/fail/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/poor/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/abnormal/i)).not.toBeInTheDocument();
  });
});
