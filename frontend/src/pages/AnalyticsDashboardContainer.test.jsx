/**
 * Tests for the real-session-loading wrapper around AnalyticsDashboard
 * (follow-up to PR #86's documented "demo-session" placeholder).
 *
 * Like AnalyticsDashboard's own tests, every test injects its own fetchers
 * instead of touching the real API client, so these stay fast and
 * deterministic.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

// The container's default props point at the real API functions in
// "../analytics/api", which in turn import the shared axios client and
// (transitively) Firebase init -- not available/configured in a test
// environment. Every test here supplies its own fetchers, so the real
// module is never actually needed; it's mocked purely to keep it from
// loading at import time.
vi.mock("../analytics/api", () => ({
  fetchMostRecentCompletedSession: vi.fn(),
  fetchSessionAnalytics: vi.fn(),
  requestInsightReport: vi.fn(),
}));

import { MOCK_SCENARIOS } from "../analytics/mockData";
import AnalyticsDashboardContainer from "./AnalyticsDashboardContainer";

function resolvedRecentSession(session) {
  return vi.fn(() => Promise.resolve(session));
}

function rejectedRecentSession(kind) {
  return vi.fn(() => {
    const error = new Error("mock error");
    error.kind = kind;
    return Promise.reject(error);
  });
}

function resolvedAnalytics(scenario) {
  return vi.fn(() => Promise.resolve(scenario));
}

describe("AnalyticsDashboardContainer", () => {
  it("loads the real most recent completed session and passes it to AnalyticsDashboard", async () => {
    const fetchRecentSession = resolvedRecentSession({
      session_id: "session-normal",
      completed_at: "2026-08-17T09:20:00Z",
    });
    const fetchAnalytics = resolvedAnalytics(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION);

    render(
      <MemoryRouter>
        <AnalyticsDashboardContainer
          fetchRecentSession={fetchRecentSession}
          fetchAnalytics={fetchAnalytics}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Intro to Cellular Respiration")).toBeInTheDocument();
    expect(fetchRecentSession).toHaveBeenCalledTimes(1);
    expect(fetchAnalytics).toHaveBeenCalledWith("session-normal");
  });

  it("shows a calm loading state before the session list resolves", () => {
    render(
      <MemoryRouter>
        <AnalyticsDashboardContainer
          fetchRecentSession={() => new Promise(() => {})}
          fetchAnalytics={resolvedAnalytics(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION)}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("status")).toHaveTextContent(/loading your session summary/i);
  });

  it("shows a friendly empty state when the learner has no completed sessions", async () => {
    const fetchRecentSession = resolvedRecentSession(null);
    const fetchAnalytics = vi.fn();

    render(
      <MemoryRouter>
        <AnalyticsDashboardContainer
          fetchRecentSession={fetchRecentSession}
          fetchAnalytics={fetchAnalytics}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/no session summary yet/i)).toBeInTheDocument();
    expect(screen.getByText(/finish a study session/i)).toBeInTheDocument();
    // No real analytics fetch should ever be attempted with no session to fetch.
    expect(fetchAnalytics).not.toHaveBeenCalled();
  });

  it("shows an error state when the session-history request fails", async () => {
    render(
      <MemoryRouter>
        <AnalyticsDashboardContainer
          fetchRecentSession={rejectedRecentSession("server_error")}
          fetchAnalytics={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });
});

describe("AnalyticsDashboardContainer report generation", () => {
  const SESSION = { session_id: "sess-9", completed_at: "2026-08-17T09:20:00Z" };
  const base = MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION;
  const pending = { ...base, insightReport: { status: "pending", report_text: null } };

  it("requests the report for the loaded session, then refetches analytics", async () => {
    const done = {
      ...base,
      insightReport: { status: "generated", report_text: "Written by the server." },
    };
    const fetchAnalytics = vi.fn().mockResolvedValueOnce(pending).mockResolvedValueOnce(done);
    const requestReport = vi.fn().mockResolvedValue({ retried: true, message: null });

    render(
      <MemoryRouter>
        <AnalyticsDashboardContainer
          fetchRecentSession={resolvedRecentSession(SESSION)}
          fetchAnalytics={fetchAnalytics}
          requestReport={requestReport}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Written by the server.")).toBeInTheDocument();
    expect(requestReport).toHaveBeenCalledWith("sess-9");
    expect(fetchAnalytics).toHaveBeenLastCalledWith("sess-9");
  });

  it("still refetches when the request itself fails", async () => {
    const fetchAnalytics = vi.fn().mockResolvedValue(pending);
    const requestReport = vi.fn().mockRejectedValue(new Error("down"));

    render(
      <MemoryRouter>
        <AnalyticsDashboardContainer
          fetchRecentSession={resolvedRecentSession(SESSION)}
          fetchAnalytics={fetchAnalytics}
          requestReport={requestReport}
        />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/not available for this session right now/)).toBeInTheDocument();
    expect(fetchAnalytics.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

describe("AnalyticsDashboardContainer opening a named session", () => {
  it("loads the session named in ?session= instead of the most recent one", async () => {
    const fetchRecentSession = vi.fn();
    const fetchAnalytics = vi.fn(() =>
      Promise.resolve(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION)
    );

    render(
      <MemoryRouter initialEntries={["/analytics?session=older-session"]}>
        <AnalyticsDashboardContainer
          fetchRecentSession={fetchRecentSession}
          fetchAnalytics={fetchAnalytics}
          requestReport={vi.fn(() => Promise.resolve({ retried: false }))}
        />
      </MemoryRouter>,
    );

    await screen.findByRole("heading", { name: /session summary/i });
    expect(fetchAnalytics).toHaveBeenCalledWith("older-session");
    // The history list links here; looking up "most recent" would quietly
    // show the wrong session.
    expect(fetchRecentSession).not.toHaveBeenCalled();
  });
});
