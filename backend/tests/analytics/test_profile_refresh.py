"""The learning profile is actually built and stored (scope 6.8).

`build_learning_profile` was a pure function nothing called, and
`learning_profiles.save` had no caller, so the API returned a placeholder to
everyone. The tests that matter therefore go through the real session-end path
and look at what ended up in the store - a unit test of the builder would have
passed before this change too.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

import mongomock

from app.analytics.domain.metrics import METRIC_VERSION
from app.analytics.service import profile_refresh, session_lifecycle
from app.analytics.service.finalization import AnalyticsRepositories
from tests.analytics.test_api import _seed_and_finalize


def _repositories() -> AnalyticsRepositories:
    return AnalyticsRepositories.from_database(mongomock.MongoClient()["profile_test"])


def _finalized(repositories, session_id, user_id="user-1"):
    return _seed_and_finalize(repositories, session_id=session_id, user_id=user_id)


class RefreshTests(unittest.TestCase):
    def test_a_finalized_session_produces_a_stored_profile(self):
        repositories = _repositories()
        _finalized(repositories, "s1")
        self.assertIsNone(repositories.learning_profiles.get("user-1"))

        profile = profile_refresh.refresh_learning_profile("user-1", repositories)

        stored = repositories.learning_profiles.get("user-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["user_id"], "user-1")
        self.assertEqual(stored["sessions_analyzed"], 1)
        self.assertEqual(profile["sessions_analyzed"], 1)

    def test_it_grows_with_each_session(self):
        repositories = _repositories()
        _finalized(repositories, "s1")
        profile_refresh.refresh_learning_profile("user-1", repositories)
        _finalized(repositories, "s2")
        profile_refresh.refresh_learning_profile("user-1", repositories)

        self.assertEqual(repositories.learning_profiles.get("user-1")["sessions_analyzed"], 2)

    def test_refreshing_twice_changes_nothing(self):
        # Recomputed from scratch, so it cannot drift or double count.
        repositories = _repositories()
        _finalized(repositories, "s1")
        profile_refresh.refresh_learning_profile("user-1", repositories)
        profile_refresh.refresh_learning_profile("user-1", repositories)
        profile_refresh.refresh_learning_profile("user-1", repositories)

        self.assertEqual(repositories.learning_profiles.get("user-1")["sessions_analyzed"], 1)

    def test_a_session_finalized_under_two_metric_versions_counts_once(self):
        # Summaries are keyed on session id AND metric version, so a session
        # re-finalized after a version bump has two documents. Feeding both in
        # would count it twice.
        repositories = _repositories()
        _finalized(repositories, "s1")
        original = repositories.session_analytics.list_by_user("user-1")[0]
        stale = dict(original["summary"], metric_version="0.9")
        repositories.session_analytics.save(stale)
        self.assertEqual(len(repositories.session_analytics.list_by_user("user-1")), 2)

        profile_refresh.refresh_learning_profile("user-1", repositories)

        self.assertEqual(repositories.learning_profiles.get("user-1")["sessions_analyzed"], 1)

    def test_one_learners_sessions_never_reach_another_learners_profile(self):
        repositories = _repositories()
        _finalized(repositories, "mine", user_id="user-1")
        _finalized(repositories, "theirs", user_id="user-2")

        profile_refresh.refresh_learning_profile("user-1", repositories)

        self.assertEqual(repositories.learning_profiles.get("user-1")["sessions_analyzed"], 1)
        self.assertIsNone(repositories.learning_profiles.get("user-2"))

    def test_it_builds_the_profile_of_whoever_it_is_asked_about(self):
        # Every other test uses "user-1", so an implementation that hardcoded it
        # would pass all of them. A different learner is what exposes that.
        repositories = _repositories()
        _finalized(repositories, "a1", user_id="user-1")
        _finalized(repositories, "b1", user_id="user-2")
        _finalized(repositories, "b2", user_id="user-2")

        profile_refresh.refresh_learning_profile("user-2", repositories)

        self.assertEqual(repositories.learning_profiles.get("user-2")["sessions_analyzed"], 2)
        self.assertIsNone(repositories.learning_profiles.get("user-1"))

    def test_no_summaries_means_no_profile_rather_than_an_empty_one(self):
        repositories = _repositories()
        self.assertIsNone(profile_refresh.refresh_learning_profile("user-1", repositories))
        self.assertIsNone(repositories.learning_profiles.get("user-1"))

    def test_it_is_bounded_to_the_most_recent_sessions(self):
        repositories = _repositories()
        for index in range(5):
            _finalized(repositories, f"s{index}")
        with patch.object(profile_refresh, "MAX_SESSIONS", 3):
            profile_refresh.refresh_learning_profile("user-1", repositories)

        self.assertEqual(repositories.learning_profiles.get("user-1")["sessions_analyzed"], 3)


class SafetyTests(unittest.TestCase):
    def test_the_safe_wrapper_never_raises(self):
        class Broken:
            @property
            def session_analytics(self):
                raise RuntimeError("db unreachable")

        try:
            profile_refresh.refresh_learning_profile_safely("user-1", Broken())
        except Exception as error:  # pragma: no cover
            self.fail(f"raised {error!r}")


class SessionEndTests(unittest.TestCase):
    """Through the real session-end hook, the path a learner actually takes."""

    def _end(self, repositories, session_id, user_id="user-1"):
        with patch.object(session_lifecycle, "_repositories", return_value=repositories):
            session_lifecycle.finalize_session_safely(user_id, session_id)

    def test_ending_a_session_builds_the_profile(self):
        from tests.analytics.test_api import _seed_session

        repositories = _repositories()
        seeded = _seed_session(repositories, "normal_completed_session", session_id="s1",
                               user_id="user-1", status="active")
        self._end(repositories, seeded["session_id"])

        stored = repositories.learning_profiles.get("user-1")
        self.assertIsNotNone(stored)
        self.assertEqual(stored["sessions_analyzed"], 1)

    def test_a_retried_end_repairs_a_profile_whose_refresh_failed(self):
        from tests.analytics.test_api import _seed_session

        repositories = _repositories()
        seeded = _seed_session(repositories, "normal_completed_session", session_id="s1",
                               user_id="user-1", status="active")

        with patch.object(profile_refresh, "refresh_learning_profile",
                          side_effect=RuntimeError("write failed")):
            self._end(repositories, seeded["session_id"])
        self.assertIsNone(repositories.learning_profiles.get("user-1"))

        # The session is now finalized ("already_finalized"), and ending it again
        # is what heals the profile.
        self._end(repositories, seeded["session_id"])
        self.assertIsNotNone(repositories.learning_profiles.get("user-1"))

    def test_a_refresh_failure_never_breaks_ending_the_session(self):
        from tests.analytics.test_api import _seed_session

        repositories = _repositories()
        seeded = _seed_session(repositories, "normal_completed_session", session_id="s1",
                               user_id="user-1", status="active")
        with patch.object(profile_refresh, "refresh_learning_profile",
                          side_effect=RuntimeError("boom")):
            try:
                self._end(repositories, seeded["session_id"])
            except Exception as error:  # pragma: no cover
                self.fail(f"session end raised {error!r}")
        # And the summary the session end exists to produce is still there.
        self.assertEqual(len(repositories.session_analytics.list_by_user("user-1")), 1)

    def test_a_rejected_finalization_does_not_rebuild_the_profile(self):
        # An abandoned session is finalization's `rejected` outcome, which is a
        # normal return rather than an exception, so it is the path that could
        # wrongly reach the refresh. The learner already has a finished session,
        # so a wrongly-triggered refresh WOULD produce a profile here - its
        # absence is the assertion. (A session that does not exist raises
        # instead, and the except clause returns before the refresh.)
        from tests.analytics.test_api import _seed_and_finalize, _seed_session

        repositories = _repositories()
        _seed_and_finalize(repositories, session_id="earlier", user_id="user-1")
        self.assertIsNone(repositories.learning_profiles.get("user-1"))

        seeded = _seed_session(repositories, "normal_completed_session", session_id="quit",
                               user_id="user-1", status="abandoned")
        self._end(repositories, seeded["session_id"])

        self.assertIsNone(repositories.learning_profiles.get("user-1"))

    def test_a_session_that_does_not_exist_does_not_touch_the_profile(self):
        repositories = _repositories()
        self._end(repositories, "does-not-exist")
        self.assertIsNone(repositories.learning_profiles.get("user-1"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
