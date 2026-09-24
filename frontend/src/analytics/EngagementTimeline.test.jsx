import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import EngagementTimeline from "./EngagementTimeline";
import { MOCK_SCENARIOS } from "./mockData";

const { summary, interventions } = MOCK_SCENARIOS.NORMAL_COMPLETED_SESSION;

describe("EngagementTimeline", () => {
  it("shows the not-enough-data message when there are no segments", () => {
    render(
      <EngagementTimeline segments={[]} interventions={[]} totalDurationSeconds={0} />
    );

    expect(
      screen.getByText(/not enough data was collected to show a timeline/i)
    ).toBeInTheDocument();
  });

  it("renders each real segment with a time-ranged text alternative", () => {
    render(
      <EngagementTimeline
        segments={summary.timeline_segments}
        interventions={interventions}
        totalDurationSeconds={summary.duration_seconds}
      />
    );

    // The first segment: focused, 0:00 to 14:00.
    expect(
      screen.getByRole("img", { name: /^Focused, 0s to 14m \(14m\)$/ })
    ).toBeInTheDocument();
  });

  it("fills an unmeasured gap between segments as its own unknown block, never stretching a neighbor", () => {
    const sparseSegments = [
      { started_at: "2026-01-01T00:00:00.000Z", ended_at: "2026-01-01T00:01:00.000Z", state: "focused" },
      // Gap: 60s-180s is not covered by any segment.
      { started_at: "2026-01-01T00:03:00.000Z", ended_at: "2026-01-01T00:04:00.000Z", state: "struggling" },
    ];

    render(
      <EngagementTimeline
        segments={sparseSegments}
        interventions={[]}
        totalDurationSeconds={240}
      />
    );

    // The gap between the two real segments becomes its own "Not measured" block.
    expect(
      screen.getByRole("img", { name: /^Not measured, 1m to 3m \(2m\)$/ })
    ).toBeInTheDocument();
    // And the trailing time after the last segment (180s+60s=240s covers it exactly here,
    // so add a case with a real trailing gap too).
  });

  it("fills a trailing gap after the last segment when segments end before the session does", () => {
    const segments = [
      { started_at: "2026-01-01T00:00:00.000Z", ended_at: "2026-01-01T00:01:00.000Z", state: "focused" },
    ];

    render(
      <EngagementTimeline segments={segments} interventions={[]} totalDurationSeconds={120} />
    );

    expect(
      screen.getByRole("img", { name: /^Not measured, 1m to 2m \(1m\)$/ })
    ).toBeInTheDocument();
  });

  it("marks a point on the timeline for each intervention", () => {
    render(
      <EngagementTimeline
        segments={summary.timeline_segments}
        interventions={interventions}
        totalDurationSeconds={summary.duration_seconds}
        sessionStartIso={summary.timeline_segments[0].started_at}
      />
    );

    expect(screen.getByRole("img", { name: /^Support offered at 15m$/ })).toBeInTheDocument();
  });

  it("notes in the text list when support was offered during a segment", () => {
    render(
      <EngagementTimeline
        segments={summary.timeline_segments}
        interventions={interventions}
        totalDurationSeconds={summary.duration_seconds}
        sessionStartIso={summary.timeline_segments[0].started_at}
      />
    );

    expect(screen.getByText(/support offered during this stretch/i)).toBeInTheDocument();
  });

  it("never renders an unknown segment as if it were focused", () => {
    const sparseSegments = [
      { started_at: "2026-01-01T00:00:00.000Z", ended_at: "2026-01-01T00:01:00.000Z", state: "focused" },
    ];

    render(
      <EngagementTimeline segments={sparseSegments} interventions={[]} totalDurationSeconds={120} />
    );

    expect(screen.queryByRole("img", { name: /^Focused, 1m to 2m/ })).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: /^Not measured, 1m to 2m/ })).toBeInTheDocument();
  });
});
