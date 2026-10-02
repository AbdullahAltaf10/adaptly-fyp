/**
 * Add a document - six ways, one screen.
 *
 * Scope section 6.2: PDF, research paper, pasted text, YouTube link, uploaded
 * video and web address. They are one screen with a tab per method rather than
 * six pages because the learner's question is always the same ("get this into
 * Adaptly") and only the input differs.
 *
 * Things here that are decisions rather than plumbing:
 *
 * - **A duplicate is not a failure and not a success.** The backend returns the
 *   existing document for an identical upload (`duplicate_of_existing`). Saying
 *   "uploaded!" would be wrong - nothing new was created - and treating it as
 *   an error would be worse. It is reported plainly, with a link to the copy
 *   they already have.
 * - **Long operations say how long.** A video is uploaded *and* transcribed in
 *   one request, which can take minutes. A progress bar that reaches 100% and
 *   then sits there looks like a hang, so once the bytes are sent the copy
 *   changes to say the server is still working.
 * - **Cancelling is not an error.** An aborted request is dropped silently.
 * - **Document warnings are shown at the moment of adding**, not only later in
 *   the library. "This is Urdu, support will be less accurate" is most useful
 *   before someone has committed to studying it.
 *
 * Everything is validated on the client first so an obviously wrong file never
 * starts a 200 MB upload, but the server re-checks all of it - see
 * `uploadValidation.js`.
 */

import { FileText, Globe, NotepadText, PlayCircle, Video } from "lucide-react";
import { useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  addFromUrl,
  addFromYoutube,
  pasteText,
  uploadPdf,
  uploadResearchPaper,
  uploadVideo,
} from "./api";
import {
  MAX_PDF_BYTES,
  MAX_TEXT_CHARS,
  MAX_VIDEO_BYTES,
  MB,
  collectFieldErrors,
  describeUploadError,
  validatePastedText,
  validatePdfFile,
  validateTitle,
  validateVideoFile,
  validateWebUrl,
  validateYoutubeUrl,
} from "./uploadValidation";
import { describeContentWarning } from "./warnings";
import { Alert, Button, Card, Field, Input, Textarea } from "../ui";

/**
 * One entry per method. `kind` decides which form fields exist; `submit` does
 * the call. Keeping it as data means the tab list, the form and the copy cannot
 * drift apart.
 */
const METHODS = [
  {
    id: "pdf",
    label: "PDF",
    icon: FileText,
    kind: "file",
    accept: ".pdf,application/pdf",
    validate: validatePdfFile,
    submit: uploadPdf,
    hint: `A PDF up to ${MAX_PDF_BYTES / MB} MB. It needs selectable text - a scan of a page will not work.`,
    wait: "Usually a few seconds.",
  },
  {
    id: "research",
    label: "Research paper",
    icon: FileText,
    kind: "file",
    accept: ".pdf,application/pdf",
    validate: validatePdfFile,
    submit: uploadResearchPaper,
    hint: `A paper as a PDF, up to ${MAX_PDF_BYTES / MB} MB. Columns and the abstract are handled for you.`,
    wait: "Usually a few seconds.",
  },
  {
    id: "text",
    label: "Paste text",
    icon: NotepadText,
    kind: "text",
    wait: "Immediate.",
  },
  {
    id: "web",
    label: "Web page",
    icon: Globe,
    kind: "url",
    validate: validateWebUrl,
    submit: addFromUrl,
    placeholder: "https://example.com/article",
    hint: "The public address of a page. Pages that need a login cannot be read.",
    wait: "Usually under a minute.",
  },
  {
    id: "youtube",
    label: "YouTube",
    icon: PlayCircle,
    kind: "url",
    validate: validateYoutubeUrl,
    submit: addFromYoutube,
    placeholder: "https://www.youtube.com/watch?v=...",
    hint: "A video with captions. We read the captions, not the audio.",
    wait: "Can take a couple of minutes.",
  },
  {
    id: "video",
    label: "Video file",
    icon: Video,
    kind: "file",
    accept: "video/*,.mp4,.mov,.m4v,.webm,.mkv,.avi",
    validate: validateVideoFile,
    submit: uploadVideo,
    hint: `MP4, MOV, WebM, MKV or AVI up to ${MAX_VIDEO_BYTES / MB} MB. It is transcribed automatically.`,
    wait: "Can take several minutes. Keep this page open until it finishes.",
  },
];

