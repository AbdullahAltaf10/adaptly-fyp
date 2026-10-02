import { Mic, MicOff } from "lucide-react";

export function VoiceInputButton({
  isSupported,
  isListening,
  interimTranscript,
  error,
  onStart,
  onStop,
  disabled,
}) {
  if (!isSupported) {
    return (
      <p className="text-xs text-muted m-0">
        Voice input is not supported in this browser.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2 mt-1">
      <button
        type="button"
        onClick={isListening ? onStop : onStart}
        disabled={disabled}
        aria-label={isListening ? "Stop listening" : "Speak your question"}
        className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium
                    transition-colors duration-150 disabled:opacity-60 disabled:cursor-not-allowed ${
                      isListening
                        ? "bg-danger-soft border-danger/40 text-danger"
                        : "bg-surface border-line-strong text-ink hover:bg-page"
                    }`}
      >
        {isListening ? (
          <MicOff size={14} strokeWidth={1.75} aria-hidden="true" />
        ) : (
          <Mic size={14} strokeWidth={1.75} aria-hidden="true" />
        )}
        {isListening ? "Stop listening" : "Speak your question"}
      </button>
      {isListening && (
        <span className="text-xs text-muted" role="status">
          Listening...{interimTranscript ? ` ${interimTranscript}` : ""}
        </span>
      )}
      {error && (
        <p className="text-xs text-danger m-0" role="status">
          {error}
        </p>
      )}
    </div>
  );
}
