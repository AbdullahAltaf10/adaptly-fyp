import { useEffect, useRef, useState } from "react";

function getRecognitionConstructor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function friendlyRecognitionError(errorCode) {
  switch (errorCode) {
    case "not-allowed":
    case "service-not-allowed":
      return "Microphone access was not available. You can still type your question.";
    case "audio-capture":
      return "A microphone was not available. You can still type your question.";
    case "no-speech":
      return "No speech was detected. You can still type your question.";
    default:
      return "Voice input could not be completed. You can still type your question.";
  }
}

export function useSpeechRecognition({ onFinalTranscript }) {
  const recognitionRef = useRef(null);
  const [isSupported] = useState(() => Boolean(getRecognitionConstructor()));
  const [isListening, setIsListening] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [recognitionError, setRecognitionError] = useState("");

  useEffect(() => () => {
    recognitionRef.current?.abort?.();
  }, []);

  function startListening() {
    const Recognition = getRecognitionConstructor();
    if (!Recognition || isListening) return;

    const recognition = new Recognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = window.navigator.language || "en-US";
    recognitionRef.current = recognition;
    setRecognitionError("");
    setInterimTranscript("");
    setIsListening(true);

    recognition.onstart = () => setIsListening(true);
    recognition.onresult = (event) => {
      let finalTranscript = "";
      let interim = "";

      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const transcript = event.results[index][0].transcript;
        if (event.results[index].isFinal) {
          finalTranscript += transcript;
        } else {
          interim += transcript;
        }
      }

      setInterimTranscript(interim.trim());
      if (finalTranscript.trim()) onFinalTranscript(finalTranscript.trim());
    };
    recognition.onerror = (event) => {
      console.error("Speech recognition error:", event.error);
      if (event.error !== "aborted") setRecognitionError(friendlyRecognitionError(event.error));
    };
    recognition.onend = () => {
      setIsListening(false);
      setInterimTranscript("");
      recognitionRef.current = null;
    };
    try {
      recognition.start();
    } catch {
      setIsListening(false);
      setRecognitionError("Voice input could not be started. You can still type your question.");
    }
  }

  function stopListening() {
    recognitionRef.current?.stop?.();
    setIsListening(false);
  }

  return {
    isSupported,
    isListening,
    interimTranscript,
    recognitionError,
    startListening,
    stopListening,
  };
}
