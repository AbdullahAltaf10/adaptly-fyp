export function SuggestedQuestions({ questions, onSelect, disabled }) {
  return (
    <section className="suggested-questions" aria-labelledby="suggested-questions-title">
      <h3 id="suggested-questions-title">Try asking</h3>
      <div>
        {questions.map((question) => (
          <button key={question} type="button" onClick={() => onSelect(question)} disabled={disabled}>
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}
