/**
 * The two Module 4 endpoints.
 *
 * There is no endpoint for triggering an intervention. The decision is made
 * server-side inside /engagement/analyze, because it depends on signals the
 * browser is deliberately never given - a client that could report how badly
 * it was struggling could fabricate its own interventions. Analyze returns an
 * `intervention` field, and these two are what happens next.
 */

import api from "../api/client";

/**
 * Report what happened to an intervention.
 *
 * This is not optional bookkeeping. Module 8 starts measuring whether an
 * intervention helped from a particular delivery status, and `offered` - which
 * is where every intervention starts - is not one of them. An intervention
 * that is rendered and never reported stays at `offered` and contributes to no
 * metric in the system, while still looking perfectly fine in the database.
 *
 * The response carries `starts_recovery_measurement`, which says whether the
 * status just reported is one that counts. The tests assert on it rather than
 * assuming.
 */
export function reportStatus(interventionId, { sessionId, status }) {
  return api.post(`/intervention/${interventionId}/status`, {
    session_id: sessionId,
    delivery_status: status,
  });
}

/**
 * Fetch the text to show, for the two types that have generated content.
 *
 * Separate from the analyze response because a model call takes seconds and
 * analyze runs every ten, serialised per session - generating there would
 * stall engagement detection behind it. A cache hit here is immediate.
 *
 * Returns `original` alongside `generated` so the learner can see what was
 * changed, and `generator` so model output is never confused with the
 * extractive fallback.
 */
export function fetchContent(interventionId) {
  return api.get(`/intervention/${interventionId}/content`);
}
