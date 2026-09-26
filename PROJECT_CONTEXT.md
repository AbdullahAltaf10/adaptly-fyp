# Adaptly — Autonomous Neurodiversity-Aware Learning Coach for Online Education
### Project Context for AI-Assisted Development

> Read this file fully before doing any work in this repo.
> **Rule #1: This file gives you architecture, contracts, and history. It does NOT give you
> live repo state.** Before touching any code, always verify actual current state with
> `git status`, `git branch --show-current`, `git log`, and `gh issue list` / `gh issue view`.
> This file can go stale; the repo and GitHub cannot.

---

## 1. Project Summary

Adaptly is a browser-based adaptive learning web application for adult learners. It monitors a
student's engagement in real time via webcam (no video stored — only numerical features extracted
locally/in-browser) and automatically adapts learning content (simplify / summarize / suggest
break / offer chatbot help) when the student is struggling or disengaged. It also supports an
HR/enterprise compliance use case (training manual distribution, attestation, document quality
heatmaps).

**Institution:** Air University Islamabad, Dept. of Computer Science
**Supervisor:** Dr. Sumera Hayat Khan
**Repo:** `https://github.com/AbdullahAltaf10/adaptly-fyp` (monorepo)
**Team:**
- Syed Sibtain Haider — 231589 — CV/ML pipeline & training, coordination, **and Module 4 (Adaptive Intervention), merged via PR #48**
- M. Hassan Jamshaid — 231574 — has completed his 3 modules independently, currently integrating them into this shared repo
- **Abdullah Altaf — 231625 — this is me, the person working with an AI coding assistant on this repo**

> A second doc, `ADAPTLY_PROJECT_HANDOFF.md`, circulates among the team but is **not** committed
> to this repo — it was shared out-of-band and is a dated snapshot, not a live source. Treat any
> such external doc the same way as this one: useful history and rationale, never trusted for
> current state. The traps/gotchas from it worth keeping have been folded into this file (Section
> 10) so they live in the repo instead of a file only some teammates have.

---

