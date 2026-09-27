/**
 * Client-side checks for the six ways of adding a document.
 *
 * **These mirror the server, they do not replace it.** `app/content/validation.py`
 * is the real gate: it checks the file's actual bytes (magic numbers) because
 * the browser's idea of a file's type is just a string the client sends. All
 * this file can do is tell a learner "that is 300 MB" *before* they wait for it
 * to upload and be refused, which for a video is the difference between one
 * second and several minutes.
 *
 * So the numbers below are copied from the backend and must move with it.
 * There is a test that pins them; if `validation.py` changes a limit, that test
 * is the reminder to change this.
 *
 * Every validator returns a message string or null, the same shape as the auth
 * forms, so `Field` can wire the message to its input for screen readers.
 */

export const MB = 1024 * 1024;

/** Mirrors backend/app/content/validation.py. */
export const MAX_PDF_BYTES = 25 * MB;
export const MAX_VIDEO_BYTES = 200 * MB;
export const MAX_TEXT_CHARS = 500_000;
export const MIN_TEXT_CHARS = 50;

/**
 * Extensions only as a first filter. A `.pdf` that is not a PDF still gets
 * refused by the server's signature check; this just stops the obvious
 * mistake (picking a Word file) without a round trip.
 */
const PDF_EXTENSIONS = [".pdf"];
const VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"];

function extensionOf(name) {
  const dot = (name ?? "").lastIndexOf(".");
  return dot === -1 ? "" : name.slice(dot).toLowerCase();
}

function formatSize(bytes) {
  return bytes >= MB ? `${(bytes / MB).toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

function validateFile(file, { extensions, maxBytes, noun, allowedLabel }) {
  if (!file) return `Choose ${noun} to upload.`;
  if (!extensions.includes(extensionOf(file.name))) {
    return `That does not look like ${noun}. Choose a ${allowedLabel} file.`;
  }
  // Checked before size: an empty file is a clearer problem than a big one.
  if (file.size === 0) return "That file is empty.";
  if (file.size > maxBytes) {
    return `That file is ${formatSize(file.size)}. The limit is ${formatSize(maxBytes)}.`;
  }
  return null;
}

export const validatePdfFile = (file) =>
  validateFile(file, {
    extensions: PDF_EXTENSIONS,
    maxBytes: MAX_PDF_BYTES,
    noun: "a PDF",
    allowedLabel: "PDF",
  });

export const validateVideoFile = (file) =>
  validateFile(file, {
    extensions: VIDEO_EXTENSIONS,
    maxBytes: MAX_VIDEO_BYTES,
    noun: "a video",
    allowedLabel: "MP4, MOV, WebM, MKV or AVI",
  });

export function validateTitle(value) {
  const title = (value ?? "").trim();
  if (!title) return "Give this document a title.";
  if (title.length > 200) return "Keep the title under 200 characters.";
  return null;
}

export function validatePastedText(value) {
  // Whitespace is stripped by the server before it counts, so count the same way.
  const text = (value ?? "").trim();
  if (!text) return "Paste some text to study.";
  if (text.length < MIN_TEXT_CHARS) {
    return `That is only ${text.length} characters. Paste at least ${MIN_TEXT_CHARS}.`;
  }
  if (text.length > MAX_TEXT_CHARS) {
    return `That is ${text.length.toLocaleString()} characters. The limit is ${MAX_TEXT_CHARS.toLocaleString()}.`;
  }
  return null;
}

/**
 * Only http(s). The server also blocks private and internal addresses (an SSRF
 * check before any fetch); this cannot and does not try to reproduce that, it
 * just catches "forgot the https://" and pasting a non-link.
 */
export function validateWebUrl(value) {
  const raw = (value ?? "").trim();
  if (!raw) return "Paste the web address.";
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    return "That does not look like a web address. Include the https:// at the start.";
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    return "Only http and https addresses work.";
  }
  return null;
}

const YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
]);

export function validateYoutubeUrl(value) {
  const generic = validateWebUrl(value);
  if (generic) return generic;
  const host = new URL(value.trim()).hostname.toLowerCase();
  if (!YOUTUBE_HOSTS.has(host)) return "That is not a YouTube link.";
  return null;
}

/**
 * Turn whatever an upload threw into a sentence.
 *
 * The backend raises `HTTPException(detail=...)` with wording it wrote for
 * users ("The uploaded file is empty.", "File is too large..."), so that
 * message is shown as-is when there is one. Everything below is what to say
 * when there is not, and each case needs different advice - "the server is
 * down" and "you cancelled" and "your session expired" are not the same
 * failure.
 */
export function describeUploadError(error) {
  if (error?.code === "ERR_CANCELED" || error?.name === "CanceledError") {
    return null; // the learner cancelled; not an error worth showing
  }

  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  // FastAPI's validation errors put a list here, not a string.
  if (typeof detail === "string" && detail.trim()) return detail;

  if (status === 401 || status === 403) return "Your session has expired. Sign in again.";
  if (status === 413) return "That file is too large.";
  if (status === 422) return "That could not be turned into readable content.";
  if (error?.code === "ECONNABORTED") {
    return "This took too long and was stopped. Try a shorter file, or try again.";
  }
  if (!error?.response) return "Could not reach the server. Check your connection and try again.";
  return "Something went wrong adding that. Try again.";
}

/**
 * Keep only the checks that failed, so a form shows every problem at once
 * rather than one per submit.
 *
 * Deliberately not imported from `auth/validation.js`: content should not
 * depend on the auth module for a three-line helper, and the two would then
 * have to change together.
 */
export function collectFieldErrors(checks) {
  const errors = {};
  for (const [field, message] of Object.entries(checks)) {
    if (message) errors[field] = message;
  }
  return errors;
}
