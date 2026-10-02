/**
 * The signed-in home screen.
 *
 * "/" used to redirect straight to /library with nothing of its own - a
 * returning learner had no sense of their own progress before the first
 * click. Every stat here comes from GET /api/analytics/sessions, injected as
 * `loadHistory` so nothing here touches the network.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const authState = { profile: { display_name: "Sara" }, currentUser: { email: "sara@x.com" } };
vi.mock("../auth/AuthContext", () => ({ useAuth: () => authState }));

import DashboardPage from "./DashboardPage";

const HISTORY = {
  items: [
    {
      session_id: "s-1",
      completed_at: "2026-09-27T09:00:00Z",
      duration_seconds: 900,
      content_id: "c-1",
      engagement_distribution: { focused: { percentage: 72 } },
    },
    {
      session_id: "s-2",
      completed_at: "2026-09-26T09:00:00Z",
      duration_seconds: 600,
      content_id: "c-2",
      engagement_distribution: { focused: { percentage: 50 } },
    },
  ],
  pagination: { limit: 30, offset: 0, returned_count: 2, total_count: 2 },
};

function draw(loadHistory) {
  return render(
    <MemoryRouter>
      <DashboardPage loadHistory={loadHistory} />
    </MemoryRouter>
  );
}

describe("DashboardPage", () => {
  it("greets the learner by name", async () => {
    draw(vi.fn().mockResolvedValue(HISTORY));

    expect(await screen.findByText(/welcome, sara/i)).toBeInTheDocument();
  });

  it("falls back to the account email when there is no display name", async () => {
    authState.profile = null;
    draw(vi.fn().mockResolvedValue(HISTORY));

    expect(await screen.findByText(/welcome, sara@x\.com/i)).toBeInTheDocument();
    authState.profile = { display_name: "Sara" };
  });

  it("shows the four stat tiles computed from history", async () => {
    draw(vi.fn().mockResolvedValue(HISTORY));

    await screen.findByText(/your progress/i);
    expect(screen.getByRole("group", { name: "Sessions this week" })).toHaveTextContent("2");
    expect(screen.getByRole("group", { name: "Content covered" })).toHaveTextContent("2");
  });

  it("lists recent sessions, each linking to its own analytics", async () => {
    draw(vi.fn().mockResolvedValue(HISTORY));

    await screen.findByText(/recent sessions/i);
    const links = screen.getAllByRole("link", { name: /2026/ });
    expect(links[0]).toHaveAttribute("href", "/analytics?session=s-1");
    expect(links[1]).toHaveAttribute("href", "/analytics?session=s-2");
  });

  it("invites a first session when there is no history, rather than showing empty stats as if normal", async () => {
    draw(vi.fn().mockResolvedValue({ items: [], pagination: { total_count: 0 } }));

    expect(await screen.findByText(/nothing here yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /add a document/i })).toHaveAttribute(
      "href",
      "/library/new"
    );
  });

  it("shows an error state rather than a blank dashboard when history fails to load", async () => {
    draw(vi.fn().mockRejectedValue(Object.assign(new Error("down"), { kind: "server_error" })));

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
  });

  it("always offers a way to start a new session", async () => {
    draw(vi.fn().mockResolvedValue(HISTORY));

    expect(screen.getByRole("link", { name: /start a new session/i })).toHaveAttribute(
      "href",
      "/library"
    );
  });
});
