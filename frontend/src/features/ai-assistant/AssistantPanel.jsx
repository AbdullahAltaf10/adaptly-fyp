import { useEffect, useRef, useState } from "react";

import { sendAssistantMessage } from "./assistantApi";
import { demoStudyContext } from "./demoStudyContext";
import { MessageList } from "./MessageList";
import { QuestionInput } from "./QuestionInput";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { useSpeechRecognition } from "./useSpeechRecognition";
import { useSpeechSynthesis } from "./useSpeechSynthesis";
import { VoiceInputButton } from "./VoiceInputButton";
import "./assistant.css";

const safeErrorMessage = "I couldn't get a response right now. Please try again.";

function messageForHistory(message) {
  return { role: message.role, message: message.content };
}

export function AssistantPanel({ apiClient = sendAssistantMessage, studyContext = demoStudyContext }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [failedRequest, setFailedRequest] = useState(null);
  const [voiceResponsesEnabled, setVoiceResponsesEnabled] = useState(false);
  const nextMessageId = useRef(1);
  const endRef = useRef(null);
  const speech = useSpeechSynthesis();
  const recognition = useSpeechRecognition({ onFinalTranscript: setInput });

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, isLoading, error]);

  async function submitQuestion(question, appendUserMessage = true, historyOverride = null) {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) return;

    const priorMessages = historyOverride || messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map(messageForHistory);
    const userMessage = { id: nextMessageId.current++, role: "user", content: trimmedQuestion };

    if (appendUserMessage) {
      setMessages((currentMessages) => [...currentMessages, userMessage]);
    }
    setInput("");
    setError("");
    setFailedRequest(null);
    setIsLoading(true);

    try {
      const result = await apiClient({
        ...studyContext,
        question: trimmedQuestion,
        previous_messages: priorMessages,
      });
      setMessages((currentMessages) => [
        ...currentMessages,
        { id: nextMessageId.current++, role: "assistant", content: result.answer },
      ]);
      if (voiceResponsesEnabled) speech.speak(result.answer);
    } catch {
      setError(safeErrorMessage);
      setFailedRequest({ question: trimmedQuestion, previousMessages: priorMessages });
    } finally {
      setIsLoading(false);
    }
  }

  function retryFailedQuestion() {
    if (failedRequest) {
      submitQuestion(failedRequest.question, false, failedRequest.previousMessages);
    }
  }

  return (
    <section className="assistant-panel" aria-labelledby="assistant-title">
      <header className="assistant-panel__header">
        <div>
          <h1 id="assistant-title">Adaptly Assistant</h1>
          <p>Support for the section you&apos;re studying.</p>
        </div>
        {speech.isSupported && (
          <label className="voice-toggle">
            <input
              type="checkbox"
              checked={voiceResponsesEnabled}
              onChange={(event) => setVoiceResponsesEnabled(event.target.checked)}
            />
            Voice responses
          </label>
        )}
      </header>
      <div className="assistant-panel__messages">
        <MessageList
          messages={messages}
          isLoading={isLoading}
          endRef={endRef}
          speechSupported={speech.isSupported}
          isSpeaking={speech.isSpeaking}
          onPlay={speech.speak}
          onStop={speech.stop}
        />
      </div>
      <SuggestedQuestions onSelect={setInput} disabled={isLoading} />
      {error && (
        <div className="assistant-error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={retryFailedQuestion} disabled={isLoading}>
            Retry
          </button>
        </div>
      )}
      <QuestionInput
        value={input}
        onChange={setInput}
        onSubmit={() => submitQuestion(input)}
        disabled={isLoading}
        voiceControl={(
          <VoiceInputButton
            isSupported={recognition.isSupported}
            isListening={recognition.isListening}
            interimTranscript={recognition.interimTranscript}
            error={recognition.recognitionError}
            onStart={recognition.startListening}
            onStop={recognition.stopListening}
            disabled={isLoading}
          />
        )}
      />
    </section>
  );
}
