/**
 * The learner's documents, and the way into a study session.
 *
 * Until this existed, `/study` never received a `contentId` at all, so the
 * content viewer, dwell tracking and both content-dependent interventions had
 * no document to work on outside of tests. Choosing one here is what makes
 * Module 4's reading features reachable by an actual person.
 *
 * Four states, each with its own copy, because collapsing them is how a list
 * screen ends up showing "No documents" during a network failure: loading,
 * error, empty, and populated.
 *
 * Documents that are still `processing` or have `failed` are shown, not
 * hidden. A learner who just uploaded a video and sees nothing will upload it
 * again; telling them it is still being processed - or that it failed, and why
 * they cannot open it - is the difference between waiting and duplicating.
 */

import { FileText, FolderOpen, Globe, NotepadText, PlayCircle, Plus, Video } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listContent, sortNewestFirst } from "./api";
import { CONTENT_TYPE_LABELS, describeContentWarning } from "./warnings";
import { Alert, Button, Card, Spinner } from "../ui";

/** A quick visual anchor for scanning a list of mixed document types. */
const CONTENT_TYPE_ICONS = {
  pdf: FileText,
  research_paper: FileText,
  plain_text: NotepadText,
  website: Globe,
  youtube: PlayCircle,
  uploaded_video: Video,
};

function formatDate(iso) {
  const time = Date.parse(iso ?? "");
  if (!time) return null;
  return new Date(time).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function StatusBadge({ status }) {
  if (status === "ready" || !status) return null;
  const tone =
    status === "failed"
      ? "border-danger text-danger bg-danger-soft"
      : "border-warning text-warning bg-warning-soft";
  return (
    <span className={`inline-block border rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {status === "failed" ? "Could not be processed" : "Still processing"}
    </span>
  );
}

function DocumentRow({ item }) {
  const ready = item.status === "ready" || !item.status;
  const date = formatDate(item.created_at);
  const warnings = item.warnings ?? [];
  const TypeIcon = CONTENT_TYPE_ICONS[item.content_type] ?? FileText;

  return (
    <li className="border border-line rounded-md bg-surface p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <span className="flex items-center justify-center w-9 h-9 rounded-md bg-info-soft text-accent shrink-0 mt-0.5">
            <TypeIcon size={18} strokeWidth={1.75} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <h3 className="m-0 text-base font-semibold break-words">
              {item.title || "Untitled document"}
            </h3>
            <p className="mt-1 mb-0 text-sm text-muted">
              {CONTENT_TYPE_LABELS[item.content_type] ?? item.content_type}
              {typeof item.chunk_count === "number" && ` · ${item.chunk_count} sections`}
              {date && ` · added ${date}`}
            </p>
            <div className="mt-2">
              <StatusBadge status={item.status} />
            </div>
          </div>
        </div>

        {ready ? (
          <Link
            to={`/study?content=${encodeURIComponent(item.content_id)}`}
            className="inline-flex items-center min-h-10 px-4 py-2 rounded-md border border-accent bg-accent text-on-accent font-medium hover:bg-accent-hover"
          >
            Start session
          </Link>
        ) : (
          <span className="text-sm text-muted">
            {item.status === "failed" ? "Add it again to retry." : "Check back in a moment."}
          </span>
        )}
      </div>

      {warnings.length > 0 && (
        <ul className="mt-3 mb-0 pl-5 text-sm text-warning">
          {warnings.map((code) => (
            <li key={code}>{describeContentWarning(code)}</li>
          ))}
        </ul>
      )}
    </li>
  );
}

export default function LibraryPage() {
  const [state, setState] = useState({ status: "loading", items: [], error: null });

  const load = useCallback(() => {
    let cancelled = false;
    setState({ status: "loading", items: [], error: null });
    listContent()
      .then((response) => {
        if (cancelled) return;
        const items = sortNewestFirst(response.data);
        setState({ status: items.length ? "ready" : "empty", items, error: null });
      })
      .catch((error) => {
        if (!cancelled) setState({ status: "error", items: [], error });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => load(), [load]);

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="m-0 text-2xl font-semibold">My documents</h1>
        <Link
          to="/library/new"
          className="inline-flex items-center gap-1.5 min-h-10 px-4 py-2 rounded-md border border-accent bg-accent text-on-accent font-medium hover:bg-accent-hover"
        >
          <Plus size={16} strokeWidth={2} aria-hidden="true" />
          Add a document
        </Link>
      </div>

      {state.status === "loading" && <Spinner label="Loading your documents..." />}

      {state.status === "error" && (
        <Alert tone="error" title="Could not load your documents">
          <p className="mt-0">
            Your documents are safe - this is a problem reaching the server, not a sign they are
            gone.
          </p>
          <Button variant="secondary" onClick={load}>
            Try again
          </Button>
        </Alert>
      )}

      {state.status === "empty" && (
        <Card
          title="Nothing here yet"
          subtitle="Add a document and it will appear here, ready to study."
        >
          <div className="flex flex-col items-center text-center py-6">
            <FolderOpen size={36} strokeWidth={1.5} className="text-muted mb-3" aria-hidden="true" />
            <Link
              to="/library/new"
              className="inline-flex items-center gap-1.5 text-accent hover:underline font-medium"
            >
              <Plus size={16} strokeWidth={2} aria-hidden="true" />
              Add your first document
            </Link>
          </div>
        </Card>
      )}

      {state.status === "ready" && (
        <ul className="list-none p-0 m-0 flex flex-col gap-3">
          {state.items.map((item) => (
            <DocumentRow key={item.content_id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}
