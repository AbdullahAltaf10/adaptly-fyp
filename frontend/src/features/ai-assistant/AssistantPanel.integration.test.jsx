import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AssistantPanel } from "./AssistantPanel";

const contextA = {
  session_id: "session-001",
  content_id: "content-001",
  current_chunk: {
    chunk_id: "chunk-gradient-descent",
    section_title: "Gradient Descent",
    text: "Gradient descent iteratively reduces a loss function.",
  },
  content_context: { title: "Machine Learning", content_type: "pdf", language: "en" },
  session_context: { status: "active", current_chunk_id: "chunk-gradient-descent" },
  learner_preferences: { preferred_explanation_mode: "simple" },
};

const contextB = {
  ...contextA,
  current_chunk: {
    chunk_id: "chunk-neural-networks",
    section_title: "Neural Networks",
    text: "Neural networks learn through connected layers.",
  },
  session_context: { status: "active", current_chunk_id: "chunk-neural-networks" },
};

function response(answer, suggestedQuestions = ["Backend suggestion one?", "Backend suggestion two?", "Backend suggestion three?"]) {
  return {
    answer,
    suggested_questions: suggestedQuestions,
    emotion_signal: "neutral",
    used_context: true,
    response_mode: "text",
    session_id: "session-001",
    content_id: "content-001",
    chunk_id: "chunk-gradient-descent",
  };
}

async function ask(user, question) {
  await user.type(screen.getByLabelText("Ask Adaptly a question"), question);
  await user.click(screen.getByRole("button", { name: "Send" }));
}

describe("AssistantPanel API integration", () => {
  it("sends active context and renders backend-provided suggested questions", async () => {
    const user = userEvent.setup();
    const apiClient = vi.fn().mockResolvedValue(
      response("Gradient descent reduces loss.", ["Explain gradient descent simply?", "Give a gradient descent example?", "Why use gradient descent?"]),
    );
    render(<AssistantPanel apiClient={apiClient} studyContext={contextA} />);

    await ask(user, "Explain gradient descent.");
    await screen.findByText("Gradient descent reduces loss.");

    expect(apiClient).toHaveBeenCalledWith({
      ...contextA,
      question: "Explain gradient descent.",
      previous_messages: [],
    });
    expect(screen.getByRole("button", { name: "Give a gradient descent example?" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Give a gradient descent example?" }));
    expect(screen.getByLabelText("Ask Adaptly a question")).toHaveValue("Give a gradient descent example?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(apiClient).toHaveBeenCalledTimes(2));
    expect(apiClient.mock.calls[1][0]).toMatchObject({
      ...contextA,
      question: "Give a gradient descent example?",
      previous_messages: [
        { role: "user", message: "Explain gradient descent." },
        { role: "assistant", message: "Gradient descent reduces loss." },
      ],
    });
  });

  it("forwards completed history through four consecutive questions without duplication", async () => {
    const user = userEvent.setup();
    const apiClient = vi
      .fn()
      .mockResolvedValueOnce(response("Answer one."))
      .mockResolvedValueOnce(response("Answer two."))
      .mockResolvedValueOnce(response("Answer three."))
      .mockResolvedValueOnce(response("Answer four."));
    render(<AssistantPanel apiClient={apiClient} studyContext={contextA} />);

    await ask(user, "Explain gradient descent.");
    await screen.findByText("Answer one.");
    await ask(user, "Can you explain that more simply?");
    await screen.findByText("Answer two.");
    await ask(user, "Can you give me an example?");
    await screen.findByText("Answer three.");
    await ask(user, "Why is it useful?");
    await screen.findByText("Answer four.");

    expect(apiClient.mock.calls[3][0].previous_messages).toEqual([
      { role: "user", message: "Explain gradient descent." },
      { role: "assistant", message: "Answer one." },
      { role: "user", message: "Can you explain that more simply?" },
      { role: "assistant", message: "Answer two." },
      { role: "user", message: "Can you give me an example?" },
      { role: "assistant", message: "Answer three." },
    ]);
  });

  it("uses the newly supplied current chunk after a section switch", async () => {
    const user = userEvent.setup();
    const apiClient = vi
      .fn()
      .mockResolvedValueOnce(response("Gradient descent answer."))
      .mockResolvedValueOnce(response("Neural networks answer."));
    const view = render(<AssistantPanel apiClient={apiClient} studyContext={contextA} />);

    await ask(user, "Explain this simply.");
    await screen.findByText("Gradient descent answer.");
    view.rerender(<AssistantPanel apiClient={apiClient} studyContext={contextB} />);

    await ask(user, "What is this?");
    await screen.findByText("Neural networks answer.");
    await waitFor(() => expect(apiClient).toHaveBeenCalledTimes(2));
    expect(apiClient.mock.calls[1][0].session_id).toBe("session-001");
    expect(apiClient.mock.calls[1][0].content_id).toBe("content-001");
    expect(apiClient.mock.calls[1][0].current_chunk).toEqual(contextB.current_chunk);
  });
});
