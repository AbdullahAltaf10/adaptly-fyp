"""Module 8 orchestration/service layer (Issue #28).

Connects the pure metric engine (``domain``) with the persistence layer
(``persistence``). Contains no MongoDB driver calls of its own and no
Gemini/LLM dependency.
"""

from __future__ import annotations

from .finalization import (
    AnalyticsRepositories,
    FinalizationResult,
    SessionAccessDeniedError,
    SessionNotFoundError,
    finalize_session,
)

__all__ = [
    "AnalyticsRepositories",
    "FinalizationResult",
    "SessionAccessDeniedError",
    "SessionNotFoundError",
    "finalize_session",
]
