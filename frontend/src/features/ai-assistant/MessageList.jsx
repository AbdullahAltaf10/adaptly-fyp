import { MessageBubble } from "./MessageBubble";

export function MessageList({ messages, isLoading, endRef, speechSupported, isSpeaking, onPlay, onStop }) {
  if (messages.length === 0) {
    return (
      <div className="assistant-empty-state">
        Ask me anything about the section you&apos;re studying.
        <div ref={endRef} />
      </div>
    );
  }

  return (
    <div className="message-list" aria-label="Assistant conversation">
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
        <p className="assistant-thinking" role="status">
          Adaptly is thinking...
        </p>
      )}
      <div ref={endRef} />
    </div>
  );
}
