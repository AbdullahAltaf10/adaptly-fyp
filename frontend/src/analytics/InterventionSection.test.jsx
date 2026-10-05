import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import InterventionSection from "./InterventionSection";

describe("InterventionSection with no support offered", () => {
  it("claims 'on track' only when engagement was measured", () => {
    render(<InterventionSection interventionMetrics={{ total_count: 0 }} engagementMeasured />);
    expect(screen.getByText(/you were on track throughout/i)).toBeInTheDocument();
  });

  it("does not claim 'on track' when nothing was measured", () => {
    render(<InterventionSection interventionMetrics={{ total_count: 0 }} engagementMeasured={false} />);
    expect(screen.getByText(/no extra support was offered during this session\./i)).toBeInTheDocument();
    expect(screen.queryByText(/on track/i)).not.toBeInTheDocument();
  });
});
