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
    return <p className="voice-notice">Voice input is not supported in this browser.</p>;
  }

  return (
    <div className="voice-input">
      <button
        type="button"
        className="voice-input__button"
        onClick={isListening ? onStop : onStart}
        disabled={disabled}
        aria-label={isListening ? "Stop listening" : "Speak your question"}
      >
        {isListening ? "Stop listening" : "Speak"}
      </button>
      {isListening && (
        <span className="voice-notice" role="status">
          Listening...{interimTranscript ? ` ${interimTranscript}` : ""}
        </span>
      )}
      {error && <p className="voice-error" role="status">{error}</p>}
    </div>
  );
}
