/**
 * Loads the document a session is about, once.
 *
 * Separate from `ContentViewer` so the viewer stays a pure render of whatever
 * it is handed — that is what lets its tests run without a network layer, and
 * what would let a future offline mode supply content from somewhere else.
 *
 * A failure here is reported rather than swallowed. Without content there is
 * nothing to read, so hiding the error would leave a blank page with no
 * explanation.
 */

import { useEffect, useState } from "react";

import { fetchContent } from "./api";

export function useContent(contentId) {
  const [content, setContent] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(Boolean(contentId));

  useEffect(() => {
    if (!contentId) {
      setContent(null);
      setError(null);
      setLoading(false);
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchContent(contentId)
      .then((response) => {
        if (cancelled) return;
        setContent(response.data);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        // A session that cannot load its document is broken in a way the
        // learner needs told about, so this surfaces rather than retrying
        // silently.
        setError(err?.message || "Could not load this document.");
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [contentId]);

  return { content, error, loading };
}
