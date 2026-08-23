const defaultApiBaseUrl = "http://127.0.0.1:8000";
const allowedEmotionSignals = new Set(["neutral", "confusion", "frustration"]);

function getApiBaseUrl() {
  return (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/$/, "");
}

export async function sendAssistantMessage(payload, options = {}) {
  let response;
  try {
    response = await fetch(`${getApiBaseUrl()}/api/v1/assistant/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: options.signal,
    });
  } catch {
    throw new Error("Unable to reach the assistant service.");
  }

  if (!response.ok) {
    throw new Error("Assistant service returned an error.");
  }

  const data = await response.json();
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
