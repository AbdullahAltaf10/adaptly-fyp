import api from "../../api/client";

const allowedEmotionSignals = new Set(["neutral", "confusion", "frustration"]);

// Uses the shared axios client (same one Module 3/4's frontend code uses)
// instead of a raw fetch, because its interceptor is what attaches the
// Firebase ID token this endpoint now requires (Issue #34). Switching this
// import is the only frontend change needed for auth - AssistantPanel.jsx
// never has to know a token exists.
export async function sendAssistantMessage(payload, options = {}) {
  let response;
  try {
    response = await api.post("/assistant/messages", payload, { signal: options.signal });
  } catch (error) {
    // Mirrors client.js's own classifyError split: no `response` at all means
    // the request never reached the backend (down, CORS, timeout); a present
    // `response` means the backend answered with a non-2xx status.
    if (!error.response) {
      throw new Error("Unable to reach the assistant service.");
    }
    throw new Error("Assistant service returned an error.");
  }

  const data = response.data;
  const hasSuggestedQuestions = Array.isArray(data?.suggested_questions)
    && data.suggested_questions.length === 3
    && data.suggested_questions.every((question) => typeof question === "string" && question.trim());
  if (
    !data
    || typeof data.answer !== "string"
    || !data.answer.trim()
    || !hasSuggestedQuestions
    || !allowedEmotionSignals.has(data.emotion_signal)
  ) {
    throw new Error("Assistant service returned an invalid response.");
  }
  return data;
}
