import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import EngagementSection from "./EngagementSection";

describe("EngagementSection", () => {
  it("shows the empty-state message, not a 100% 'Not measured' bar, when nothing was measured", () => {
    render(
      <EngagementSection
        distribution={{
          focused: { percentage: 0 },
          recovered: { percentage: 0 },
          drifting: { percentage: 0 },
          struggling: { percentage: 0 },
          fatigued: { percentage: 0 },
          unknown: { percentage: 100 },
        }}
      />
    );
    expect(
      screen.getByText(/not enough data was collected to show an engagement breakdown/i)
    ).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /not measured: 100%/i })).not.toBeInTheDocument();
  });

  it("still shows the breakdown when there is measured data", () => {
    render(
      <EngagementSection
        distribution={{
          focused: { percentage: 60 },
          recovered: { percentage: 0 },
          drifting: { percentage: 30 },
          struggling: { percentage: 10 },
          fatigued: { percentage: 0 },
          unknown: { percentage: 0 },
        }}
      />
    );
    expect(screen.getByText(/you were focused for about 60%/i)).toBeInTheDocument();
  });
});
