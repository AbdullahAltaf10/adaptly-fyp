import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// `../compliance/api`'s real module imports the shared `api/client`, which
// initializes real Firebase auth at import time. Every test here supplies
// its own `fetchReport`/`fetchSessions`, but `ComplianceReportPage` still
// imports `generateComplianceReport` from `../compliance/api` at module
// scope for the "Generate report" button, so the client is mocked the same
// way `HrComplianceReportsPage`'s tests already do.
vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import apiClient from "../api/client";
import { MOCK_COMPLETE_REPORT } from "../compliance/mockData";
import ComplianceReportPage from "./ComplianceReportPage";

function resolvedFetcher(report) {
  return vi.fn(() => Promise.resolve(report));
}

function rejectedFetcher() {
  return vi.fn(() => Promise.reject(new Error("network")));
}

function missingReportError() {
  return {
    response: {
      status: 409,
      data: { detail: { reason_code: "compliance_report_missing", message: "none yet" } },
    },
  };
}

function fetchSessionsWith(sessionId) {
  return vi.fn(() =>
    Promise.resolve({ data: { items: sessionId ? [{ session_id: sessionId }] : [] } })
  );
}

describe("ComplianceReportPage", () => {
  beforeEach(() => {
    apiClient.post.mockReset();
  });

  it("shows a loading state, then the report, for an explicit sessionId", async () => {
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

  it("with no sessionId given, discovers the most recent completed session and loads its report", async () => {
    const fetchReport = resolvedFetcher(MOCK_COMPLETE_REPORT);
    render(
      <ComplianceReportPage
        fetchSessions={fetchSessionsWith("session-1")}
        fetchReport={fetchReport}
      />
    );

    expect(screen.getByText(/looking for your most recent session/i)).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByText(/compliance attestation report/i)).toBeInTheDocument()
    );
    expect(fetchReport).toHaveBeenCalledWith("session-1");
  });

  it("shows a friendly empty state when the learner has no completed sessions", async () => {
    render(
      <ComplianceReportPage
        fetchSessions={fetchSessionsWith(null)}
        fetchReport={resolvedFetcher(MOCK_COMPLETE_REPORT)}
      />
    );

    await waitFor(() =>
      expect(screen.getByText(/haven.t completed a study session yet/i)).toBeInTheDocument()
    );
  });

  it("offers a Generate report button when no report exists yet, and loads the report once generation succeeds", async () => {
    const fetchReport = vi
      .fn()
      .mockImplementationOnce(() => Promise.reject(missingReportError()))
      .mockImplementationOnce(() => Promise.resolve(MOCK_COMPLETE_REPORT));
    apiClient.post.mockResolvedValue({ data: { outcome: "created" } });

    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();

    render(<ComplianceReportPage sessionId="session-1" fetchReport={fetchReport} />);

    await waitFor(() =>
      expect(
        screen.getByText(/no compliance report has been generated for this session yet/i)
      ).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: /generate report/i }));

    expect(apiClient.post).toHaveBeenCalledWith("/api/sessions/session-1/compliance-report");
    await waitFor(() =>
      expect(screen.getByText(/compliance attestation report/i)).toBeInTheDocument()
    );
    expect(fetchReport).toHaveBeenCalledTimes(2);
  });

  it("shows an error if report generation fails, without losing the Generate button", async () => {
    const fetchReport = vi.fn(() => Promise.reject(missingReportError()));
    apiClient.post.mockRejectedValue(new Error("boom"));

    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();

    render(<ComplianceReportPage sessionId="session-1" fetchReport={fetchReport} />);

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /generate report/i })).toBeInTheDocument()
    );

    await user.click(screen.getByRole("button", { name: /generate report/i }));

    await waitFor(() =>
      expect(screen.getByText(/could not generate the report/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /generate report/i })).toBeInTheDocument();
  });
});
