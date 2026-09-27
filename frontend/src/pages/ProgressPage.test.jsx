/**
 * The progress page — session history and the learning profile.
 *
 * Both were produced by the backend and shown nowhere: the history endpoint
 * and its client wrapper were unused, and the learning profile was being built
 * (#97) and acted on (#98) without the learner ever seeing it.
 *
 * Every test injects its own loaders, so nothing here touches the network.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import ProgressPage from "./ProgressPage";

const profileWithData = {
  sessions_analyzed: 4,
  average_focus_percentage: 62.5,
  average_session_duration_seconds: 1800,
  focus_trend: "improving",
  recovery_trend: "insufficient_data",
  effective_support_methods: [
    {
      intervention_type: "bullet_summary",
      times_used: 4,
      effective_count: 3,
      effectiveness_rate: 0.75,
    },
  ],
  recurring_difficulty_areas: [
    { area_key: "gradient-descent", label: "Gradient descent", session_count: 2, occurrence_count: 5 },
  ],
};

const emptyProfile = {
  sessions_analyzed: 0,
  average_focus_percentage: null,
  average_session_duration_seconds: null,
  focus_trend: "insufficient_data",
  recovery_trend: "insufficient_data",
  effective_support_methods: [],
  recurring_difficulty_areas: [],
};

const history = {
  items: [
    {
      session_id: "s-1",
      completed_at: "2026-09-20T10:30:00Z",
      duration_seconds: 1500,
      engagement_distribution: { focused_percentage: 70 },
    },
    {
      session_id: "s-2",
      completed_at: "2026-09-18T09:00:00Z",
      duration_seconds: 900,
      engagement_distribution: { focused_percentage: 40 },
    },
  ],
  pagination: { limit: 20, offset: 0, returned_count: 2, total_count: 2 },
};

function renderPage({ profile = profileWithData, sessions = history } = {}) {
  return render(
    <MemoryRouter>
      <ProgressPage
        loadProfile={vi.fn(() => Promise.resolve(profile))}
        loadHistory={vi.fn(() => Promise.resolve(sessions))}
      />
    </MemoryRouter>
  );
}

describe("ProgressPage", () => {
  it("lists the learner's finished sessions", async () => {
    renderPage();

    expect(await screen.findByText(/Your sessions/)).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
  });

  it("links each session to its own analytics, not to the most recent one", async () => {
    renderPage();

    await screen.findByText(/Your sessions/);
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/analytics?session=s-1");
    expect(links[1]).toHaveAttribute("href", "/analytics?session=s-2");
  });

  it("shows what the profile has learned", async () => {
    renderPage();

    expect(await screen.findByText(/Based on 4 finished sessions/)).toBeInTheDocument();
    expect(screen.getByText(/Focus over time: getting easier/)).toBeInTheDocument();
    expect(screen.getByText(/Quick summary/)).toBeInTheDocument();
    expect(screen.getByText(/Gradient descent/)).toBeInTheDocument();
  });

  it("says nothing about a trend it does not have enough data for", async () => {
    renderPage();

    await screen.findByText(/Based on 4 finished sessions/);
    expect(screen.queryByText(/Getting back on track/)).not.toBeInTheDocument();
  });

  it("explains an empty profile instead of showing zeros", async () => {
    renderPage({ profile: emptyProfile, sessions: { items: [] } });

    expect(await screen.findByText(/Nothing yet/)).toBeInTheDocument();
    expect(screen.queryByText(/Based on 0/)).not.toBeInTheDocument();
  });

  it("invites a first session when there is no history", async () => {
    renderPage({ profile: emptyProfile, sessions: { items: [] } });

    expect(await screen.findByText(/No finished sessions yet/)).toBeInTheDocument();
  });

  it("still shows the sessions when the profile fails to load", async () => {
    render(
      <MemoryRouter>
        <ProgressPage
          loadProfile={vi.fn(() => Promise.reject(Object.assign(new Error("x"), { kind: "server_error" })))}
          loadHistory={vi.fn(() => Promise.resolve(history))}
        />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Your sessions/)).toBeInTheDocument();
    expect(screen.getAllByRole("link")).toHaveLength(2);
  });

  it("still shows the profile when the history fails to load", async () => {
    render(
      <MemoryRouter>
        <ProgressPage
          loadProfile={vi.fn(() => Promise.resolve(profileWithData))}
          loadHistory={vi.fn(() => Promise.reject(Object.assign(new Error("x"), { kind: "server_error" })))}
        />
      </MemoryRouter>
    );

    expect(await screen.findByText(/Based on 4 finished sessions/)).toBeInTheDocument();
  });

  it("has exactly one main landmark", async () => {
    const { container } = renderPage();

    await screen.findByText(/Your sessions/);
    expect(container.querySelectorAll("main, [role='main']")).toHaveLength(1);
  });
});
