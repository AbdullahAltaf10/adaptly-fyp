import { Square, Volume2 } from "lucide-react";

export function VoiceOutputControls({ isSpeaking, onPlay, onStop }) {
  return (
    <div className="flex gap-1.5 mt-2" aria-label="Assistant response audio controls">
      <button
        type="button"
        onClick={onPlay}
        aria-label="Play assistant response"
        className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-line-strong
                   bg-surface text-ink hover:bg-page transition-colors duration-150"
      >
        <Volume2 size={14} strokeWidth={1.75} aria-hidden="true" />
      </button>
      <button
        type="button"
        onClick={onStop}
        disabled={!isSpeaking}
        aria-label="Stop assistant response"
        className="inline-flex items-center justify-center w-7 h-7 rounded-full border border-line-strong
                   bg-surface text-ink hover:bg-page disabled:opacity-50 disabled:cursor-not-allowed
                   transition-colors duration-150"
      >
        <Square size={12} strokeWidth={1.75} aria-hidden="true" />
      </button>
    </div>
  );
}
