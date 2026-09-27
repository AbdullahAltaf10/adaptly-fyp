/**
 * Per-type recovery time on the dashboard — scope 6.8's "the average recovery
 * time after each type of response".
 *
 * The key-numbers row already showed one average for the whole session. These
 * tests pin that each kind of support now reports its own, that a summary
 * stored before the breakdown existed still renders, and that a type which
 * never recovered says nothing rather than showing a misleading zero.
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import InterventionSection from "./InterventionSection";

const interventionMetrics = {
  total_count: 3,
  effective_count: 2,
  ineffective_count: 1,
  unknown_outcome_count: 0,
  by_type: [
    { intervention_type: "bullet_summary", total_count: 2, effectiveness_rate: 1 },
    { intervention_type: "break_suggestion", total_count: 1, effectiveness_rate: 0 },
  ],
};

const recoveryMetrics = {
  eligible_intervention_count: 3,
  recovered_intervention_count: 2,
  recovery_rate: 0.67,
  average_recovery_time_seconds: 60,
  by_type: [
    {
      intervention_type: "bullet_summary",
      eligible_intervention_count: 2,
      recovered_intervention_count: 2,
      recovery_rate: 1,
      average_recovery_time_seconds: 30,
    },
    {
      intervention_type: "break_suggestion",
      eligible_intervention_count: 1,
      recovered_intervention_count: 0,
      recovery_rate: 0,
      average_recovery_time_seconds: null,
    },
  ],
};

describe("InterventionSection recovery time per type", () => {
  it("reports how long each kind of support took to land", () => {
    render(
      <InterventionSection
        interventionMetrics={interventionMetrics}
        recoveryMetrics={recoveryMetrics}
      />
    );

    const summaryLine = screen
      .getAllByRole("listitem")
      .find((item) => item.textContent.includes("Quick summary"));
    expect(summaryLine).toHaveTextContent(/back on track in about/);
    expect(summaryLine).toHaveTextContent(/30/);
  });

  it("says nothing about timing for a type that never recovered", () => {
    render(
      <InterventionSection
        interventionMetrics={interventionMetrics}
        recoveryMetrics={recoveryMetrics}
      />
    );

    const breakLine = screen
      .getAllByRole("listitem")
      .find((item) => item.textContent.includes("Break suggested"));
    expect(breakLine).toBeDefined();
    expect(breakLine).not.toHaveTextContent(/back on track in about/);
  });

  it("renders a summary stored before the breakdown existed", () => {
    const { by_type: _omitted, ...withoutBreakdown } = recoveryMetrics;

    render(
      <InterventionSection
        interventionMetrics={interventionMetrics}
        recoveryMetrics={withoutBreakdown}
      />
    );

    expect(screen.getByText(/Support was offered 3 times/)).toBeInTheDocument();
    expect(screen.queryByText(/back on track in about/)).not.toBeInTheDocument();
  });

  it("renders with no recovery metrics at all", () => {
    render(<InterventionSection interventionMetrics={interventionMetrics} />);

    expect(screen.getByText(/Support was offered 3 times/)).toBeInTheDocument();
  });

  it("still shows the empty state when no support was offered", () => {
    render(
      <InterventionSection
        interventionMetrics={{ total_count: 0 }}
        recoveryMetrics={recoveryMetrics}
      />
    );

    expect(screen.getByText(/you were on track throughout/)).toBeInTheDocument();
  });
});
