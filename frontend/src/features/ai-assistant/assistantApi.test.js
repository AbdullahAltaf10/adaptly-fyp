import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../api/client", () => ({
  default: { post: vi.fn() },
}));

import api from "../../api/client";
import { sendAssistantMessage } from "./assistantApi";

const payload = {
  question: "Explain gradient descent.",
  session_id: "session-001",
  content_id: "content-001",
  current_chunk: {
    chunk_id: "chunk-001",
    text: "Gradient descent reduces loss.",
    section_title: "Gradient Descent",
  },
  previous_messages: [],
  input_mode: "typed",
};

const validResponse = {
  answer: "Gradient descent reduces loss step by step.",
  suggested_questions: ["Explain it simply?", "Give an example?", "Why is it useful?"],
  emotion_signal: "neutral",
  used_context: true,
  response_mode: "text",
  session_id: "session-001",
  content_id: "content-001",
  chunk_id: "chunk-001",
};

afterEach(() => {
  vi.clearAllMocks();
});

describe("sendAssistantMessage", () => {
  it("posts through the shared api client (which attaches auth) with input_mode included", async () => {
    api.post.mockResolvedValue({ data: validResponse });

    await expect(sendAssistantMessage(payload)).resolves.toEqual(validResponse);
    expect(api.post).toHaveBeenCalledWith(
      "/assistant/messages",
      payload,
      { signal: undefined },
    );
    expect(api.post.mock.calls[0][1].input_mode).toBe("typed");
  });

  it("forwards an abort signal through to the shared client", async () => {
    api.post.mockResolvedValue({ data: validResponse });
    const controller = new AbortController();

    await sendAssistantMessage(payload, { signal: controller.signal });

    expect(api.post).toHaveBeenCalledWith(
      "/assistant/messages",
      payload,
      { signal: controller.signal },
    );
  });

  it("safely rejects network and malformed-response failures", async () => {
    api.post.mockRejectedValue(new Error("Network Error"));
    await expect(sendAssistantMessage(payload)).rejects.toThrow("Unable to reach the assistant service.");

    api.post.mockResolvedValue({ data: { answer: "Only text" } });
    await expect(sendAssistantMessage(payload)).rejects.toThrow("Assistant service returned an invalid response.");
  });

  it("distinguishes a backend error status from an unreachable backend", async () => {
    const httpError = new Error("Request failed with status code 502");
    httpError.response = { status: 502 };
    api.post.mockRejectedValue(httpError);

    await expect(sendAssistantMessage(payload)).rejects.toThrow("Assistant service returned an error.");
  });
});
