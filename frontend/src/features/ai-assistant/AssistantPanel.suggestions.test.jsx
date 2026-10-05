/**
 * The suggested questions follow the paragraph on screen.
 *
 * They used to be the same three generic questions for the whole session. The
 * details worth pinning are the ordering ones: a slow fetch for the paragraph
 * the learner has already scrolled past, or one arriving after an answer that
 * brought its own suggestions, must not overwrite what is now on screen.
 */

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({ default: { post: vi.fn() } }));

import { AssistantPanel } from "./AssistantPanel";
import { fallbackStudyContext } from "./demoStudyContext";

const contextFor = (chunkId, text) => ({
  ...fallbackStudyContext,
  current_chunk: { chunk_id: chunkId, text, section_title: null },
});

const questionsFor = (topic) => [
  `About ${topic}: what does it mean?`,
  `About ${topic}: an example?`,
  `About ${topic}: why does it matter?`,
];

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("AssistantPanel: suggestions about the current paragraph", () => {
  it("shows the generic questions first, then ones about this paragraph", async () => {
    const suggestionsClient = vi.fn().mockResolvedValue(questionsFor("gradients"));
    render(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("1", "Gradients point uphill.")}
      />
    );

    expect(screen.getByRole("button", { name: "Why is this important?" })).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: "About gradients: an example?" })
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Why is this important?" })).toBeNull();
  });

  it("asks the server about the paragraph that is actually on screen", async () => {
    const suggestionsClient = vi.fn().mockResolvedValue(questionsFor("x"));
    render(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("7", "Seventh paragraph text.")}
      />
    );

    await waitFor(() => expect(suggestionsClient).toHaveBeenCalled());
    expect(suggestionsClient.mock.calls[0][0]).toMatchObject({
      chunk_id: "7",
      text: "Seventh paragraph text.",
    });
  });

  it("asks again when the learner moves to a different paragraph", async () => {
    const suggestionsClient = vi
      .fn()
      .mockResolvedValueOnce(questionsFor("first"))
      .mockResolvedValueOnce(questionsFor("second"));
    const { rerender } = render(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("1", "First paragraph.")}
      />
    );
    await screen.findByRole("button", { name: "About first: an example?" });

    rerender(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("2", "Second paragraph.")}
      />
    );

    expect(
      await screen.findByRole("button", { name: "About second: an example?" })
    ).toBeInTheDocument();
    expect(suggestionsClient).toHaveBeenCalledTimes(2);
  });

  it("keeps the generic questions when the server cannot be reached", async () => {
    const suggestionsClient = vi.fn().mockRejectedValue(new Error("offline"));
    render(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("1", "Anything.")}
      />
    );

    await waitFor(() => expect(suggestionsClient).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: "Why is this important?" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("does not let a slow reply for the OLD paragraph replace the new one's", async () => {
    const slow = deferred();
    const suggestionsClient = vi
      .fn()
      .mockReturnValueOnce(slow.promise)
      .mockResolvedValueOnce(questionsFor("second"));
    const { rerender } = render(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("1", "First paragraph.")}
      />
    );

    rerender(
      <AssistantPanel
        apiClient={vi.fn()}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("2", "Second paragraph.")}
      />
    );
    await screen.findByRole("button", { name: "About second: an example?" });

    // Inside act so the late reply is actually applied (or not) before we look.
    await act(async () => {
      slow.resolve(questionsFor("first"));
      await slow.promise;
    });

    expect(screen.getByRole("button", { name: "About second: an example?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About first: an example?" })).toBeNull();
  });

  it("does not let a late paragraph reply replace suggestions an answer brought", async () => {
    const user = userEvent.setup();
    const slow = deferred();
    const suggestionsClient = vi.fn().mockReturnValue(slow.promise);
    const apiClient = vi.fn().mockResolvedValue({
      answer: "Here is an answer.",
      suggested_questions: ["From the answer one?", "From the answer two?", "From the answer three?"],
      emotion_signal: "neutral",
    });
    render(
      <AssistantPanel
        apiClient={apiClient}
        suggestionsClient={suggestionsClient}
        studyContext={contextFor("1", "First paragraph.")}
      />
    );

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Explain?");
    await user.click(screen.getByRole("button", { name: /send/i }));
    await screen.findByRole("button", { name: "From the answer one?" });

    await act(async () => {
      slow.resolve(questionsFor("stale"));
      await slow.promise;
    });

    expect(screen.getByRole("button", { name: "From the answer one?" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "About stale: an example?" })).toBeNull();
  });
});
