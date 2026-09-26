/**
 * The document the learner actually reads (issue #47).
 *
 * Two jobs, and the second is the one that is easy to get wrong.
 *
 * **Render each chunk as its own element.** Module 2 already splits content
 * into chunks; rendering them as one blob would throw that away. Each chunk
 * gets its own element so something can be said about *which paragraph* the
 * learner is on.
 *
 * **Hand every chunk element to whoever is watching.** `onChunkRef` is a seam,
 * deliberately optional: this component works on its own with nothing
 * attached, and Module 4 passes `dwell.register` through it. That is what
 * makes `simplify_content` and `bullet_summary` able to fire at all — both
 * need to know the active chunk, and until now nothing registered one, so
 * `seconds()` returned 0 and neither could ever be offered.
 *
 * The ref callback is called with `null` on unmount, which is how React
 * signals the element is going away. `useDwell.register` treats that as
 * "stop watching this chunk", so no special handling is needed here.
 *
 * Scope section 6.8 forbids scores or engagement indicators during an active
 * session, so nothing here renders state, confidence, or dwell. A learner
 * reading this page cannot tell they are being measured.
 */

import { useCallback } from "react";

/**
 * `is_critical` comes from Module 9's HR tagging. Module 4 already halves its
 * dwell threshold for these, so difficulty is caught sooner where
 * comprehension matters most. It is deliberately NOT shown to the learner:
 * marking a paragraph "critical" on screen is pressure, and scope section 6.4
 * asks for support delivered without disruption.
 */
function ContentChunk({ chunk, onChunkRef }) {
  const ref = useCallback(
    (element) => {
      if (onChunkRef) onChunkRef(chunk.chunk_id, element);
    },
    [onChunkRef, chunk.chunk_id]
  );

  return (
    <section ref={ref} data-chunk-id={chunk.chunk_id} style={{ marginBottom: "1.75rem" }}>
      {chunk.section_title && (
        <h3 style={{ margin: "0 0 0.5rem", fontSize: "1.05rem" }}>
          {chunk.section_title}
        </h3>
      )}
      <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{chunk.text}</p>
    </section>
  );
}

export default function ContentViewer({ content, onChunkRef, lineSpacing = 1.7 }) {
  if (!content) {
    return (
      <section aria-labelledby="content-heading">
        <h2 id="content-heading">Reading</h2>
        <p>No document loaded.</p>
      </section>
    );
  }

  const chunks = Array.isArray(content.chunks) ? content.chunks : [];

  // Module 2 guarantees `order`, but a document assembled by hand or by a
  // future importer might not, so sort rather than trust the array order.
  const ordered = [...chunks].sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

  return (
    <article aria-labelledby="content-heading">
      <h2 id="content-heading" style={{ marginTop: 0 }}>
        {content.title || "Untitled document"}
      </h2>

      {ordered.length === 0 ? (
        <p>This document has no readable sections.</p>
      ) : (
        <div style={{ lineHeight: lineSpacing, maxWidth: "70ch" }}>
          {ordered.map((chunk) => (
            <ContentChunk key={chunk.chunk_id} chunk={chunk} onChunkRef={onChunkRef} />
          ))}
        </div>
      )}
    </article>
  );
}
