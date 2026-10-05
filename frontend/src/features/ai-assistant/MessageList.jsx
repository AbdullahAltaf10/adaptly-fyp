import { Sparkles } from "lucide-react";

import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages, isLoading, endRef, speechSupported, isSpeaking, onPlay, onStop }) {
  if (messages.length === 0) {
    return (
      <div className="grid min-h-48 place-content-center text-center text-muted px-6" aria-hidden={false}>
        <Sparkles size={22} strokeWidth={1.5} className="mx-auto mb-2 text-accent" aria-hidden="true" />
        Ask me anything about the section you&apos;re studying.
        <div ref={endRef} />
      </div>
    );
  }

  return (
    <div className="grid gap-3" aria-label="Assistant conversation">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          role={message.role}
          content={message.content}
          speechSupported={speechSupported}
          isSpeaking={isSpeaking}
          onPlay={onPlay}
          onStop={onStop}
        />
      ))}
      {isLoading && (
        <p className="text-muted italic text-sm m-0 flex items-center gap-2" role="status">
          <span className="flex gap-1" aria-hidden="true">
            <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce [animation-delay:-0.3s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce [animation-delay:-0.15s]" />
            <span className="w-1.5 h-1.5 rounded-full bg-muted animate-bounce" />
          </span>
          Adaptly is thinking...
        </p>
      )}
      <div ref={endRef} />
    </div>
  );
}
