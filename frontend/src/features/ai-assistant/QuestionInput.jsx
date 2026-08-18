export function QuestionInput({ value, onChange, onSubmit, disabled }) {
  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form className="question-input" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
      <label className="visually-hidden" htmlFor="assistant-question">Ask Adaptly a question</label>
      <textarea
        id="assistant-question"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about this section..."
        rows="3"
        disabled={disabled}
      />
      <button type="submit" disabled={disabled || !value.trim()}>
        Send
      </button>
    </form>
  );
}
