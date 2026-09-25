import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AssistantPanel } from "./AssistantPanel";


describe("AssistantPanel", () => {
  it("renders a calm empty state and suggested questions", () => {
    render(<AssistantPanel apiClient={vi.fn()} />);

    expect(screen.getByText("Ask me anything about the section you're studying.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Can you explain this more simply?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Can you give me an example?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Why is this important?" })).toBeInTheDocument();
  });

  it("places a suggested question in the input", async () => {
    const user = userEvent.setup();
    render(<AssistantPanel apiClient={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Can you give me an example?" }));

    expect(screen.getByLabelText("Ask Adaptly a question")).toHaveValue("Can you give me an example?");
  });

  it("does not submit an empty question", async () => {
    const apiClient = vi.fn();
    render(<AssistantPanel apiClient={apiClient} />);

    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(apiClient).not.toHaveBeenCalled();
  });

  it("shows learner, loading, and assistant messages", async () => {
    const user = userEvent.setup();
    let resolveRequest;
    const apiClient = vi.fn(() => new Promise((resolve) => { resolveRequest = resolve; }));
    render(<AssistantPanel apiClient={apiClient} />);

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "What is gradient descent?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(screen.getByText("What is gradient descent?")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Adaptly is thinking...");
    resolveRequest({ answer: "It is a way to reduce error step by step." });

    expect(await screen.findByText("It is a way to reduce error step by step.")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("forwards visible conversation as previous messages", async () => {
    const user = userEvent.setup();
    const apiClient = vi
      .fn()
      .mockResolvedValueOnce({ answer: "It is an optimization method." })
      .mockResolvedValueOnce({ answer: "It helps improve the model." });
    render(<AssistantPanel apiClient={apiClient} />);

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "What is gradient descent?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("It is an optimization method.");

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Why is that useful?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(apiClient).toHaveBeenCalledTimes(2));
    expect(apiClient.mock.calls[1][0].previous_messages).toEqual([
      { role: "user", message: "What is gradient descent?" },
      { role: "assistant", message: "It is an optimization method." },
    ]);
  });

  it("shows a safe error and retries without duplicating the learner message", async () => {
    const user = userEvent.setup();
    const apiClient = vi
      .fn()
      .mockRejectedValueOnce(new Error("internal details"))
      .mockResolvedValueOnce({ answer: "Recovered response." });
    render(<AssistantPanel apiClient={apiClient} />);

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Please explain this.");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "I couldn't get a response right now. Please try again.",
    );
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Recovered response.")).toBeInTheDocument();
    expect(apiClient).toHaveBeenCalledTimes(2);
    expect(apiClient.mock.calls[1][0].previous_messages).toEqual([]);
    expect(screen.getAllByText("Please explain this.")).toHaveLength(1);
  });
});
