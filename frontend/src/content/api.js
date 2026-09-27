/**
 * Module 2's content endpoints, as far as a study session needs them.
 *
 * Only the two reads are here. Uploading is a separate screen that does not
 * exist yet, and putting its endpoints in this file would suggest the session
 * knows how to create content, which it does not.
 */

import api from "../api/client";

/**
 * One document with its chunks.
 *
 * `GET /content/{id}` returns the full shared-contract shape, chunks included.
 * The listing endpoint deliberately omits chunk text, so a viewer has to come
 * here rather than reusing a list entry.
 */
export function fetchContent(contentId) {
  return api.get(`/content/${contentId}`);
}

/** The learner's documents, metadata only — no chunk text. */
export function listContent() {
  return api.get("/content/list");
}
