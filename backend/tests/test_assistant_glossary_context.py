"""
The assistant's half of scope 6.2: "so the agent can explain them instantly".

Module 2 preparing a glossary is only half the sentence. These tests pin that
it reaches the prompt, that it arrives in a section the model is told to
trust, and that a document without one produces no section at all rather than
an empty one.
"""

import unittest

from app.ai_assistant.context import build_assistant_context
from app.ai_assistant.prompts import build_assistant_prompt
from app.ai_assistant.schemas import AssistantMessageRequest

GLOSSARY = [
    {"term": "LSTM", "definition": "a network that learns from sequences"},
    {"term": "EAR", "definition": "a blink measure taken from the eye"},
]


def a_request(**overrides):
    payload = {
        "session_id": "session-1",
        "content_id": "content-1",
        "question": "What does LSTM mean here?",
        "current_chunk": {
            "chunk_id": "chunk-1",
            "text": "The LSTM reads a window of EAR values.",
            "section_title": "Engagement detection",
        },
    }
    payload.update(overrides)
    return AssistantMessageRequest(**payload)


class GlossaryReachesThePromptTests(unittest.TestCase):
    def test_the_glossary_appears_in_the_prompt(self):
        context = build_assistant_context(a_request(), glossary=GLOSSARY)

        prompt = build_assistant_prompt(context)

        self.assertIn("<document_glossary>", prompt)
        self.assertIn("LSTM", prompt)
        self.assertIn("a network that learns from sequences", prompt)
        self.assertIn("a blink measure taken from the eye", prompt)

    def test_it_is_presented_as_adaptly_derived_not_as_learner_input(self):
        """It sits beside the engagement guidance, not inside the untrusted JSON.

        `document_metadata` carries a title and language that came from the
        request, so that block is labelled untrusted. The glossary did not come
        from the request, and a model told the difference can rely on it.
        """
        context = build_assistant_context(a_request(), glossary=GLOSSARY)

        prompt = build_assistant_prompt(context)

        section = prompt.split("<document_glossary>")[1].split("</document_glossary>")[0]
        self.assertIn("not learner input", section)

        untrusted = prompt.split("<document_metadata_untrusted_json>")[1].split(
            "</document_metadata_untrusted_json>"
        )[0]
        self.assertNotIn("a network that learns from sequences", untrusted)

    def test_no_glossary_means_no_section_at_all(self):
        """An empty section would invite the model to remark on the absence."""
        context = build_assistant_context(a_request())

        prompt = build_assistant_prompt(context)

        self.assertNotIn("<document_glossary>", prompt)

    def test_an_empty_list_is_treated_the_same_as_none(self):
        context = build_assistant_context(a_request(), glossary=[])

        self.assertNotIn("<document_glossary>", build_assistant_prompt(context))

    def test_the_context_carries_the_entries(self):
        context = build_assistant_context(a_request(), glossary=GLOSSARY)

        self.assertEqual(
            [(entry.term, entry.definition) for entry in context.content.glossary],
            [(entry["term"], entry["definition"]) for entry in GLOSSARY],
        )


if __name__ == "__main__":
    unittest.main()
