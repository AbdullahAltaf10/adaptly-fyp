import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AssistantPanel } from "./AssistantPanel";

let recognitionInstances = [];

class MockSpeechRecognition {
  constructor() {
    recognitionInstances.push(this);
  }

  start = vi.fn();
  stop = vi.fn();
  abort = vi.fn();
}

function installSpeechRecognition() {
  window.SpeechRecognition = MockSpeechRecognition;
}

function installSpeechSynthesis() {
  window.speechSynthesis = { cancel: vi.fn(), speak: vi.fn() };
  window.SpeechSynthesisUtterance = class MockUtterance {
    constructor(text) {
      this.text = text;
    }
  };
}

afterEach(() => {
  recognitionInstances = [];
  delete window.SpeechRecognition;
  delete window.webkitSpeechRecognition;
  delete window.speechSynthesis;
  delete window.SpeechSynthesisUtterance;
});

describe("AssistantPanel voice interaction", () => {
  it("shows a voice input fallback while typed chat remains available", () => {
    render(<AssistantPanel apiClient={vi.fn()} />);

    expect(screen.getByText("Voice input is not supported in this browser.")).toBeInTheDocument();
    expect(screen.getByLabelText("Ask Adaptly a question")).toBeInTheDocument();
  });

  it("shows the microphone control and inserts a final transcript", async () => {
    installSpeechRecognition();
    const user = userEvent.setup();
    render(<AssistantPanel apiClient={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Speak your question" }));
    expect(screen.getByRole("button", { name: "Stop listening" })).toBeInTheDocument();

    act(() => {
      recognitionInstances[0].onresult({
        resultIndex: 0,
        results: [{ 0: { transcript: "Explain gradient descent simply" }, isFinal: true }],
      });
    });

    expect(screen.getByLabelText("Ask Adaptly a question")).toHaveValue("Explain gradient descent simply");
  });

  it("keeps typed chat usable after a recognition error", async () => {
    installSpeechRecognition();
    const apiClient = vi.fn().mockResolvedValue({ answer: "A helpful answer." });
    const user = userEvent.setup();
    render(<AssistantPanel apiClient={apiClient} />);

    await user.click(screen.getByRole("button", { name: "Speak your question" }));
    act(() => recognitionInstances[0].onerror({ error: "not-allowed" }));
    expect(screen.getByText("Microphone access was not available. You can still type your question.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Typed question");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("A helpful answer.")).toBeInTheDocument();
  });

  it("keeps voice responses off by default and speaks a new answer when enabled", async () => {
    installSpeechSynthesis();
    const apiClient = vi.fn().mockResolvedValue({ answer: "**Gradient descent** reduces error." });
    const user = userEvent.setup();
    render(<AssistantPanel apiClient={apiClient} />);

    const voiceToggle = screen.getByRole("checkbox", { name: "Voice responses" });
    expect(voiceToggle).not.toBeChecked();
    await user.click(voiceToggle);
    expect(voiceToggle).toBeChecked();

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Explain this");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("**Gradient descent** reduces error.");

    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);
    expect(window.speechSynthesis.speak.mock.calls[0][0].text).toBe("Gradient descent reduces error.");
  });

  it("does not auto-play when voice responses are disabled", async () => {
    installSpeechSynthesis();
    const user = userEvent.setup();
    render(<AssistantPanel apiClient={vi.fn().mockResolvedValue({ answer: "Text only." })} />);

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Explain this");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Text only.");

    expect(window.speechSynthesis.speak).not.toHaveBeenCalled();
  });

  it("plays only assistant messages and stops existing playback", async () => {
    installSpeechSynthesis();
    const user = userEvent.setup();
    render(<AssistantPanel apiClient={vi.fn().mockResolvedValue({ answer: "Assistant response." })} />);

    await user.type(screen.getByLabelText("Ask Adaptly a question"), "Learner question");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("Assistant response.");

    expect(screen.getAllByRole("button", { name: "Play assistant response" })).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Play assistant response" }));
    expect(window.speechSynthesis.cancel).toHaveBeenCalled();
    expect(window.speechSynthesis.speak).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Stop assistant response" }));
    await waitFor(() => expect(window.speechSynthesis.cancel).toHaveBeenCalledTimes(2));
  });
});
