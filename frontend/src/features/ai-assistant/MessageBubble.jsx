export function MessageBubble({ role, content }) {
  const isAssistant = role === "assistant";
  return (
    <article className={`message-bubble message-bubble--${role}`}>
      <span className="message-bubble__label">{isAssistant ? "Adaptly" : "You"}</span>
      <p>{content}</p>
    </article>
  );
}
