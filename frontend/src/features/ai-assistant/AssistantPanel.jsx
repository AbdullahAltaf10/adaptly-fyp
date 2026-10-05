import { RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { fetchAssistantHistory, fetchSuggestedQuestions, sendAssistantMessage } from "./assistantApi";
import { fallbackStudyContext, fallbackSuggestedQuestions } from "./demoStudyContext";
import { MessageList } from "./MessageList";
import { QuestionInput } from "./QuestionInput";
import { SuggestedQuestions } from "./SuggestedQuestions";
import { useSpeechRecognition } from "./useSpeechRecognition";
import { useSpeechSynthesis } from "./useSpeechSynthesis";
import { VoiceInputButton } from "./VoiceInputButton";

const safeErrorMessage = "I couldn't get a response right now. Please try again.";

function messageForHistory(message) {
  return { role: message.role, message: message.content };
}

export function AssistantPanel({
  apiClient = sendAssistantMessage,
  suggestionsClient = fetchSuggestedQuestions,
  historyClient = fetchAssistantHistory,
  studyContext = fallbackStudyContext,
  // Set by StudySession when the learner clicks "Continue in chat" on a
  // ParagraphPopup: the same content already shown there, appended to this
  // same persistent conversation so further questions have it as context.
  // { id, content } - id is what gates re-application, not object identity,
  // so the caller does not need to memoize it.
  seedTurn = null,
}) {
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
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const appliedSeedIdRef = useRef(null);
  const endRef = useRef(null);
  const previousSessionId = useRef(studyContext.session_id);
  // Bumped whenever something else decides the suggestions (a new paragraph, or
  // an answer that came with its own). A paragraph's suggestions arrive late
  // and must not overwrite ones the learner has already moved past.
  const suggestionVersion = useRef(0);
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
    let cancelled = false;
    historyClient()
      .then((history) => {
        if (cancelled || !Array.isArray(history) || history.length === 0) return;
        setMessages(
          history.map((entry) => ({
            id: nextMessageId.current++,
            role: entry.role,
            content: entry.content,
          }))
        );
      })
      .catch(() => {
        // A history that fails to load leaves the conversation empty -
        // today's actual starting state - rather than blocking the panel.
      })
      .finally(() => {
        if (!cancelled) setHistoryLoaded(true);
      });
    return () => {
      cancelled = true;
    };
    // Runs once, on mount, regardless of studyContext - a remount (closing
    // and reopening the panel) is exactly when this should re-fetch, since
    // AssistantPanel already loses its in-memory `messages` state on every
    // remount today.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    // Gated on historyLoaded so a fresh mount (panel opened BY the redirect
    // itself) cannot race: history's setMessages is a wholesale replace, and
    // resolving after an early-applied seed would silently wipe it. Gated
    // on the seed's own id, not object identity, so the caller passing a
    // fresh object each render does not re-append it.
    if (!historyLoaded || !seedTurn || appliedSeedIdRef.current === seedTurn.id) return;
    appliedSeedIdRef.current = seedTurn.id;
    setMessages((current) => [
      ...current,
      { id: nextMessageId.current++, role: "assistant", content: seedTurn.content },
    ]);
  }, [historyLoaded, seedTurn]);

  useEffect(() => {
    if (previousSessionId.current !== studyContext.session_id) {
      setMessages([]);
      setError("");
      setFailedRequest(null);
    }
    previousSessionId.current = studyContext.session_id;

    // Show the generic questions at once, then replace them with ones about
    // THIS paragraph as soon as the server has them. A failure just keeps the
    // generic ones: suggestions are a convenience and must never be an error.
    setSuggestedQuestions(fallbackSuggestedQuestions);
    const version = ++suggestionVersion.current;
    const controller = new AbortController();
    Promise.resolve(suggestionsClient(studyContext.current_chunk, { signal: controller.signal }))
      .then((questions) => {
        if (suggestionVersion.current === version && Array.isArray(questions)) {
          setSuggestedQuestions(questions);
        }
      })
      .catch(() => {});
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
      // An answer brings its own suggestions, so a slower paragraph fetch that
      // is still in flight must not replace them.
      suggestionVersion.current += 1;
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
    <section
      className="assistant-panel flex flex-col h-full bg-surface text-ink"
      aria-labelledby="assistant-title"
    >
      <header className="flex items-start justify-between gap-3 px-4 py-3 border-b border-line">
        <div>
          <h2 id="assistant-title" className="m-0 text-base font-semibold">
            Adaptly Assistant
          </h2>
          <p className="m-0 mt-0.5 text-xs text-muted">
            Support for the section you&apos;re studying.
          </p>
        </div>
        {speech.isSupported && (
          <label className="inline-flex items-center gap-1.5 text-xs text-muted whitespace-nowrap shrink-0">
            <input
              type="checkbox"
              checked={voiceResponsesEnabled}
              onChange={(event) => setVoiceResponsesEnabled(event.target.checked)}
              className="accent-accent"
            />
            Voice responses
          </label>
        )}
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-3 min-h-0">
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
        <div
          role="alert"
          className="flex items-center justify-between gap-3 mx-4 mb-2 px-3 py-2 rounded-md
                     border-l-4 border-l-warning bg-warning-soft text-ink text-sm"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={retryFailedQuestion}
            disabled={isLoading}
            className="inline-flex items-center gap-1 shrink-0 rounded-md border border-line-strong
                       bg-surface px-2.5 py-1 text-xs font-medium hover:bg-page
                       disabled:opacity-60 disabled:cursor-not-allowed transition-colors duration-150"
          >
            <RefreshCw size={12} strokeWidth={1.75} aria-hidden="true" />
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
