// Temporary standalone fallback until the study-session/content modules provide
// active context to App. AssistantPanel accepts `studyContext` from that future
// integration boundary and does not generate IDs itself.
export const fallbackStudyContext = {
  session_id: "demo-session-001",
  content_id: "demo-content-001",
  current_chunk: {
    chunk_id: "chunk-001",
    section_title: "Gradient Descent",
    text: "Gradient descent is an optimization algorithm that iteratively updates model parameters in the direction that reduces the loss function.",
  },
  content_context: {
    title: "Introduction to Machine Learning",
    content_type: "plain_text",
    language: "en",
  },
  session_context: {
    status: "active",
    current_chunk_id: "chunk-001",
  },
  learner_preferences: {
    preferred_explanation_mode: "simple",
  },
};

export const fallbackSuggestedQuestions = [
  "Can you explain this more simply?",
  "Can you give me an example?",
  "Why is this important?",
];
