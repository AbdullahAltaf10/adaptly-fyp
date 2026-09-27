import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import InsightReport from "./InsightReport";

const pending = { status: "pending", report_text: null };
const generated = { status: "generated", report_text: "You stayed focused." };
const fallback = { status: "fallback_generated", report_text: "Basic summary." };
const failed = { status: "failed", report_text: null };

describe("InsightReport generation on view", () => {
  it("generates once for a pending report and shows the result", async () => {
    const generate = vi.fn().mockResolvedValue({ insightReport: generated, retried: true });
    render(<InsightReport insightReport={pending} generate={generate} sessionId="s1" />);

    expect(await screen.findByText("You stayed focused.")).toBeInTheDocument();
    expect(generate).toHaveBeenCalledTimes(1);
  });

  it("shows a working message while generating", async () => {
    let release;
    const generate = vi.fn(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    render(<InsightReport insightReport={pending} generate={generate} sessionId="s1" />);

    expect(await screen.findByText(/Writing your summary/)).toBeInTheDocument();
    expect(screen.queryByText(/not available for this session/)).not.toBeInTheDocument();
    await act(async () => release({ insightReport: generated, retried: true }));
    expect(screen.queryByText(/Writing your summary/)).not.toBeInTheDocument();
  });

  it("does not generate again on re-render for the same session", async () => {
    const generate = vi
      .fn()
      .mockResolvedValue({ insightReport: pending, retried: false, message: "No key." });
    const { rerender } = render(
      <InsightReport insightReport={pending} generate={generate} sessionId="s1" />,
    );
    await screen.findByText("No key.");
    rerender(<InsightReport insightReport={pending} generate={generate} sessionId="s1" />);
    expect(generate).toHaveBeenCalledTimes(1);
  });

  it("does not generate again when only the generate callback identity changes", async () => {
    const first = vi.fn().mockResolvedValue({ insightReport: pending, retried: false });
    const second = vi.fn().mockResolvedValue({ insightReport: pending, retried: false });
    const { rerender } = render(
      <InsightReport insightReport={pending} generate={first} sessionId="s1" />,
    );
    await waitFor(() => expect(first).toHaveBeenCalledTimes(1));
    rerender(<InsightReport insightReport={pending} generate={second} sessionId="s1" />);
    await screen.findByText(/not available for this session right now/);
    expect(second).not.toHaveBeenCalled();
  });

  it("generates again for a different session", async () => {
    const generate = vi.fn().mockResolvedValue({ insightReport: generated, retried: true });
    const { rerender } = render(
      <InsightReport insightReport={pending} generate={generate} sessionId="s1" />,
    );
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(1));
    rerender(<InsightReport insightReport={pending} generate={generate} sessionId="s2" />);
    await waitFor(() => expect(generate).toHaveBeenCalledTimes(2));
  });

  it("does not generate when the report already exists", () => {
    const generate = vi.fn();
    render(<InsightReport insightReport={generated} generate={generate} sessionId="s1" />);
    expect(generate).not.toHaveBeenCalled();
    expect(screen.getByText("You stayed focused.")).toBeInTheDocument();
  });

  it("says it is unavailable, not preparing, when still pending after an attempt", async () => {
    const generate = vi.fn().mockResolvedValue({ insightReport: pending, retried: false });
    render(<InsightReport insightReport={pending} generate={generate} sessionId="s1" />);
    expect(await screen.findByText(/not available for this session right now/)).toBeInTheDocument();
    expect(screen.queryByText(/preparing a written summary/)).not.toBeInTheDocument();
  });

  it("shows the server's reason when it declines to retry", async () => {
    const generate = vi
      .fn()
      .mockResolvedValue({ insightReport: pending, retried: false, message: "Retry limit reached." });
    render(<InsightReport insightReport={pending} generate={generate} sessionId="s1" />);
    expect(await screen.findByText("Retry limit reached.")).toBeInTheDocument();
  });

  it("shows an error notice when generate throws", async () => {
    const generate = vi.fn().mockRejectedValue(new Error("net"));
    render(<InsightReport insightReport={pending} generate={generate} sessionId="s1" />);
    expect(await screen.findByText(/could not reach the server/)).toBeInTheDocument();
  });

  it("offers Try again on failed and runs generate on click", async () => {
    const generate = vi.fn().mockResolvedValue({ insightReport: generated, retried: true });
    render(<InsightReport insightReport={failed} generate={generate} sessionId="s1" />);
    expect(generate).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("You stayed focused.")).toBeInTheDocument();
  });

  it("offers a fuller summary for a fallback report", async () => {
    const generate = vi.fn().mockResolvedValue({ insightReport: generated, retried: true });
    render(<InsightReport insightReport={fallback} generate={generate} sessionId="s1" />);
    await userEvent.click(screen.getByRole("button", { name: /fuller written summary/ }));
    expect(await screen.findByText("You stayed focused.")).toBeInTheDocument();
  });

  it("without generate behaves as before: preparing text and onRetry", async () => {
    const onRetry = vi.fn();
    const { rerender } = render(<InsightReport insightReport={pending} />);
    expect(screen.getByText(/preparing a written summary/)).toBeInTheDocument();
    rerender(<InsightReport insightReport={failed} onRetry={onRetry} />);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
