import { SendHorizontal } from "lucide-react";

export function QuestionInput({ value, onChange, onSubmit, disabled, voiceControl }) {
  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      onSubmit();
    }
  }

  return (
    <form
      className="grid grid-cols-[1fr_auto] gap-2 p-3 border-t border-line"
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit();
      }}
    >
      <label className="sr-only" htmlFor="assistant-question">
        Ask Adaptly a question
      </label>
      <textarea
        id="assistant-question"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask about this section..."
        rows="2"
        disabled={disabled}
        className="w-full resize-y rounded-md border border-line-strong bg-surface text-ink text-sm
                   px-3 py-2 disabled:opacity-60 disabled:cursor-not-allowed"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        className="inline-flex items-center justify-center gap-1.5 self-end min-h-10 px-4 rounded-md
                   bg-accent text-on-accent font-medium hover:bg-accent-hover
                   disabled:opacity-60 disabled:cursor-not-allowed transition-colors duration-150"
      >
        <SendHorizontal size={16} strokeWidth={1.75} aria-hidden="true" />
        Send
      </button>
      {voiceControl && <div className="col-span-2">{voiceControl}</div>}
    </form>
  );
}