## 2. Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React.js |
| Backend | Python / FastAPI |
| Real-time comms | **Actually HTTP POST once per second today, not WebSocket.** A WebSocket upgrade is a known, not-yet-done gap — see Section 10. |
| Computer Vision | MediaPipe FaceLandmarker (Tasks API, in-browser landmark extraction, 478 points) |
| ML Training | **TensorFlow / Keras** (LSTM engagement classifier). Trained on Google Colab (free T4). Gaze regression / re-reading detection is a stub (`gaze_regression_detected` always `false`) — not built. |
| PDF Processing | `pypdf` (standard) + `pymupdf` (column-aware research-paper extraction) |
| Video Transcription | OpenAI Whisper (via `openai` package; inactive without `OPENAI_API_KEY`) |
| Web Content Extraction | BeautifulSoup |
| LLM | Google Gemini (`google-genai>=2.0`) — Module 4 content simplification, Module 5 assistant, Module 8 insight reports. All three read the same `GEMINI_API_KEY`/`GEMINI_MODEL` env vars, one key for the whole app. |
| Text-to-Speech | Not yet implemented — listed in scope, no code found in repo as of 2026-09-25 |
| Database | MongoDB Atlas via `pymongo` (needs `certifi`'s CA bundle on Windows — see Section 10) |
| Auth | Firebase Authentication (email/password + Google) |
| Design | Figma |
| VCS | Git / GitHub, `gh` CLI |

---

## 3. Module Map (11 modules — FINAL division per Architecture Diagram)

1. **Learner Profile & Access Management** — Login, Register, JWT auth, roles, profile, accessibility settings
2. **Content Processing** — PDF/website/video/YouTube/text ingestion, OCR, chunking, metadata, glossary extraction
3. **Real-Time Engagement Detection** — Webcam capture, face/eye/head tracking, LSTM engagement classifier, gaze regression (re-reading detection)
4. **Adaptive Intervention & Content Enhancement** — Simplify / summarize / break-suggestion / hint decision logic
5. **Context-Aware AI Assistant** — Prompt builder, chat history, context memory, Q&A, suggested questions
6. **CV–AI Integration Layer** — Feature fusion of camera + chat signals, session state management, trigger logic
7. **Audio Content Generation** — TTS, playback controls, voice/speed selection, downloadable audio
8. **Session Analytics & Insight Reporting** — see full deep-dive in Section 6 below
9. **HR Admin & Manual Management** — Manual upload, versioning, assignment, completion tracking
10. **Compliance Attestation Engine** — Engagement Quality Score (0–100), attestation report, critical-section evidence
11. **Document Intelligence Layer** — Paragraph difficulty heatmap, AI rewrite suggestions, HR approval workflow

### Authoritative Module Ownership Table

| Module | Name | Owner |
|---|---|---|
| 1 | Learner Profile & Access Management | Hassan |
| 2 | Content Processing | Hassan |
| 3 | Real-Time Engagement Detection | Sibtain — ✅ merged (PR #38-equivalent work + PR #44 evaluation/calibration fixes) |
| 4 | Adaptive Intervention & Content Enhancement | **Sibtain** — ✅ merged via PR #48 (originally unowned/TBD; Sibtain built and shipped it) |
| 5 | Context-Aware AI Assistant | **Abdullah** — ✅ merged. PR #43 is closed; PR #65 rebuilt it cleanly on current `develop` and resolved all of Hassan/Sibtain's review findings (router registration, CORS, frontend scaffold, dependency manifest, `google-genai` version). `/assistant/messages` is registered and live. |
| 6 | CV–AI Integration Layer | Sibtain |
| 7 | Audio Content Generation | Sibtain |
| 8 | Session Analytics & Insight Reporting | **Abdullah** — 🔨 CURRENT FOCUS (see Section 6) |
| 9 | HR Admin & Manual Management | Unassigned/TBD |
| 10 | Compliance Attestation Engine | **Abdullah** — ⏳ Not started (consumes Module 8 output) |
| 11 | Document Intelligence Layer | **Abdullah** — ⏳ Not started (consumes Module 8 output) |

### Hassan Jamshaid
- Owns Modules 1, 2, 4. Also separately integrating his own earlier prototype work
  (see `legacy/hassan-prototype` branch on origin) into the main repo structure.
- Issues have been created for this integration — review his code against
  `shared/contracts/` and this architecture before approving.

### Sibtain Haider
- Owns Modules 3, 6, 7 (CV/ML pipeline, integration layer, audio generation), plus general
  coordination.

---

## 4. System Flow (Swimlane Activity Diagram)

**Phase 1 — Session Initialization:** Login (POST `/login` → JWT) → Load Dashboard → Upload
Learning Material (POST `/content/upload`) → Content Processing (parse/OCR/transcript/chunk/
metadata) → Content stored, Content ID generated → Student clicks "Start Learning" → first
chunk retrieved and displayed.

**Phase 2 — Active Study Session:** Start webcam monitoring (POST `/engagement/start`) →
real-time loop: capture frame → face detect → eye track → head pose → extract features →
**predict learner state** (Focused / Drifting / Struggling / Fatigued / Recovered) →
- Focused → retrieve next chunk, continue.
- Needs intervention → determine type → Gemini generates response → optional TTS audio →
  merge → **update session analytics** (this is Module 8 writing events in real time) → return.

Loop repeats until the student ends the session.

**Phase 3 — Session Finalization & Reporting:** Click "Finish" (POST `/session/end`) → stop
monitoring → save session record → **Module 8 finalizes and computes the session summary** →
Module 10 generates Compliance Report → Module 11 generates Document Intelligence insights →
compile final Learning Report → return to student → display report → option to start another
session or Logout.

---

## 5. Architecture (high level)

```
Student/HR → Browser → React Frontend → FastAPI Backend (REST + WebSocket)
                                              │
        ┌───────────────┬───────────────┬────┴─────────┬───────────────┐
   User & Session   Engagement Det.   Intelligent    Content Proc.   Session Analytics
   Management       Module (Mod 3)    Agent (Mod 5)   (Module 2)     Engine (MODULE 8)
        │                 │                │               │               │
        │           MediaPipe→LSTM    Gemini/LLM      PDF/Web/Video         │
        │                 │                │           extraction          │
        └────────────┬────┴────────────────┴───────────────┴───────────────┘
                      Agentic AI & Context Fusion (Module 6)
                                  │
                      Adaptive Intervention Engine (Module 4)
              Simplify | Summarize | Suggest Break | Chatbot Assist
                                  │
                            MongoDB (Users, Session Logs, Chat History, Engagement Data)
```

MongoDB collections: `user_profiles`, `session_logs`, `chat_history`, `engagement_data`,
`processed_content`, `compliance_reports`, `document_insights`, plus Module 8's own analytics
collections (see Section 6.4).

---

## 6. MODULE 8 DEEP DIVE — Session Analytics & Insight Reporting

### 6.1 Purpose and Boundaries

Module 8 takes structured events produced by Modules 3, 4, and 5 and turns them into:
session-level engagement metrics, intervention effectiveness metrics, assistant interaction
metrics, session summaries, AI insight reports, multi-session learning profiles, and
data-quality indicators — all privacy-safe, for the dashboard and for downstream Modules 10/11.

**Module 8 must NOT own:** webcam processing, facial landmark extraction, raw audio processing,
frontend UI outside its own dashboard area, authentication, or LLM orchestration beyond its own
insight-report layer. It **consumes** structured outputs from Modules 3/4/5 — it doesn't produce
raw signals itself.

**Core architectural principle:** Module 8 calculates deterministic analytics from structured
events *first*. AI-generated insight text is a higher-level layer built *on top of* those
deterministic metrics — Gemini never touches raw data directly.

**Layer separation (must not be collapsed into one file):**
```
EVENTS → DOMAIN METRICS (pure, no infra deps) → SESSION ANALYTICS (orchestration/persistence)
       → INSIGHTS (Gemini + fallback) → LEARNING PROFILE (multi-session) → API / STORAGE
```

### 6.2 GitHub Milestone: "Module 8 — Session Analytics & Insight Reporting"

10 issues, dependency-ordered. **Status below was confirmed by directly inspecting the repo
(`git remote -v`, `git branch -a`, `git log`, `git status`) on 2026-08-25 — but branches/commits
move, so re-verify with `git status` / `gh issue list` before trusting it blindly.**

> **⚠️ Superseded — kept for history only.** The snapshot below is from 2026-08-25, before Issue
> #26 was even committed. Issues #25–#31 and #45/#46 are now merged into `develop`, and #32 is in
> review as PR #62 (state current as of 2026-09-25 — see Section 11, and `docs/module-8/README.md`
> for the live progress table). Do not treat anything below this line as current; it's left in
> place to show the reasoning trail, not as a status source.

**CONFIRMED REAL STATE (as of last check):**
- `origin/develop` exists. Currently contains: project structure (PR #1) + shared data contracts
  (PR #7 — `content.schema.json`, `engagement-event.schema.json`, `session.schema.json`,
  `user-profile.schema.json`). **Module 8's own contracts are NOT yet merged into `develop`.**
- `feature/25-module-8-analytics-contracts` — commit `b64026e` ("feat: define module 8 analytics
  contracts") is **pushed to origin**. Likely has an open PR awaiting review/merge into `develop`
  — verify with `gh pr list` or the GitHub PRs tab.
- `feature/26-module-8-metric-engine` — currently checked out locally, HEAD is still at the same
  commit `b64026e` as feature/25 (i.e. **zero commits made on this branch yet**). However,
  `backend/app/analytics/`, `backend/tests/analytics/`, `backend/__init__.py`,
  `backend/app/__init__.py`, `backend/tests/__init__.py` exist as **untracked, uncommitted local
  files** — this is where the actual metric-engine implementation (reported as 51 tests passing)
  physically lives right now. It has never been committed or pushed.
- Other branches on origin worth knowing about: `feature/17-assistant-foundation`,
  `feature/3-shared-data-contracts` (merged via PR #7), `feature/backend-dependencies`,
  `feature/project-structure` (merged via PR #1), `feature/ssh-test`, `legacy/hassan-prototype`.

| # | Title | Status (confirmed) | Depends on |
|---|---|---|---|
| **25** | Define Module 8 analytics contracts | Committed + pushed to origin (`b64026e`), **not yet merged to `develop`** — confirm PR status | Shared contracts (merged via PR #7) |
| **26** | Build Module 8 analytics metric engine | Code exists but is **100% uncommitted/untracked** on the `feature/26-module-8-metric-engine` branch. Reported as 51 tests passing per last working session — **must be re-verified by actually running the tests**, not assumed. | #25 |
| **27** | Add Module 8 analytics persistence and indexes | Not started | #25, #26 |
| **28** | Implement Module 8 session finalization and summary computation | Not started | #26, #27 |
| **29** | Build Module 8 analytics and session history APIs | Not started | #25, #27, #28 |
| **30** | Build Module 8 post-session analytics dashboard shell | Not started (can start with mocks, doesn't block on backend) | #25 |
| **31** | Add Module 8 engagement timeline and intervention log | Not started | #26, #29, #30 |
| **32** | Implement Module 8 Gemini insight report and fallback | Not started | #25, #28 |
| **33** | Build Module 8 multi-session learning profile | Not started | #25, #28, #29 |
| **34** | Integrate Module 8 with Modules 3, 4, and 5 | **In progress, all three producers wired.** Module 5 (this branch): assistant events now flow into `AssistantEventRepository` via `app/ai_assistant/analytics_sink.py`, two events per exchange (`direction: learner`/`assistant`); `/assistant/messages` now requires auth; frontend sends real `input_mode`. Module 3 (engagement events via `analytics_sink.py`) and Module 4 (`intervention/store.py` refactored to a facade over `InterventionEventRepository`) are tracked separately in PR #67 — **not yet merged as of this writing**, so don't assume those two exist on `develop` until confirmed with `git log`/`gh pr view 67`. Component-level wiring only; full end-to-end flow and Module 10/11 readiness not separately verified — see "Known follow-ups" in §6.9. | #25–#33 (all merged except #32, in review as PR #62) |

**Dependency shape:**
```
#25 Contracts -> #26 Metric Engine -> #27 Persistence
                                          |
                        +-----------------+-----------------+
                        v                                   v
                  #28 Finalization                    (frontend track)
                        |                              #30 Dashboard shell
                        v                                    |
                  #29 Analytics APIs <----------------+------+
                        |                              |
              +---------+---------+
              v         v         v
        #32 Insight  #33 Learning   #31 Timeline & intervention log
        Report       Profile
              |         |
              +----+----+
                    v
              #34 Real integration (Modules 3/4/5) + hardening
```

**IMMEDIATE NEXT STEP:** On branch `feature/26-module-8-metric-engine`, the untracked files
(`backend/app/analytics/`, `backend/tests/analytics/`) need to be: (1) reviewed, (2) have their
tests actually run and confirmed passing — do not trust the "51 tests passing" claim without
re-running it, (3) staged and committed with a proper message, (4) pushed to origin, (5) opened
as a PR into `develop`. Separately, confirm whether `feature/25`'s PR into `develop` has been
merged yet — Issue #26 conceptually depends on #25's contracts being in `develop`, though
practically the code was written against the contract files directly so it may not block
committing #26. Do not start #27's persistence work until #26 is committed, pushed, and its
tests verified.

### 6.3 Shared Contracts (`shared/contracts/`)

Pre-existing (from earlier shared-data-contract work, reviewed and merged by Hassan):
- `content.schema.json`
- `engagement-event.schema.json`
- `session.schema.json`
- `user-profile.schema.json`

Created by Issue #25 (Module 8-specific):
- `intervention-event.schema.json`
- `assistant-event.schema.json`
- `session-summary.schema.json`
- `analytics-report.schema.json`
- `learning-profile.schema.json`

Documentation: `docs/api/module-8-analytics-contracts.md`

**Contract rules:** JSON Schema Draft 2020-12, `schema_version` field required, snake_case
field names, ISO 8601 UTC timestamps, explicit enums, `null`/`unknown` allowed when an outcome
can't be determined. **Existing contracts are authoritative** — do not redesign them just
because you'd have designed them differently. If you spot a real architectural problem, report
it and explain the impact; don't silently change the contract. Contract changes only happen
through an explicit, deliberate issue.

**Key contract details worth remembering:**

- **Intervention Event** — types: `simplify_content`, `bullet_summary`, `break_suggestion`,
  `assistant_help_prompt`, `other`. Lifecycle: `offered -> displayed -> accepted -> dismissed ->
  completed -> failed`. Outcome: `not_observed | recovered | improved | unchanged | worsened |
  dismissed | unknown`. `helped` is `boolean | null` (never a fake default).
- **Assistant Event** — analytics-safe metadata only; deliberately excludes chat transcript,
  full prompts, full responses, API keys. Input modes: `typed | voice | suggested_question |
  not_applicable`. Response modes: `text | voice | mixed | not_applicable`. Learner signal:
  `neutral | confusion | frustration | unknown`.
- **Session Summary** — deterministic Module 8 metric-engine output for one session: duration,
  engagement distribution, longest focus, intervention stats, recovery stats, assistant usage,
  modality usage, critical-section engagement, completed chunks, coverage, quality flags,
  `metric_version`, `computed_at` (required, injected — not derived from wall clock during calc,
  for testability).
- **Analytics Report** — higher-level insight text generated via Gemini or deterministic
  fallback. Fallback status is named `deterministic_fallback` (not `template_fallback`).
  ~150 words when Gemini-generated.
- **Learning Profile** — cross-session pattern aggregate: repeated engagement states,
  intervention effectiveness, assistant usage patterns, recovery behavior, effective support
  methods, quality indicators. Includes ineffective/unknown outcome counts and quality flags.
  Must never become a dumping ground for raw sensitive data.

### 6.4 Privacy Rules (non-negotiable, apply everywhere in Module 8)

Never store or forward to Gemini/APIs:
- webcam frames, raw video recordings
- dense facial landmarks
- raw gaze coordinate streams, raw head-pose streams
- full chat transcripts (by default)
- full uploaded document text
- API keys / secrets
- unnecessary PII (learner email, etc.), medical/diagnostic info
- other learners' data

Module 8 works on **derived/structured** information only. Module 11 later consumes
anonymized/aggregated data on top of that — pseudonymize identifiers where required.

### 6.5 Critical Semantic Rules (do not violate these — they're load-bearing across the module)

1. **Unknown is not zero.** If the system can't determine a state, represent it as `unknown`
   (categorical) or `null` (numeric) — never as a fake `0` or a silently-assumed `focused` state.
   Long gaps between engagement events → `unknown` segments, not "focused by default."
2. **Missing recovery is not zero recovery duration.** If recovery can't be determined, return
   `null`, not `0`.
3. **Effectiveness rate excludes unknowns from the denominator.** e.g. `effective=4,
   ineffective=2, unknown=3` → rate is `4/(4+2)`, not `4/9`.
4. **Metric versioning is separate from schema versioning.** Schema version = data structure.
   Metric version = calculation rules (gap handling, recovery windows, smoothing policy,
   effectiveness rules). Current metric version: **1.0**. This exists so historical analytics
   stay reproducible even if calculation logic changes later.
5. **Learner-safe, non-clinical language everywhere user-facing** (dashboard, insight reports,
   intervention log). Never use words like "failure," "poor learner," "abnormal," "deficient,"
   "inattentive." Prefer neutral framing like "support was offered after signs of difficulty"
   or "outcome could not be determined."
6. **Post-session analytics only.** Never expose detailed engagement stats/scores during an
   *active* session — the study interface stays calm and number-free while studying.
7. **Small-sample caution.** Don't claim a support type is "best" or show a strong trend off 1–2
   data points. Use `insufficient_data` / `not_applicable` states instead of inventing trends.
8. **Idempotency everywhere.** Duplicate event submission, repeated session finalization, and
   repeated report generation must never create duplicate records or double-counted metrics.

### 6.6 Metric Engine (Issue #26) — Architecture Notes

Pure Python domain layer, deliberately with **zero dependency** on FastAPI, MongoDB, the Gemini
SDK, frontend, auth, or network. Location: `backend/app/analytics/domain/metrics.py`. Tests:
`backend/tests/analytics/fixtures.py`, `backend/tests/analytics/test_metrics.py`. This
independence is intentional — the metric engine must be testable in complete isolation.

**MetricConfig (v1.0) key values** — keep centralized, don't scatter magic numbers through code:
- expected sample interval: 5s · long-gap tolerance: 10s · minimum focused period: 5s
- recovery observation window: 120s · sustained recovery: 2 qualifying samples
- minimum coverage: 80% · excessive-unknown threshold: >20%

**Known audit history (for context, don't "re-fix" things already fixed):**
- Original smoothing was too aggressive and could erase legitimate short `struggling` /
  `fatigued` / `recovered` periods — corrected to a conservative, tested policy.
- Deep-thinking detection originally overrode contradictory states unconditionally — corrected
  to proper precedence/compatibility rules.
- Recovery timing, overlapping interventions, event-boundary handling, duplicate events, and
  assistant-success counting ambiguity were all audited and addressed; regression tests exist
  for each.

**Two known, intentionally-unresolved architectural gaps — do not "fix" silently:**
1. **No correlation ID** in the assistant-event contract to pair a learner request with its
   response. Current approach: conservatively count successful assistant events rather than
   claiming exact conversational exchange counts. Changing this requires a contract-level
   decision, not a code workaround.
2. **No explicit pause intervals** in the session contract. Current approach: treat
   `duration_seconds` as authoritative and flag timestamp inconsistencies rather than inventing
   a pause model. Same — contract decision required before changing this.
3. Full third-party `jsonschema` package validation has not been run (not installed) — don't
   install new dependencies without a reason tied to the current issue.
4. The minimum evidence threshold for `effective_support_methods` in the learning profile
   (Issue #33) has intentionally not been finalized — must be defined via config/metric-version/
   tests, not invented silently.

### 6.7 Git Workflow for Module 8

```
develop
   |
feature/<issue-number>-<short-description>
   | implementation -> tests -> git diff --check -> commit -> push -> PR -> review -> merge to develop
```
- Never work directly on `develop`.
- Never merge another module's branch into a Module 8 branch unless explicitly required.
- Before any commit: `git status`, `git diff --check`, `git branch --show-current`.

### 6.8 Working Method (carried over from prior sessions with this repo — keep using it)

For each issue:
1. **Inspect first** — current repo state, existing contracts, related modules. Don't assume;
   verify.
2. **Implement only what the specified issue asks for.** Avoid unrelated modifications. Don't
   install dependencies unless the issue requires it. Don't commit unless asked.
3. **Audit strictly afterward** — self-review or ask for a second pass — and report a clear
   `PASS` / `NEEDS CHANGES` before proposing a commit.
4. **Run available tests/validation** before calling anything done.
5. Treat existing schemas/contracts and Issue #26's completed behavior as **authoritative**.
   Don't redesign completed work without an explicit reason and issue to justify it.

### 6.9 Definition of Done for Module 8 (overall milestone, for orientation — not all done yet)

- [x] Contracts: analytics event, session summary, analytics report, learning profile, privacy documented
- [~] Metric engine: timeline, unknown gaps, distribution, longest focus, smoothing, deep-thinking,
      recovery, intervention effectiveness, assistant analytics, critical-section metrics, quality
      flags, deterministic summary — implemented, 51 tests passing, pending final commit
- [ ] Session analytics service / persistence (#27, #28)
- [ ] Analytics API layer (#29)
- [ ] Dashboard shell + timeline/intervention log UI (#30, #31)
- [ ] Gemini insight report + deterministic fallback (#32)
- [ ] Multi-session learning profile with evidence thresholds (#33)
- [~] Real integration with Modules 3/4/5 (#34): all three producers now wire into Module 8's
      real repositories (Module 3 direct sink, Module 4 facade — both PR #67, not yet merged;
      Module 5 sink + auth + input_mode — this branch). Not yet done: a verified end-to-end
      flow test and Module 10/11 downstream readiness confirmation.
- [ ] Module 10/11 downstream readiness confirmed

**Known follow-ups from #34 (Module 5):**
- `analytics_contracts.py`'s `intent` field is always `"unknown"` — a documented placeholder,
  not real classification. No intent classifier exists in Module 5 today; building one is
  separate work, not part of this wiring.
- `api.py` records `model_name=None` on every error path (`AssistantConfigurationError`,
  `AssistantProviderError`, `AssistantProviderTimeoutError`), even when a real Gemini call was
  attempted and failed. `service.py`'s exception paths don't currently carry the attempted
  model name back out to the caller; threading it through would widen
  `create_assistant_response`'s error handling beyond what this issue's wiring needed. See the
  comment directly above the try/except chain in `api.py`.
- `suggested_question_used`, `intent`, and `learner_signal` are mirrored onto both the learner
  and assistant events for one exchange, since the contract has no neutral "not applicable to
  this direction" value for any of the three (unlike `input_mode`/`response_mode`, which do).
  This is a judgement call made in `analytics_contracts.py`'s own module docstring, not
  something the contract dictates — worth a second opinion if anyone disagrees with the
  interpretation.
- No end-to-end test exists that runs a real learner session through Module 3 → Module 4 →
  Module 5 → Module 8 and confirms the analytics collections end up populated correctly
  together. Each module's wiring is unit/component-tested in isolation.

---

## 7. GitHub Conventions for This Repo (general)

- Milestones = Modules
- Issues = individual features/tasks within a module
- When asked to work on a module, **always fetch the live issue list and issue details from
  GitHub first** via `gh issue list --milestone "<name>"` and `gh issue view <number>` — never
  assume from memory or from this file, since issue content or status may have changed.
- When reviewing Hassan's integration work: `gh issue list --assignee <his-username>` (confirm
  actual username first), cross-check his code against `shared/contracts/` and this architecture.

### 7.1 Scope Discipline — Staying Aligned Across Modules (repo-wide, not just Module 8)

This came out of PR #43 (Module 5): a branch built weeks earlier, against an older `develop`,
collided badly with everything that had merged since — a router file that would have silently
deleted other modules' endpoints, a duplicate frontend scaffold, conflicting CORS config, two
disagreeing dependency manifests. None of it was carelessness; it was the natural result of a
branch drifting out of sync with the rest of the repo while it sat waiting for review. To avoid
repeating this:

1. **Before starting an issue**, re-read this file's section for that module *and* the live issue
   on GitHub — not memory of either. If the branch will live more than a couple of days before
   review, plan to rebase onto `develop` right before opening the PR, not just at branch creation.
2. **Build only what the issue asks for.** Don't re-scaffold something another module already
   owns (frontend app shell, router registration, CORS, dependency manifests) — touch those
   additively (one line, one entry), never by replacing the file wholesale.
3. **Shared files are additive-only by convention**: `backend/app/api/router.py`,
   `backend/app/main.py`'s middleware, `backend/requirements.txt`, `.gitignore`. A PR that
   rewrites one of these instead of adding a line to it should be treated as a design smell worth
   a second look before requesting review.
4. **One dependency manifest** (`backend/requirements.txt`). Don't introduce a second one
   (e.g. `pyproject.toml`) for a single module's needs.
5. **Keep this file current as part of the PR that changes shared plumbing** — not as separate
   cleanup afterward. If your PR changes router registration, CORS, the dependency manifest, or a
   module's ownership/status, update the relevant section here in the same PR.
6. **Self-review against this section before requesting teammate review** — catching a
   router.py rewrite or a duplicate scaffold yourself costs a few minutes; catching it after two
   people have reviewed costs a full re-review cycle.

---

## 8. Constraints to Respect Project-Wide

- No webcam video is ever stored or transmitted — only numeric feature vectors (gaze, EAR, head pose).
- No alerts/sounds/flashing UI during active sessions — interventions must be calm, silent, dismissible.
- Accessibility: OpenDyslexic font option, adjustable line spacing, high contrast, sentence-level
  focus isolation — relevant wherever Module 8's dashboard UI is touched.
- Desktop/laptop only — no mobile support in scope.

---

## 9. Module 3 essentials (for anyone building on top of its output, not just Sibtain)

Modules 4, 5, 6 and 8 all consume what Module 3 produces, so getting this wrong ripples widely.
Full detail lives in `docs/model/model-card.md`; this is the summary every other module needs.

- **Five engagement states, only three come from the model.** `focused`, `drifting`,
  `struggling` are LSTM output; `fatigued` and `recovered` are rule-based (DAiSEE has no fatigue
  dimension, and "recovered" needs a comparison across time a single clip can't express). Every
  engagement event carries a `source` field: `lstm`, `rule`, or `hybrid`.
- **`confidence` describes the reported state, not the model's top class** (fixed in PR #44's
  `confidence_for()` — before that fix it reported the wrong probability in 3 scenarios). If you
  persist or display confidence, make sure you're on a branch with that fix.
- **Never quote raw accuracy for this model — use per-class recall / macro F1.** A classifier
  that always guesses "focused" scores 84.7% on the same test set. Struggling recall is the
  product-critical number: **10% on the held-out test set** with the model that actually runs
  (18% on validation — that gap is split instability, not a range). Per-subject centring plus a
  tuned threshold was measured to reach ~0.245 recall and 12 of 19 subjects at the selected
  operating point, **but the calibrated artifacts are not loaded at runtime**, so nothing in the
  running system benefits from it yet. Re-measure with `ml/evaluation/calibrated_threshold.py`
  rather than quoting these numbers second-hand.
- **`blink_rate` is not a real blink rate.** It's byte-identical to `eye_openness` — a real blink
  (100–400ms) can't be measured at a 1-frame-per-second sample rate. Don't build anything that
  depends on it meaning what its name implies.
- **The model does not consume real head-pose degrees.** `solvePnP` is implemented and used by
  rule detectors, but the LSTM was fitted on a simplified geometric estimate on a different scale.
  Consequence: **opening your mouth reads as "struggling"**, because the simplified estimate uses
  the chin — not because confusion was detected. Never demo this as confusion detection.
- **`gaze_regression_detected` (re-reading detection) is always `false` — it's an unbuilt stub**,
  not a working feature with a bug. Don't build downstream logic that assumes it ever fires.
- **Layout constraint for anyone building UI the learner reads during a session:** don't put text
  in the lower part of the screen. Looking down lowers eye-openness and reads as "fatigued" —
  a sensing limitation, not something a threshold tweak fixes.
- **Never validated on real users** — all published numbers are against DAiSEE (80% male,
  controlled recording conditions), not this system's actual learners.

---

## 10. Traps & gotchas (merged in from team handoff notes, so they live in the repo)

These cost someone real time to discover. Read before you hit the same wall.

- **CORS must stay a regex, not a fixed origin list.** Vite silently moves to 5174, 5175... when
  5173 is taken, and browsers treat `localhost` and `127.0.0.1` as different origins. The correct,
  deliberate setting is `allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$"` — replacing
  it with a fixed list is the single most common cause of an opaque "Network Error" that looks
  like an auth bug. Tighten it before deployment, don't replace it now.
- **`certifi` is required for MongoDB Atlas on Windows.** Without `tlsCAFile=certifi.where()`,
  writes silently fail to appear in Atlas — no error, just missing data.
- **Windows clock drift causes Firebase 401s** (`Token used too early`). Fix: Settings → Time &
  Language → Sync now.
- **Never run `npm audit fix --force`** — it upgraded Vite past the installed Node version and
  broke the project once already.
- **TensorFlow must be imported lazily, never at module load** — importing it at import time costs
  ~20 seconds of backend startup. It's lazy now with a background warm-up thread; keep it that way.
- **`.gitattributes` is load-bearing for `ml/artifacts/`.** `ml/artifacts/** -text` must stay
  *below* `* text=auto` (last matching rule wins). Without it, git rewrites the model artifact's
  line endings on checkout, its SHA-256 changes, and `verify_artifacts()` fails on a file nobody
  actually edited.
- **Watch for missing trailing newlines in `.gitignore` and `requirements.txt`.** A missing
  newline once fused two package names into one invalid line and made the backend uninstallable
  for the whole team (Issue #5).
- **Don't inspect FastAPI routes via `app.routes`** — lazy `_IncludedRouter` objects make it look
  like nothing is registered even when it is. Use `/openapi.json` instead.
- **`Closes #N` in a PR description does not auto-close the issue on this repo.** GitHub only
  auto-closes when a PR merges into the *default* branch (`main`), and everything here merges into
  `develop`. Close issues by hand.
- **Commit whenever something works, not only when the whole task is done.** A `git stash pop` on
  this project once permanently deleted two files that had never been committed.
- **Verify ML thresholds against a live face, not just synthetic test fixtures.** The head-pose
  sign was wrong three separate times; each time the unit tests encoded the same wrong assumption
  and passed against a gate that could never fire in reality.

---

## 11. What the Assistant Should Do Right Now

Module 8 is the active focus. As of 2026-09-25: Issues #25–#31 (#31 shipped as PR #60) and
#45/#46 are merged into `develop`; Issue #32 (Gemini insight report) is implemented and open as
PR #62, awaiting review from Sibtain/Hassan; Issue #33 (multi-session learning profile, shipped
as PR #63) is merged into `develop`. Verify this against `git log`/`gh pr list` before trusting
it — this section goes stale fast, same as everything else in this file (see Rule #1 at the top).

Follow the working method in Section 6.8, respect the contracts in Section 6.3, and never violate
the semantic rules in Section 6.5. Issue #33 in particular: follow `learning-profile.schema.json`
exactly rather than the issue's prose where they differ (see Section 6.3's contract rule) — flag
any mismatch in the PR rather than silently extending the contract.
