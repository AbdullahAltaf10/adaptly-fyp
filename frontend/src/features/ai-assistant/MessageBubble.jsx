import { VoiceOutputControls } from "./VoiceOutputControls";

export function MessageBubble({ role, content, speechSupported, isSpeaking, onPlay, onStop }) {
  const isAssistant = role === "assistant";
  return (
    <article className={`message-bubble message-bubble--${role}`}>
      <span className="message-bubble__label">{isAssistant ? "Adaptly" : "You"}</span>
      <p>{content}</p>
      {isAssistant && speechSupported && (
        <VoiceOutputControls isSpeaking={isSpeaking} onPlay={() => onPlay(content)} onStop={onStop} />
      )}
    </article>
  );
}
