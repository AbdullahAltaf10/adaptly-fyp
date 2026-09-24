/**
 * Tests for the Module 8 post-session analytics dashboard shell (Issue #30).
 *
 * Every test injects its own `fetchAnalytics` (resolved/rejected/pending
 * promises) instead of relying on the mock layer's built-in setTimeout, so
 * these stay fast and deterministic without fake timers.
 */

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MOCK_SCENARIOS } from "../analytics/mockData";
import AnalyticsDashboard from "./AnalyticsDashboard";

function resolvedFetcher(scenario) {
  return vi.fn(() => Promise.resolve(scenario));
}

function rejectedFetcher(kind) {
  return vi.fn(() => {
    const error = new Error("mock error");
    error.kind = kind;
    return Promise.reject(error);
  });
}

function pendingFetcher() {
  return vi.fn(() => new Promise(() => {}));
}

function cardValue(label) {
  return within(screen.getByRole("group", { name: label })).getByText(/.+/, {
    selector: "p:nth-of-type(2)",
  });
}

describe("AnalyticsDashboard", () => {
  it("renders the full summary for a normal completed session", async () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-normal", status: "completed" }}
        fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION)}
      />
    );

    expect(await screen.findByText("Intro to Cellular Respiration")).toBeInTheDocument();
    expect(cardValue("Longest focused period")).toHaveTextContent("14m");
    expect(cardValue("Average recovery time")).toHaveTextContent("1m");
    expect(cardValue("Recovery rate")).toHaveTextContent("100%");
    expect(cardValue("Support offered")).toHaveTextContent("1");
    expect(cardValue("Assistant interactions")).toHaveTextContent("2");
    expect(screen.getByText(/AI-written summary/i)).toBeInTheDocument();
  });

  it("shows a calm loading state while analytics are being fetched", () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-normal", status: "completed" }}
        fetchAnalytics={pendingFetcher()}
      />
    );

    expect(screen.getByRole("status")).toHaveTextContent(/loading your session summary/i);
    // No animation classes/keyframes — just static text.
    expect(document.querySelector("[style*='animation']")).toBeNull();
  });

  it("shows an error state when the fetch fails", async () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-normal", status: "completed" }}
        fetchAnalytics={rejectedFetcher("server_error")}
      />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("shows the not-found error copy for an unknown session", async () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "does-not-exist", status: "completed" }}
        fetchAnalytics={rejectedFetcher("not_found")}
      />
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/session not found/i);
  });

  it("shows a positive empty state when no interventions occurred", async () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-no-interventions", status: "completed" }}
        fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.NO_INTERVENTIONS)}
      />
    );

    expect(
      await screen.findByText(/no extra support was offered.*on track throughout/i)
    ).toBeInTheDocument();
    // The support-log's own empty state sits right below the totals section
    // and must read as a distinct, non-duplicated message (Issue #31).
    expect(
      screen.getByText(/nothing logged here.*no individual support events/i)
    ).toBeInTheDocument();
  });

  it("renders the engagement timeline and support log for a session with logged support (Issue #31)", async () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-normal", status: "completed" }}
        fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION)}
      />
    );

    await screen.findByText("Intro to Cellular Respiration");

    expect(screen.getByRole("heading", { name: /session timeline/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /support log/i })).toBeInTheDocument();
    expect(screen.getAllByText(/break suggested/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/helped you get back on track/i)).toBeInTheDocument();
  });

  it('shows "Not available" rather than 0 for missing metrics', async () => {
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-no-webcam", status: "completed" }}
        fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.NO_WEBCAM_DATA)}
      />
    );

    await screen.findByText("Article: Newton's Laws of Motion");

    expect(cardValue("Longest focused period")).toHaveTextContent("Not available");
    expect(cardValue("Average recovery time")).toHaveTextContent("Not available");
    expect(cardValue("Recovery rate")).toHaveTextContent("Not available");

    // None of the "not available" cards render a bare 0 or false instead.
    expect(cardValue("Longest focused period")).not.toHaveTextContent(/^0$|^false$/i);
    expect(cardValue("Average recovery time")).not.toHaveTextContent(/^0$|^false$/i);
    expect(cardValue("Recovery rate")).not.toHaveTextContent(/^0$|^false$/i);
  });

  it("shows the failed insight-report state with a retry affordance", async () => {
    const onRetry = vi.fn();
    render(
      <AnalyticsDashboard
        session={{ sessionId: "session-insight-unavailable", status: "completed" }}
        fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.INSIGHT_REPORT_UNAVAILABLE)}
        onRetryInsightReport={onRetry}
      />
    );

    expect(await screen.findByText(/couldn't prepare a written summary/i)).toBeInTheDocument();
    const retryButton = screen.getByRole("button", { name: /try again/i });
    expect(retryButton).toBeInTheDocument();

    // The failure message must not read as if the numeric analytics failed too.
    expect(screen.getByText(/session numbers above are complete and unaffected/i)).toBeInTheDocument();
  });

  describe("active-session guard", () => {
    it.each(["created", "active", "paused", "abandoned"])(
      "never fetches or renders analytics while status is %s",
      async (status) => {
        const fetcher = resolvedFetcher(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION);

        render(
          <AnalyticsDashboard
            session={{ sessionId: "session-normal", status }}
            fetchAnalytics={fetcher}
          />
        );

        expect(await screen.findByText(/still in progress/i)).toBeInTheDocument();
        expect(fetcher).not.toHaveBeenCalled();
        expect(screen.queryByText("Intro to Cellular Respiration")).not.toBeInTheDocument();
        expect(screen.queryByText(/Engagement summary/i)).not.toBeInTheDocument();
        expect(screen.queryByRole("group", { name: "Longest focused period" })).not.toBeInTheDocument();
      }
    );

    it("renders full analytics once status is completed", async () => {
      render(
        <AnalyticsDashboard
          session={{ sessionId: "session-normal", status: "completed" }}
          fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION)}
        />
      );

      expect(await screen.findByText("Intro to Cellular Respiration")).toBeInTheDocument();
    });
  });

  describe("accessibility basics", () => {
    it("uses one top-level heading and semantic landmark structure", async () => {
      render(
        <AnalyticsDashboard
          session={{ sessionId: "session-complete", status: "completed" }}
          fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.COMPLETE_ANALYTICS)}
        />
      );

      await screen.findByText("Chapter 4: Supply and Demand");

      expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
      expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(1);
      expect(screen.getByRole("main")).toBeInTheDocument();
    });

    it("gives each engagement bar a text alternative instead of relying on color alone", async () => {
      render(
        <AnalyticsDashboard
          session={{ sessionId: "session-normal", status: "completed" }}
          fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION)}
        />
      );

      await screen.findByText("Intro to Cellular Respiration");

      expect(screen.getByRole("img", { name: /^Focused:/ })).toBeInTheDocument();
    });

    it("keeps the retry action as a real, keyboard-reachable button", async () => {
      render(
        <AnalyticsDashboard
          session={{ sessionId: "session-insight-unavailable", status: "completed" }}
          fetchAnalytics={resolvedFetcher(MOCK_SCENARIOS.INSIGHT_REPORT_UNAVAILABLE)}
        />
      );

      const retryButton = await screen.findByRole("button", { name: /try again/i });
      expect(retryButton.tagName).toBe("BUTTON");
    });
  });
});
