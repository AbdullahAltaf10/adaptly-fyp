const suggestedQuestions = [
  "Can you explain this more simply?",
  "Can you give me an example?",
  "Why is this important?",
];

export function SuggestedQuestions({ onSelect, disabled }) {
  return (
    <section className="suggested-questions" aria-labelledby="suggested-questions-title">
      <h3 id="suggested-questions-title">Try asking</h3>
      <div>
        {suggestedQuestions.map((question) => (
          <button key={question} type="button" onClick={() => onSelect(question)} disabled={disabled}>
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}
