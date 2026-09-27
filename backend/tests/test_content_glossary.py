"""
Module 2's glossary: the definitions half of scope 6.2.

`build_glossary` returned `[]` unconditionally before this, so the scope's
"a background glossary is prepared so the agent can explain them instantly"
had nothing behind it. These tests pin the three things that make the
replacement safe to run on every upload: it never raises, it never invents a
term nobody asked about, and it costs exactly one model request per document.
"""

import unittest

from app.content.glossary import (
    MAX_DEFINITION_CHARS,
    build_glossary,
    glossary_for,
    parse_glossary,
    refresh_glossary_safely,
)


class RecordingGenerator:
    """A stand-in language model that answers with whatever it was given."""

    def __init__(self, reply="", error=None):
        self.reply = reply
        self.error = error
        self.calls = []

    def generate(self, prompt, *, task, text):
        self.calls.append(prompt)
        if self.error is not None:
            raise self.error
        return self.reply


class ParseGlossaryTests(unittest.TestCase):
    def test_parses_one_entry_per_line(self):
        raw = "LSTM :: a network that learns from sequences\nEAR :: a blink measure"

        entries = parse_glossary(raw, ["LSTM", "EAR"])

        self.assertEqual(
            entries,
            [
                {"term": "LSTM", "definition": "a network that learns from sequences"},
                {"term": "EAR", "definition": "a blink measure"},
            ],
        )

    def test_drops_terms_that_were_never_asked_for(self):
        """A model that volunteers an extra term is inventing one.

        The glossary is shown to a learner as fact, so an entry nobody asked
        about is worse than a missing one.
        """
        raw = "LSTM :: a sequence model\nQuantum :: unrelated invention"

        entries = parse_glossary(raw, ["LSTM"])

        self.assertEqual(entries, [{"term": "LSTM", "definition": "a sequence model"}])

    def test_matches_case_insensitively_but_stores_the_requested_spelling(self):
        entries = parse_glossary("lstm :: a sequence model", ["LSTM"])

        self.assertEqual(entries[0]["term"], "LSTM")

    def test_keeps_the_first_definition_when_a_term_is_answered_twice(self):
        raw = "LSTM :: first answer\nLSTM :: second answer"

        entries = parse_glossary(raw, ["LSTM"])

        self.assertEqual(entries, [{"term": "LSTM", "definition": "first answer"}])

    def test_skips_lines_with_no_separator_and_empty_definitions(self):
        raw = "Here is your glossary:\nLSTM ::   \nEAR :: a blink measure"

        entries = parse_glossary(raw, ["LSTM", "EAR"])

        self.assertEqual(entries, [{"term": "EAR", "definition": "a blink measure"}])

    def test_tolerates_bulleted_lines(self):
        entries = parse_glossary("- LSTM :: a sequence model", ["LSTM"])

        self.assertEqual(entries[0]["term"], "LSTM")

    def test_definitions_are_capped(self):
        entries = parse_glossary(f"LSTM :: {'x' * 900}", ["LSTM"])

        self.assertEqual(len(entries[0]["definition"]), MAX_DEFINITION_CHARS)

    def test_a_colon_inside_a_definition_survives(self):
        """`::` rather than `:` as the separator exists for exactly this."""
        entries = parse_glossary("LSTM :: long short-term memory: a sequence model", ["LSTM"])

        self.assertEqual(
            entries[0]["definition"], "long short-term memory: a sequence model"
        )


class ContractShapeTests(unittest.TestCase):
    def test_entries_match_the_shared_content_contract(self):
        """Read from the contract rather than restated here.

        `content.schema.json` sets `additionalProperties: false` on a glossary
        entry, so an extra key would be rejected at the boundary. Comparing
        against the file means this test fails if the contract changes, which
        is the point.
        """
        import json
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        schema_path = os.path.join(
            os.path.dirname(here), "shared", "contracts", "content.schema.json"
        )
        with open(schema_path, encoding="utf-8") as handle:
            item_schema = json.load(handle)["properties"]["glossary"]["items"]

        entries = parse_glossary("LSTM :: a sequence model", ["LSTM"])

        self.assertTrue(entries)
        allowed = set(item_schema["properties"])
        required = set(item_schema["required"])
        for entry in entries:
            self.assertEqual(set(entry), allowed)
            self.assertTrue(required.issubset(entry))
            for value in entry.values():
                self.assertIsInstance(value, str)
                self.assertGreater(len(value), 0)


