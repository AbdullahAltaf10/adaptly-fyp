"""Module 8 insight-report generation (Issue #32).

The layer above deterministic metrics in Module 8's architecture
(EVENTS -> DOMAIN METRICS -> SESSION ANALYTICS -> INSIGHTS -> LEARNING
PROFILE, see CLAUDE.md 6.1). Everything in this package operates only on an
already-computed, contract-shaped session summary — never raw events, chat
transcripts, or webcam-derived data.
"""

from __future__ import annotations
