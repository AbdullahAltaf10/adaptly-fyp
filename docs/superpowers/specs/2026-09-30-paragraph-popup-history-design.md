# Paragraph Focus Highlight + Anchored Intervention Popup + Persistent Assistant History — Design

Status: approved in chat (2026-09-30), pending written-spec review.
Owner: sibtain2345 (Module 3/4/5 area).
Scope: Module 3 (engagement, paragraph highlight), Module 4 (intervention delivery),
Module 5 (assistant, persistent history) — frontend + backend.

Builds directly on `2026-09-29-dwell-fusion-rereading-design.md` (already shipped):
the four-signal paragraph fusion (`useDwellFusion`, `fusionScoring.js`) is the
signal source this spec consumes, unchanged.

## 1. Problem

Three things the user asked for, tightly coupled because they all live on the
study page and share the same "which paragraph, how confident" signal:

1. **Nothing on screen shows which paragraph the system thinks the learner is
   reading.** For a defense demo this needs to be visible (opaquely, without
   violating scope 6.8's "no scores during an active session" rule).
2. **Auto-triggered interventions (`simplify_content`, `bullet_summary`) render
   at the bottom of the page**, disconnected from the paragraph they are
   about, and have **no lifecycle tied to dwell at all** — today they close
   only on an explicit button click (`InterventionHost.jsx` / `useIntervention.js`).
   Requested: anchor the popup beside the relevant paragraph, keep it open for
   as long as the learner is anywhere in that paragraph (not per-word), and
   auto-close only once they have genuinely moved to a different paragraph.
3. **The assistant panel (`AssistantPanel.jsx`) has no real conversation
   history.** Its `messages` state is client-only and is thrown away the
   moment `session_id` changes — verified by reading the component: there is
   no `GET` endpoint anywhere that reloads a prior conversation. The
   `analytics_sink.record_assistant_exchange` calls are Module 8 analytics
   events, not a retrievable thread.

## 2. Key finding that resolves the hardest part

The user's stated worry — "stuck on line 1 → popup shows → unstuck → stuck on
a different word in the same paragraph a moment later → popup should not have
flickered" — turns out to already be prevented by the existing fusion
architecture, not something this spec needs to build:

`activeChunkId` (from `useDwellFusion`) already operates at **chunk
(paragraph) granularity, not word or line granularity**. `ContentChunk`
(`ContentViewer.jsx`) registers one DOM element per whole paragraph; nothing
in the fusion pipeline (visibility ratio, gaze-quadrant, WebGazer point, idle
mouse) ever reports a position finer than "which paragraph". So as long as
the learner is anywhere inside the same paragraph, `activeChunkId` never
changes, and `dwell.seconds()` (fixed in the previous spec's review pass to
track the *fused* chunk specifically) keeps accumulating continuously.

**Conclusion: the popup's lifecycle should be driven by `chunk_id` identity
against the live `activeChunkId`, not by re-deriving a new sub-paragraph
signal.** This is the deciding factor of the whole design below — no new ML
signal, no new dwell granularity, just correct lifecycle wiring on top of
what already exists.

Two alternatives considered and rejected:
- **Word/line-level sub-position tracking.** Would need new signal
  granularity the system deliberately does not have (and the scope
  document's own stated 2-3cm gaze accuracy makes word-level positioning
  physically unreliable regardless — see the earlier spec's section 2).
  Solves a problem that chunk-level tracking already avoids.
- **Fixed-duration popup (e.g., always show for N seconds).** Rejected by
  the user explicitly: does not respect "stays until the paragraph is
  actually finished", and would either cut off a still-reading learner or
  linger after they have moved on.

## 3. Paragraph focus highlight

`ContentChunk` (`content/ContentViewer.jsx`) gains a boolean derived from
`chunk.chunk_id === activeChunkId && fusionConfidence >= HIGHLIGHT_CONFIDENCE_THRESHOLD`,
passed down from `StudySession.jsx` (which already has both values from
`useDwellFusion`). `HIGHLIGHT_CONFIDENCE_THRESHOLD = 0.3` (estimate, same
order as `SCATTERED_CONFIDENCE_THRESHOLD` from the readability-probe design —
not a new number invented from nothing).

Visual: a subtle background tint (`bg-accent/10`, no border, no icon, no
percentage) applied to the `<section>` already rendered — an additive
className, not a new element. Scope 6.8 compliance: no number, no label, no
motion; the tint appears and disappears with focus, nothing else.

## 4. Anchored popup

### 4.1 Positioning

The already-registered chunk element (`elementsRef` inside `useDwellFusion`)
exposes `getBoundingClientRect()`. A new small hook,
`useAnchoredPosition(chunkElement)`, tracks that rect on scroll/resize
(passive listeners, rAF-throttled) and returns `{ top, left, width }` for the
currently-focused paragraph's element.

Responsive rule: at `>= 1024px` viewport width, the popup renders as a
fixed-position panel in a right-hand rail (`position: fixed; right: 16px`),
vertically aligned to the paragraph's top, following scroll. The main content
column's `max-width` narrows by the rail's width at this breakpoint so the
two never overlap (a real layout reservation, not an overlay-over-text).
Below `1024px` there is no room for a side rail: the popup renders inline,
directly under the paragraph's own element, pushing following paragraphs
down — same component, different CSS position mode, chosen by a
`window.innerWidth` media-query hook already idiomatic in this codebase's
Tailwind usage.

### 4.2 Lifecycle

New hook `useParagraphPopup({ intervention, activeChunkId })`, wrapping the
existing `useIntervention`:

- When `useIntervention` reports a new `current` intervention whose
  `chunk_id` matches `activeChunkId`, the popup opens.
- On every fusion tick, if `activeChunkId !== popup.chunkId`, start a
  **3-second confirmation timer** (`PARAGRAPH_CHANGE_CONFIRM_MS = 3000`,
  estimate — flicker-guard, same category as the previous spec's own
  `REVISIT_MIN_DWELL_SECONDS`). If `activeChunkId` is still different after
  the timer, and still different at the moment it fires (re-checked, not
  assumed), call `useIntervention`'s `complete()`. If the learner returns to
  the popup's own paragraph before the timer fires, the timer is cancelled
  and nothing closes.
- If `activeChunkId` becomes `null` (learner scrolled the paragraph
  entirely out of view, or looked away), the same 3-second confirm-then-close
  rule applies — being briefly off-screen is not different from being
  briefly on a neighboring paragraph.

### 4.3 Manual controls

Two independent affordances, both additive to the existing
`GeneratedText` card:
- **Dismiss (×)**: calls `dismiss()` (existing `STATUS_DISMISSED` path,
  unchanged semantics) — full close, will not reopen for this intervention.
- **Collapse/expand toggle**: a **frontend-only** boolean (`collapsed`,
  local `useState`, not reported to the backend — collapsing is not
  "dismissing" or "completing" in Module 8's measurement model, it is a
  display preference). Collapsed state renders a small tab anchored at the
  same position; expanding it restores the full card. Collapsing does not
  reset or pause the paragraph-change timer above — the popup (collapsed or
  not) still auto-closes on a confirmed paragraph change.

### 4.4 Own scroll

The popup body (generated text + original toggle + inline chat, below) gets
`max-height: min(60vh, 420px); overflow-y-auto` — long simplifications or
bullet lists scroll inside the card; the card's own height never pushes the
page layout around while open.

### 4.5 Inline follow-up chat

A compact `QuestionInput` (the same component `AssistantPanel` already
uses) rendered inside the popup card, below the generated content. Submitting
a question here calls the **same** `sendAssistantMessage` API the sticky
panel uses, with `current_chunk` pre-filled from the popup's own paragraph
(no re-selection needed) — and appends to the **same persistent history**
(section 5), tagged with a `source: "popup"` field so the sticky panel can
later render it distinguishably ("Simplified this paragraph" vs. a typed
question) without it being a second, separate conversation.

## 5. Persistent assistant history (backend)

New collection `assistant_messages` (Mongo), one document per turn:

```
{
  _id, uid, timestamp,
  role: "user" | "assistant",
  content: str,
  source: "panel" | "popup",           # where the turn originated
  trigger: "question" | "simplify_content" | "bullet_summary" | null,
  content_id: str | null,               # which document, if any
  chunk_id: str | null,                 # which paragraph, if any
  session_id: str | null,               # which study session, if any
}
```

`uid`-keyed, not `session_id`-keyed — matches the confirmed decision (one
continuous history site-wide, not per-session). New endpoints:

- `GET /assistant/history?limit=50&before=<timestamp>` — paginated, newest
  page first (matches how a chat app loads: latest visible, scroll up for
  older).
- Existing `POST /assistant/messages` gains one additive field,
  `source: "panel" | "popup" = "panel"`, and now also **writes** the
  user+assistant turn into `assistant_messages` (previously it only wrote
  to the analytics sink; both continue, analytics is unaffected).
- The **existing** `GET /intervention/{id}/content` endpoint (Module 4,
  `app/intervention/api.py`) gains one additive side effect: on a successful
  generation, it writes an assistant-role turn into `assistant_messages`
  directly (`source: "popup"`, `trigger` set to the intervention's own
  type, `chunk_id`/`content_id` from the intervention record it already
  has). No new endpoint, no extra frontend round-trip, no dependency on the
  frontend remembering to call anything — the same server-records-what-
  actually-happened principle already used for this endpoint's own
  analytics. No `role: "user"` turn is written (nothing was asked, so
  nothing simulates a question).

`AssistantPanel.jsx` loads `GET /assistant/history` once on mount (site-wide
now, see the companion spec) instead of starting from an empty array, and
appends locally exactly as it already does — no behavior change to its own
render logic beyond the initial hydration.

## 6. Error handling

- History fetch failure on mount: falls back to an empty conversation
  (today's actual starting state) rather than blocking the page — a chat
  history that fails to load is a degraded experience, not a broken one.
- Popup position hook: if the anchored element has been unmounted (chunk
  scrolled out of the DOM's registered set — should not happen since
  `ContentViewer` renders every chunk, but defensive nonetheless), the popup
  falls back to the existing bottom-of-page rendering rather than crashing.
- The history-write inside `/intervention/{id}/content` is wrapped the same
  way this endpoint already wraps its analytics side effects: a failure
  there is caught and logged, never allowed to turn a successful generation
  into an error response — history recording is additive, not load-bearing
  for what the learner sees.

## 7. Testing plan

- `useAnchoredPosition` — synthetic rect + scroll/resize event tests.
- `useParagraphPopup` — the 3s-confirm-then-close timer, cancel-on-return,
  null-activeChunkId case, mirroring the mutation-tested style already used
  for `rereading.py`'s own dwell-based timer.
- `ContentChunk` highlight — renders the tint class only when both
  conditions hold.
- Backend: `test_assistant_history.py` — `GET` pagination, `POST` write,
  the `source`/`trigger` fields round-trip correctly, ownership isolation
  (one learner cannot read another's history — same pattern as every other
  `uid`-scoped store in this codebase).
- Responsive layout: a snapshot-style test asserting the popup's CSS
  position mode switches at the 1024px breakpoint (jsdom viewport mock).

## 8. Out of scope for this spec

Site-wide assistant availability was proposed as a companion spec and then
explicitly declined by the user (2026-09-30): the assistant widget stays
study-session-only, never mounted on the dashboard/library/settings pages.
`assistant_messages` is still `uid`-keyed and still one continuous history
(not reset per session) — that part of the design stands on its own merit
(matches the user's explicit ChatGPT/Claude-style continuity request) and
does not depend on where the widget is mounted; it simply is never read
from anywhere outside a study session now. Module 6 (CV-AI Integration
Layer) — separate, already has its own research plan
(`sibtain-workspace/FYP_DEFENSE_GUIDE/10_MODULE_6_AND_GAZE_PLAN.md`).