class BuildGlossaryTests(unittest.TestCase):
    def test_asks_for_every_term_in_one_request(self):
        """One request per document, not per term.

        The free tier allows 20 requests per day per model across Modules 4, 5
        and 8. One call per term would spend two days of quota on one upload.
        """
        generator = RecordingGenerator("LSTM :: a sequence model\nEAR :: a blink measure")

        build_glossary(["LSTM", "EAR"], "a document about LSTM and EAR", generator)

        self.assertEqual(len(generator.calls), 1)
        self.assertIn("LSTM", generator.calls[0])
        self.assertIn("EAR", generator.calls[0])

    def test_returns_empty_without_calling_anything_when_there_are_no_terms(self):
        generator = RecordingGenerator("LSTM :: a sequence model")

        self.assertEqual(build_glossary([], "some text", generator), [])
        self.assertEqual(generator.calls, [])

    def test_a_failing_model_produces_no_glossary_rather_than_an_error(self):
        """An upload must never fail because a model was busy."""
        generator = RecordingGenerator(error=RuntimeError("model unavailable"))

        self.assertEqual(build_glossary(["LSTM"], "text", generator), [])

    def test_returns_empty_when_no_model_is_configured(self):
        """Mock mode, or no API key: no glossary, and no pretending."""
        import app.intervention.provider as provider

        saved = provider.model_generator_or_none
        provider.model_generator_or_none = lambda: None
        try:
            self.assertEqual(build_glossary(["LSTM"], "text"), [])
        finally:
            provider.model_generator_or_none = saved

    def test_sends_only_a_bounded_slice_of_the_document(self):
        generator = RecordingGenerator("LSTM :: a sequence model")

        build_glossary(["LSTM"], "x" * 50_000, generator)

        self.assertLess(len(generator.calls[0]), 20_000)


class FakeCollection:
    def __init__(self, document=None):
        self.document = document
        self.updates = []

    def update_one(self, query, update):
        self.updates.append((query, update))

    def find_one(self, query, projection=None):
        return self.document


class FakeDatabase:
    def __init__(self, document=None):
        self.content = FakeCollection(document)


class RefreshGlossaryTests(unittest.TestCase):
    """The background task. It runs unattended, so it must never raise."""

    def test_a_bad_content_id_is_swallowed(self):
        database = FakeDatabase()

        refresh_glossary_safely("not-an-object-id", ["LSTM"], "text", database=database)

        self.assertEqual(database.content.updates, [])

    def test_nothing_is_written_when_no_definitions_come_back(self):
        """An empty glossary must not overwrite whatever is already stored."""
        database = FakeDatabase()

        refresh_glossary_safely("507f1f77bcf86cd799439011", [], "text", database=database)

        self.assertEqual(database.content.updates, [])


class GlossaryForTests(unittest.TestCase):
    def test_reads_stored_entries(self):
        database = FakeDatabase(
            {"glossary": [{"term": "LSTM", "definition": "a sequence model"}]}
        )

        self.assertEqual(
            glossary_for("507f1f77bcf86cd799439011", database=database),
            [{"term": "LSTM", "definition": "a sequence model"}],
        )

    def test_drops_malformed_stored_entries(self):
        database = FakeDatabase(
            {"glossary": [{"term": "LSTM"}, {"definition": "orphaned"}, "not a dict"]}
        )

        self.assertEqual(glossary_for("507f1f77bcf86cd799439011", database=database), [])

    def test_a_missing_document_is_an_empty_glossary_not_an_error(self):
        self.assertEqual(
            glossary_for("507f1f77bcf86cd799439011", database=FakeDatabase(None)), []
        )

    def test_a_broken_database_is_an_empty_glossary_not_an_error(self):
        class Broken:
            @property
            def content(self):
                raise RuntimeError("database down")

        self.assertEqual(glossary_for("507f1f77bcf86cd799439011", database=Broken()), [])


if __name__ == "__main__":
    unittest.main()
