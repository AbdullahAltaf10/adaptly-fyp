"""Collection name constant for Module 10 compliance storage.

Kept in its own file the same way Module 8 centralizes its own collection
names (``backend/app/analytics/persistence/collections.py``). The name
itself is not new -- CLAUDE.md (renamed to PROJECT_CONTEXT.md by PR #64)'s
architecture section already reserves ``compliance_reports`` for this
purpose in its MongoDB collections list.
"""

from __future__ import annotations

COMPLIANCE_REPORTS = "compliance_reports"
