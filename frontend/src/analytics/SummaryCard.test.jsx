import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SummaryCard from "./SummaryCard";

describe("SummaryCard", () => {
  it("renders a label and formatted value", () => {
    render(<SummaryCard label="Recovery rate" value="100%" />);

    const card = screen.getByRole("group", { name: "Recovery rate" });
    expect(card).toHaveTextContent("Recovery rate");
    expect(card).toHaveTextContent("100%");
  });

  it('renders "Not available" for a missing value, never 0 or false', () => {
    render(<SummaryCard label="Average recovery time" value="Not available" />);

    const card = screen.getByRole("group", { name: "Average recovery time" });
    expect(card).toHaveTextContent("Not available");
    expect(card).not.toHaveTextContent(/^0$/);
    expect(card).not.toHaveTextContent(/^false$/);
  });
});
