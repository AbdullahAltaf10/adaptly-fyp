import api from "../../api/client";

const allowedEmotionSignals = new Set(["neutral", "confusion", "frustration"]);

// Uses the shared axios client (same one Module 3/4's frontend code uses)
// instead of a raw fetch, because its interceptor is what attaches the
// Firebase ID token this endpoint now requires (Issue #34). Switching this
// import is the only frontend change needed for auth - AssistantPanel.jsx
// never has to know a token exists.
function validQuestions(data) {
  return Array.isArray(data?.suggested_questions)
    && data.suggested_questions.length === 3
    && data.suggested_questions.every((question) => typeof question === "string" && question.trim());
}

/**
 * Questions worth asking about the paragraph the learner is on.
 *
 * Asked whenever the active paragraph changes, so the suggestions describe what
 * is on screen instead of staying the same three generic questions all session.
 * The backend answers locally (no model call), so this is cheap enough to do on
 * every scroll. Resolves to the three strings, or rejects - the panel keeps its
 * fallback questions in that case rather than showing nothing.
 */
export async function fetchSuggestedQuestions(currentChunk, options = {}) {
  const response = await api.post(
    "/assistant/suggestions",
    {
      current_chunk: {
        chunk_id: currentChunk.chunk_id,
        text: currentChunk.text,
        ...(currentChunk.section_title ? { section_title: currentChunk.section_title } : {}),
      },
    },
    { signal: options.signal }
  );
  if (!validQuestions(response?.data)) {
    throw new Error("Assistant service returned invalid suggestions.");
  }
  return response.data.suggested_questions;
}

/**
 * The learner's own persistent assistant conversation, newest first as the
 * server returns it - reversed here so the panel can append to it in
 * chronological order the same way it already appends new messages.
 */
export async function fetchAssistantHistory(options = {}) {
  const response = await api.get("/assistant/history", { signal: options.signal });
  if (!Array.isArray(response?.data?.messages)) {
    throw new Error("Assistant service returned an invalid history.");
  }
  return [...response.data.messages].reverse();
}

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
