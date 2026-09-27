/**
 * Module 2's content endpoints: the two reads a session needs, and the six ways
 * of adding a document.
 *
 * The ingest endpoints take **multipart form data**, not JSON - `UploadFile`
 * and `Form(...)` on the backend. Sending JSON here fails with a 422 that says
 * a field is missing, which reads as if the client forgot something when it
 * actually used the wrong encoding.
 *
 * Every ingest call is given its own timeout. The shared client's 20 seconds is
 * right for a profile lookup and wrong for this: a 200 MB video has to upload
 * and then be transcribed, all inside one request. Left at 20 seconds, axios
 * gives up and reports a failure while the server carries on and finishes the
 * job - the learner is told it failed and the document appears in their
 * library anyway. Each timeout below is deliberately generous for that reason,
 * and the UI says how long to expect.
 */

import api from "../api/client";

/** How long each kind of ingest may take before the client stops waiting. */
export const TIMEOUT_MS = {
  text: 60_000,
  website: 90_000,
  youtube: 3 * 60_000,
  pdf: 2 * 60_000,
  video: 15 * 60_000,
};

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

/**
 * The learner's documents, metadata only - no chunk text.
 *
 * The backend returns these in no particular order, so ordering is the
 * caller's job (`sortNewestFirst`).
 */
export function listContent() {
  return api.get("/content/list");
}

export function sortNewestFirst(items) {
  // ISO-8601 strings sort correctly as text, but parsing also tolerates a
  // missing value, which sinks to the bottom instead of throwing.
  return [...(items ?? [])].sort((a, b) => {
    const left = Date.parse(a?.created_at ?? "") || 0;
    const right = Date.parse(b?.created_at ?? "") || 0;
    return right - left;
  });
}

function postForm(path, form, { timeout, onProgress, signal } = {}) {
  return api.post(path, form, {
    timeout,
    signal,
    // Axios sets the multipart boundary itself. Setting Content-Type by hand
    // here would drop it and the server would see an unparseable body.
    onUploadProgress: onProgress
      ? (event) => {
          if (event.total) onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
        }
      : undefined,
  });
}

function fileForm(file) {
  const form = new FormData();
  form.append("file", file);
  return form;
}

export const uploadPdf = (file, options) =>
  postForm("/content/upload-pdf", fileForm(file), { timeout: TIMEOUT_MS.pdf, ...options });

export const uploadResearchPaper = (file, options) =>
  postForm("/content/upload-research-paper", fileForm(file), {
    timeout: TIMEOUT_MS.pdf,
    ...options,
  });

export const uploadVideo = (file, options) =>
  postForm("/content/upload-video", fileForm(file), { timeout: TIMEOUT_MS.video, ...options });

export function pasteText({ title, text }, options) {
  const form = new FormData();
  form.append("title", title.trim());
  form.append("text", text);
  return postForm("/content/paste-text", form, { timeout: TIMEOUT_MS.text, ...options });
}

export function addFromUrl(url, options) {
  const form = new FormData();
  form.append("url", url.trim());
  return postForm("/content/from-url", form, { timeout: TIMEOUT_MS.website, ...options });
}

export function addFromYoutube(url, options) {
  const form = new FormData();
  form.append("url", url.trim());
  return postForm("/content/from-youtube", form, { timeout: TIMEOUT_MS.youtube, ...options });
}
