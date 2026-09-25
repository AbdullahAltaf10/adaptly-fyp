import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import InterventionLog from "./InterventionLog";
import { MOCK_SCENARIOS } from "./mockData";

const { summary, interventions } = MOCK_SCENARIOS.INSIGHT_REPORT_UNAVAILABLE;
const sessionStartIso = summary.timeline_segments[0].started_at;

describe("InterventionLog", () => {
  it("shows a distinct empty state when there are no logged events (not InterventionSection's copy)", () => {
    render(<InterventionLog interventions={[]} sessionStartIso={sessionStartIso} />);

    expect(
      screen.getByText(/nothing logged here.*no individual support events/i)
    ).toBeInTheDocument();
    // Must not collide with InterventionSection's own empty-state wording.
    expect(screen.queryByText(/on track throughout/i)).not.toBeInTheDocument();
  });

  it("also shows the empty state gracefully when interventions is undefined (no backend endpoint yet)", () => {
    render(<InterventionLog interventions={undefined} sessionStartIso={sessionStartIso} />);

    expect(screen.getByText(/nothing logged here/i)).toBeInTheDocument();
  });

  it("lists each event in chronological order with its type, trigger, and outcome", () => {
    render(<InterventionLog interventions={interventions} sessionStartIso={sessionStartIso} />);

    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);

    // First event (offset 1250s = 20m50s) should appear before the second (1420s).
    expect(items[0]).toHaveTextContent("20m 50s into the session");
    expect(items[0]).toHaveTextContent("Simplified text");
    expect(items[0]).toHaveTextContent("Prompted while: Attention drifting");
    expect(items[0]).toHaveTextContent("Helped you get back on track");
    expect(items[0]).toHaveTextContent("Back on track after 45s");

    expect(items[1]).toHaveTextContent("Assistant offered");
    expect(items[1]).toHaveTextContent("Not enough information");
  });

  it("never claims a recovery time for an event that doesn't have one", () => {
    render(<InterventionLog interventions={interventions} sessionStartIso={sessionStartIso} />);

    const items = screen.getAllByRole("listitem");
    expect(items[1]).not.toHaveTextContent(/back on track after/i);
  });

  it("falls back to 'Not available' for elapsed time when no session start is known", () => {
    render(<InterventionLog interventions={interventions} sessionStartIso={null} />);

    expect(screen.getAllByText(/not available into the session/i).length).toBeGreaterThan(0);
  });
});
