import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MOCK_COMPLETE_REPORT } from "../compliance/mockData";
import ComplianceReportPage from "./ComplianceReportPage";

function resolvedFetcher(report) {
  return vi.fn(() => Promise.resolve(report));
}

function rejectedFetcher() {
  return vi.fn(() => Promise.reject(new Error("network")));
}

describe("ComplianceReportPage", () => {
  it("shows a loading state, then the report", async () => {
    render(
      <ComplianceReportPage
        sessionId="session-1"
        fetchReport={resolvedFetcher(MOCK_COMPLETE_REPORT)}
      />
    );
    expect(screen.getByText(/loading your compliance report/i)).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText(/compliance attestation report/i)).toBeInTheDocument()
    );
    expect(screen.getByText("78/100")).toBeInTheDocument();
  });

  it("shows an error state when the report fails to load", async () => {
    render(<ComplianceReportPage sessionId="session-1" fetchReport={rejectedFetcher()} />);
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});
