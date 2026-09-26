import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// This page's default `fetchReports` prop calls `listComplianceReports`,
// which imports the shared `api/client` -- and that module initializes real
// Firebase auth at import time. Every test here supplies its own
// `fetchReports`, but the module-level import still runs, so the client
// must be mocked the same way `AssistantPanel`'s tests already do.
vi.mock("../api/client", () => ({
  default: { get: vi.fn(), post: vi.fn() },
}));

import HrComplianceReportsPage from "./HrComplianceReportsPage";
import { MOCK_COMPLETE_REPORT } from "../compliance/mockData";

function fetchReportsResolving(items) {
  return vi.fn(() => Promise.resolve({ data: { items } }));
}

describe("HrComplianceReportsPage", () => {
  it("shows a loading state, then the list of reports", async () => {
    render(<HrComplianceReportsPage fetchReports={fetchReportsResolving([MOCK_COMPLETE_REPORT])} />);
    expect(screen.getByText(/loading reports/i)).toBeInTheDocument();

    await waitFor(() => expect(screen.getByText("session-1")).toBeInTheDocument());
    expect(screen.getByText("78/100")).toBeInTheDocument();
  });

  it("shows an empty state when there are no reports yet", async () => {
    render(<HrComplianceReportsPage fetchReports={fetchReportsResolving([])} />);
    await waitFor(() =>
      expect(screen.getByText(/no compliance reports have been generated/i)).toBeInTheDocument()
    );
  });

  it("shows an error state when the list fails to load", async () => {
    const fetchReports = vi.fn(() => Promise.reject(new Error("network")));
    render(<HrComplianceReportsPage fetchReports={fetchReports} />);
    await waitFor(() =>
      expect(screen.getByText(/could not load compliance reports/i)).toBeInTheDocument()
    );
  });

  it("shows the full report detail after clicking View", async () => {
    render(<HrComplianceReportsPage fetchReports={fetchReportsResolving([MOCK_COMPLETE_REPORT])} />);
    await waitFor(() => expect(screen.getByText("session-1")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /view/i }));
    expect(screen.getByText(/compliance attestation report/i)).toBeInTheDocument();
  });
});
