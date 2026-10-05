import { MessageCircleQuestion } from "lucide-react";

export function SuggestedQuestions({ questions, onSelect, disabled }) {
  return (
    <section
      className="px-4 py-3 border-t border-line"
      aria-labelledby="suggested-questions-title"
    >
      <h3 id="suggested-questions-title" className="m-0 mb-2 text-sm font-semibold text-muted">
        Try asking
      </h3>
      <div className="flex flex-wrap gap-2">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onSelect(question)}
            disabled={disabled}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface
                       px-3 py-1.5 text-sm text-ink hover:bg-accent/10 hover:border-accent/40
                       disabled:opacity-60 disabled:cursor-not-allowed transition-colors duration-150"
          >
            <MessageCircleQuestion size={14} strokeWidth={1.75} className="text-accent shrink-0" aria-hidden="true" />
            {question}
          </button>
        ))}
      </div>
    </section>
  );
}
