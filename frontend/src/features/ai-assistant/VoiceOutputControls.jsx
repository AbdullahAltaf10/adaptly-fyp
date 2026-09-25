export function VoiceOutputControls({ isSpeaking, onPlay, onStop }) {
  return (
    <div className="voice-output-controls" aria-label="Assistant response audio controls">
      <button type="button" onClick={onPlay} aria-label="Play assistant response">Play</button>
      <button type="button" onClick={onStop} disabled={!isSpeaking} aria-label="Stop assistant response">Stop</button>
    </div>
  );
}
