import { Bot, User } from "lucide-react";

import { VoiceOutputControls } from "./VoiceOutputControls";

/**
 * One line of the conversation.
 *
 * A small avatar (not a photo, not a face - scope keeps this calm and
 * unlabelled) sits beside whichever side spoke, the same way a chat app
 * separates two speakers without making either one loud. `aria-hidden` on the
 * icon: it is a visual anchor, not information - "You"/"Adaptly" already says
 * who is speaking, in text a screen reader announces.
 */
export function MessageBubble({ role, content, speechSupported, isSpeaking, onPlay, onStop }) {
  const isAssistant = role === "assistant";

  return (
    <article className={`flex gap-2 ${isAssistant ? "justify-start" : "justify-end flex-row-reverse"}`}>
      <span
        className={`flex items-center justify-center w-7 h-7 rounded-full shrink-0 mt-0.5 ${
          isAssistant ? "bg-info-soft text-accent" : "bg-page text-muted border border-line"
        }`}
        aria-hidden="true"
      >
        {isAssistant ? <Bot size={16} strokeWidth={1.75} /> : <User size={16} strokeWidth={1.75} />}
      </span>

      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
          isAssistant
            ? "bg-page border border-line text-ink rounded-tl-sm"
            : "bg-accent/10 border border-accent/20 text-ink rounded-tr-sm"
        }`}
      >
        <span className="block text-xs font-semibold text-muted mb-0.5">
          {isAssistant ? "Adaptly" : "You"}
        </span>
        <p className="m-0">{content}</p>
        {isAssistant && speechSupported && (
          <VoiceOutputControls isSpeaking={isSpeaking} onPlay={() => onPlay(content)} onStop={onStop} />
        )}
      </div>
    </article>
  );
}
