import { afterEach, describe, expect, it, vi } from "vitest";

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
  vi.unstubAllGlobals();
});

describe("sendAssistantMessage", () => {
  it("uses the single assistant endpoint with the provided integration context", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => validResponse });
    vi.stubGlobal("fetch", fetchMock);

    await expect(sendAssistantMessage(payload)).resolves.toEqual(validResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://127.0.0.1:8000/api/v1/assistant/messages",
      expect.objectContaining({
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }),
    );
  });

  it("safely rejects network and malformed-response failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("connection refused")));
    await expect(sendAssistantMessage(payload)).rejects.toThrow("Unable to reach the assistant service.");

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ answer: "Only text" }) }));
    await expect(sendAssistantMessage(payload)).rejects.toThrow("Assistant service returned an invalid response.");
  });
});
