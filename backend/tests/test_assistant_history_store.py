import time

from app.ai_assistant import history_store


class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, field, direction):
        self._docs = sorted(self._docs, key=lambda d: d[field], reverse=direction < 0)
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __iter__(self):
        return iter(self._docs)


class FakeCollection:
    def __init__(self):
        self.docs = []
        self.fail = False

    def insert_one(self, document):
        if self.fail:
            raise RuntimeError("no connection")
        self.docs.append(dict(document))

    def find(self, query):
        if self.fail:
            raise RuntimeError("no connection")
        matched = [d for d in self.docs if d["uid"] == query["uid"]]
        if "timestamp" in query:
            matched = [d for d in matched if d["timestamp"] < query["timestamp"]["$lt"]]
        return FakeCursor(matched)


class FakeDB:
    def __init__(self):
        self.assistant_messages = FakeCollection()


def test_insert_then_list_round_trips(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    assert history_store.insert_message(uid="u1", role="user", content="hi", source="panel")
    result = history_store.list_messages("u1")
    assert len(result) == 1
    assert result[0]["content"] == "hi"


def test_list_is_newest_first(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    history_store.insert_message(uid="u1", role="user", content="first", source="panel")
    time.sleep(0.001)  # Windows' time.time() resolution can tie two fast calls otherwise
    history_store.insert_message(uid="u1", role="assistant", content="second", source="panel")
    result = history_store.list_messages("u1")
    assert [m["content"] for m in result] == ["second", "first"]


def test_one_learner_never_sees_anothers_history(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    history_store.insert_message(uid="u1", role="user", content="mine", source="panel")
    history_store.insert_message(uid="u2", role="user", content="theirs", source="panel")
    result = history_store.list_messages("u1")
    assert [m["content"] for m in result] == ["mine"]


def test_a_brand_new_learner_has_an_empty_history(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)
    assert history_store.list_messages("nobody-yet") == []


def test_pagination_uses_before_as_an_exclusive_upper_bound(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)

    history_store.insert_message(uid="u1", role="user", content="old", source="panel")
    time.sleep(0.001)
    cutoff = time.time()
    time.sleep(0.001)
    history_store.insert_message(uid="u1", role="user", content="new", source="panel")

    result = history_store.list_messages("u1", before=cutoff)
    assert [m["content"] for m in result] == ["old"]


def test_a_database_problem_on_insert_is_reported_not_raised(monkeypatch):
    fake = FakeDB()
    fake.assistant_messages.fail = True
    monkeypatch.setattr(history_store, "db", fake)
    assert history_store.insert_message(uid="u1", role="user", content="x", source="panel") is False


def test_a_database_problem_on_list_returns_empty_not_raised(monkeypatch):
    fake = FakeDB()
    fake.assistant_messages.fail = True
    monkeypatch.setattr(history_store, "db", fake)
    assert history_store.list_messages("u1") == []


def test_optional_context_fields_default_to_none(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(history_store, "db", fake)
    history_store.insert_message(uid="u1", role="assistant", content="x", source="popup")
    stored = history_store.list_messages("u1")[0]
    assert stored["trigger"] is None
    assert stored["content_id"] is None
    assert stored["chunk_id"] is None
    assert stored["session_id"] is None
