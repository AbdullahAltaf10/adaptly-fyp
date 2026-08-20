import { useEffect, useState } from "react";

export function cleanTextForSpeech(text) {
  return text
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    .replace(/[*#`]/g, "")
    .replace(/^\s*[-+]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function supportsSpeechSynthesis() {
  return typeof window !== "undefined"
    && "speechSynthesis" in window
    && typeof window.SpeechSynthesisUtterance === "function";
}

export function useSpeechSynthesis() {
  const [isSupported] = useState(supportsSpeechSynthesis);
  const [isSpeaking, setIsSpeaking] = useState(false);

  useEffect(() => () => {
    if (supportsSpeechSynthesis()) window.speechSynthesis.cancel();
  }, []);

  function stop() {
    if (!supportsSpeechSynthesis()) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }

  function speak(text) {
    if (!supportsSpeechSynthesis()) return;

    const speechText = cleanTextForSpeech(text);
    if (!speechText) return;

    window.speechSynthesis.cancel();
    const utterance = new window.SpeechSynthesisUtterance(speechText);
    utterance.onend = () => setIsSpeaking(false);
    utterance.onerror = () => setIsSpeaking(false);
    setIsSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  return { isSupported, isSpeaking, speak, stop };
}
