import { useEffect, useRef, useState } from "react";

import { sendAssistantMessage } from "./assistantApi";
import { demoStudyContext } from "./demoStudyContext";
import { MessageList } from "./MessageList";
import { QuestionInput } from "./QuestionInput";
import { SuggestedQuestions } from "./SuggestedQuestions";
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
  const nextMessageId = useRef(1);
  const endRef = useRef(null);

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
      </header>
      <div className="assistant-panel__messages">
        <MessageList messages={messages} isLoading={isLoading} endRef={endRef} />
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
      />
    </section>
  );
}