export default function UploadPage() {
  const [methodId, setMethodId] = useState("pdf");
  const method = METHODS.find((m) => m.id === methodId);

  const [file, setFile] = useState(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");

  // Which fields have reached a point where a problem is worth mentioning.
  // A file is different from a typed field here: picking one already IS the
  // decision (there is no "still deciding" moment the way there is mid-word
  // in a text box), so a file counts as touched the instant one is chosen.
  const [touched, setTouched] = useState({});
  const [failure, setFailure] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const [result, setResult] = useState(null);

  const controllerRef = useRef(null);

  // Recomputed every render from the live values - the same reason as
  // RegisterPage's: showing a problem immediately, and clearing it the moment
  // it stops being true, without an effect chasing the values around. This is
  // what makes "wrong file" or "URL doesn't look right" appear before the
  // upload starts, not after a wait ending in a form the learner has to redo.
  const liveErrors =
    method.kind === "file"
      ? collectFieldErrors({ file: method.validate(file) })
      : method.kind === "url"
      ? collectFieldErrors({ url: method.validate(url) })
      : collectFieldErrors({ title: validateTitle(title), text: validatePastedText(text) });
  const errors = Object.fromEntries(
    Object.entries(liveErrors).filter(([field]) => touched[field])
  );
  const touchField = (field) => setTouched((prev) => ({ ...prev, [field]: true }));

  const reset = () => {
    setTouched({});
    setFailure(null);
    setResult(null);
    setProgress(null);
  };

  const switchMethod = (id) => {
    // Switching mid-upload would leave a request running against a form that no
    // longer exists on screen.
    if (busy) return;
    reset();
    setMethodId(id);
    setFile(null);
    setUrl("");
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFailure(null);

    // Reveal every remaining problem at once on submit - unchanged from
    // before. Live validation only changes *when* a message can first appear.
    setTouched({ file: true, url: true, title: true, text: true });
    if (Object.keys(liveErrors).length > 0) return;

    const controller = new AbortController();
    controllerRef.current = controller;
    const options = { signal: controller.signal, onProgress: setProgress };

    setBusy(true);
    try {
      const response =
        method.kind === "file"
          ? await method.submit(file, options)
          : method.kind === "url"
          ? await method.submit(url, options)
          : await pasteText({ title, text }, options);
      setResult(response.data);
    } catch (error) {
      const message = describeUploadError(error);
      if (message) setFailure(message);
    } finally {
      setBusy(false);
      setProgress(null);
      controllerRef.current = null;
    }
  };

  const cancel = () => controllerRef.current?.abort();

  // Bytes are all sent but the server is still working (transcribing, fetching).
  const serverWorking = busy && progress === 100;

  return (
    <div className="max-w-2xl mx-auto">
      <Link to="/library" className="text-sm text-accent hover:underline">
        &larr; Back to my documents
      </Link>
      <h1 className="mt-1 mb-1 text-2xl font-semibold">Add a document</h1>
      <p className="mt-0 mb-4 text-sm text-muted">
        A PDF, a research paper, pasted text, a website address, a YouTube video, or a video file
        - pick whichever fits what you have.
      </p>

      <div role="tablist" aria-label="How to add a document" className="flex flex-wrap gap-1 mb-4">
        {METHODS.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            id={`tab-${m.id}`}
            aria-selected={m.id === methodId}
            aria-controls="add-panel"
            disabled={busy && m.id !== methodId}
            onClick={() => switchMethod(m.id)}
            className={[
              "inline-flex items-center gap-1.5 px-3 py-2 rounded-md border text-sm font-medium min-h-10",
              "transition-colors duration-150",
              m.id === methodId
                ? "bg-accent text-on-accent border-accent"
                : "bg-surface text-ink border-line hover:bg-page",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            ].join(" ")}
          >
            <m.icon size={15} strokeWidth={1.75} aria-hidden="true" />
            {m.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id="add-panel" aria-labelledby={`tab-${methodId}`}>
        <Card>
          {failure && <Alert tone="error">{failure}</Alert>}

          {result ? (
            <Result result={result} onAnother={reset} />
          ) : (
            <form onSubmit={handleSubmit} noValidate>
              {method.kind === "file" && (
                <Field label="File" error={errors.file} hint={method.hint} required>
                  {(aria) => (
                    <input
                      {...aria}
                      type="file"
                      accept={method.accept}
                      disabled={busy}
                      // Reset on switch so a stale file from another tab cannot
                      // be submitted to this one.
                      key={method.id}
                      onChange={(e) => {
                        setFile(e.target.files?.[0] ?? null);
                        touchField("file");
                      }}
                      className="block w-full text-sm file:mr-3 file:px-3 file:py-2 file:rounded-md file:border file:border-line file:bg-surface file:text-ink"
                    />
                  )}
                </Field>
              )}

              {method.kind === "url" && (
                <Field label="Web address" error={errors.url} hint={method.hint} required>
                  {(aria) => (
                    <Input
                      {...aria}
                      type="url"
                      inputMode="url"
                      autoComplete="off"
                      placeholder={method.placeholder}
                      value={url}
                      disabled={busy}
                      invalid={Boolean(errors.url)}
                      onChange={(e) => setUrl(e.target.value)}
                      onBlur={() => touchField("url")}
                    />
                  )}
                </Field>
              )}

              {method.kind === "text" && (
                <>
                  <Field label="Title" error={errors.title} required>
                    {(aria) => (
                      <Input
                        {...aria}
                        placeholder="Safety induction, chapter 3"
                        value={title}
                        disabled={busy}
                        invalid={Boolean(errors.title)}
                        onChange={(e) => setTitle(e.target.value)}
                        onBlur={() => touchField("title")}
                      />
                    )}
                  </Field>
                  <Field
                    label="Text"
                    error={errors.text}
                    hint={`Up to ${MAX_TEXT_CHARS.toLocaleString()} characters.`}
                    required
                  >
                    {(aria) => (
                      <Textarea
                        {...aria}
                        placeholder="Paste the text you want to study..."
                        value={text}
                        disabled={busy}
                        invalid={Boolean(errors.text)}
                        onChange={(e) => setText(e.target.value)}
                        onBlur={() => touchField("text")}
                      />
                    )}
                  </Field>
                </>
              )}

              {busy && (
                <div className="mb-4" aria-live="polite">
                  {progress !== null && !serverWorking && (
                    <div
                      role="progressbar"
                      aria-label="Upload progress"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={progress}
                      className="h-2 rounded bg-page border border-line overflow-hidden"
                    >
                      <div className="h-full bg-accent" style={{ width: `${progress}%` }} />
                    </div>
                  )}
                  <p className="mt-2 mb-0 text-sm text-muted">
                    {serverWorking
                      ? "Sent. Still working on it - this can take a while for longer files."
                      : progress !== null
                      ? `Uploading... ${progress}%`
                      : "Working on it..."}
                  </p>
                </div>
              )}

              <p className="mt-0 mb-4 text-sm text-muted">{method.wait}</p>

              <div className="flex gap-2">
                <Button type="submit" busy={busy} busyLabel="Adding...">
                  Add document
                </Button>
                {busy && (
                  <Button type="button" variant="secondary" onClick={cancel}>
                    Cancel
                  </Button>
                )}
              </div>
            </form>
          )}
        </Card>
      </div>
    </div>
  );
}

function Result({ result, onAnother }) {
  const duplicate = Boolean(result.duplicate_of_existing);
  const warnings = result.warnings ?? [];
  const id = result.content_id;

  return (
    <div>
      <Alert
        tone={duplicate ? "info" : "success"}
        title={duplicate ? "You already have this" : "Added"}
      >
        {duplicate
          ? "This is identical to a document already in your library, so nothing new was created."
          : `"${result.title || "Your document"}" is ready to study.`}
      </Alert>

      {warnings.length > 0 && (
        <Alert tone="warning" title="Worth knowing before you start">
          <ul className="m-0 pl-5">
            {warnings.map((code) => (
              <li key={code}>{describeContentWarning(code)}</li>
            ))}
          </ul>
        </Alert>
      )}

      <div className="flex flex-wrap gap-2">
        {id && (
          <Link
            to={`/study?content=${encodeURIComponent(id)}`}
            className="inline-flex items-center min-h-10 px-4 py-2 rounded-md border border-accent bg-accent text-on-accent font-medium hover:bg-accent-hover"
          >
            Start a session
          </Link>
        )}
        <Button variant="secondary" onClick={onAnother}>
          Add another
        </Button>
        <Link
          to="/library"
          className="inline-flex items-center min-h-10 px-4 py-2 text-accent hover:underline"
        >
          Go to my documents
        </Link>
      </div>
    </div>
  );
}
