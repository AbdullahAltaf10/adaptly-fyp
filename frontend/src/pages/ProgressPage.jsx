/**
 * The learner's own history and profile, in one place.
 *
 * Two things the backend already produced and nothing ever showed:
 *
 *   - **Session history.** `GET /api/analytics/sessions` and its client
 *     wrapper both existed, unused. A learner could reach only their single
 *     most recent session, with no way back to an earlier one. Scope 6.1 lists
 *     session history as part of what a learner's profile stores.
 *   - **The learning profile.** Built at session end (#97) and already acted
 *     on by Module 4 (#98, which stops offering support that has not helped
 *     this learner), but never displayed — so the one thing the learner could
 *     not see was the reasoning being applied to them. Scope 6.8 promises a
 *     profile that "tracks patterns over time".
 *
 * Both fetchers are injectable, like every other page here, so the tests never
 * touch the network.
 *
 * The two loads are independent on purpose: a learner whose profile fails to
 * load should still get their sessions, and the reverse. Failing the whole
 * page because one of two panels is unavailable would hide working
 * information for no reason.
 */

import { useEffect, useState } from "react";

import { fetchLearningProfile, fetchSessionHistory } from "../analytics/api";
import ErrorState from "../analytics/ErrorState";
import LearningProfileSection from "../analytics/LearningProfileSection";
import LoadingState from "../analytics/LoadingState";
import SessionHistoryList from "../analytics/SessionHistoryList";

function useLoaded(loader) {
  const [state, setState] = useState({ status: "loading", data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });

    loader()
      .then((data) => {
        if (!cancelled) setState({ status: "ready", data, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", data: null, error });
      });

    return () => {
      cancelled = true;
    };
  }, [loader]);

  return state;
}

export default function ProgressPage({
  loadHistory = fetchSessionHistory,
  loadProfile = fetchLearningProfile,
}) {
  const history = useLoaded(loadHistory);
  const profile = useLoaded(loadProfile);

  return (
    <main aria-labelledby="progress-heading">
      <h1 id="progress-heading">Your progress</h1>

      {profile.status === "loading" && <LoadingState />}
      {profile.status === "error" && <ErrorState kind={profile.error?.kind} />}
      {profile.status === "ready" && <LearningProfileSection profile={profile.data} />}

      {history.status === "loading" && <LoadingState />}
      {history.status === "error" && <ErrorState kind={history.error?.kind} />}
      {history.status === "ready" && <SessionHistoryList items={history.data?.items} />}
    </main>
  );
}
