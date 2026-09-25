import { useEffect, useRef, useState } from "react";

import { sendAssistantMessage } from "./assistantApi";
import { fallbackStudyContext, fallbackSuggestedQuestions } from "./demoStudyContext";
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

export function AssistantPanel({ apiClient = sendAssistantMessage, studyContext = fallbackStudyContext }) {
  const [messages, setMessages] = useState([]);
  const [suggestedQuestions, setSuggestedQuestions] = useState(fallbackSuggestedQuestions);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [failedRequest, setFailedRequest] = useState(null);
  const [voiceResponsesEnabled, setVoiceResponsesEnabled] = useState(false);
  // Tracks how the current `input` text arrived, so it can be reported as
  // the request's input_mode (Issue #34). Reset to "typed" on every manual
  // keystroke so selecting a suggestion or dictating, then editing by hand
  // before sending, is correctly recorded as typed.
  const [inputSource, setInputSource] = useState("typed");
  const nextMessageId = useRef(1);
  const endRef = useRef(null);
  const previousSessionId = useRef(studyContext.session_id);
  const speech = useSpeechSynthesis();

  function handleManualInputChange(value) {
    setInput(value);
    setInputSource("typed");
  }

  function handleSuggestedQuestionSelect(value) {
    setInput(value);
    setInputSource("suggested_question");
  }

  function handleVoiceTranscript(value) {
    setInput(value);
    setInputSource("voice");
  }

  const recognition = useSpeechRecognition({ onFinalTranscript: handleVoiceTranscript });

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages, isLoading, error]);

  useEffect(() => {
    if (previousSessionId.current !== studyContext.session_id) {
      setMessages([]);
      setError("");
      setFailedRequest(null);
    }
    previousSessionId.current = studyContext.session_id;
    setSuggestedQuestions(fallbackSuggestedQuestions);
  }, [
    studyContext.session_id,
    studyContext.content_id,
    studyContext.current_chunk.chunk_id,
    studyContext.current_chunk.text,
    studyContext.current_chunk.section_title,
  ]);

  async function submitQuestion(
    question,
    appendUserMessage = true,
    historyOverride = null,
    requestContext = studyContext,
    inputModeOverride = null,
  ) {
    const trimmedQuestion = question.trim();
    if (!trimmedQuestion || isLoading) return;

    // Read before resetting below - a retry passes its own override instead,
    // since by the time of a retry `inputSource` state has already reset.
    const inputModeForSubmission = inputModeOverride || inputSource;

    const priorMessages = historyOverride || messages
      .filter((message) => message.role === "user" || message.role === "assistant")
      .map(messageForHistory);
    const userMessage = { id: nextMessageId.current++, role: "user", content: trimmedQuestion };

    if (appendUserMessage) {
      setMessages((currentMessages) => [...currentMessages, userMessage]);
    }
    setInput("");
    setInputSource("typed");
    setError("");
    setFailedRequest(null);
    setIsLoading(true);

    try {
      const result = await apiClient({
        ...requestContext,
        question: trimmedQuestion,
        previous_messages: priorMessages,
        input_mode: inputModeForSubmission,
      });
      setMessages((currentMessages) => [
        ...currentMessages,
        { id: nextMessageId.current++, role: "assistant", content: result.answer },
      ]);
      setSuggestedQuestions(result.suggested_questions || fallbackSuggestedQuestions);
      if (voiceResponsesEnabled) speech.speak(result.answer);
    } catch {
      setError(safeErrorMessage);
      setFailedRequest({
        question: trimmedQuestion,
        previousMessages: priorMessages,
        requestContext,
        inputMode: inputModeForSubmission,
      });
    } finally {
      setIsLoading(false);
    }
  }

  function retryFailedQuestion() {
    if (failedRequest) {
      submitQuestion(
        failedRequest.question,
        false,
        failedRequest.previousMessages,
        failedRequest.requestContext,
        failedRequest.inputMode,
      );
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
      <SuggestedQuestions
        questions={suggestedQuestions}
        onSelect={handleSuggestedQuestionSelect}
        disabled={isLoading}
      />
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
        onChange={handleManualInputChange}
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
