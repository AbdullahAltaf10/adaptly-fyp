"""Shared helpers for Module 10 persistence.

Deliberately duplicates (rather than imports) Module 8's own
``analytics/persistence/base.py`` helpers of the same name: these are tiny,
generic, dependency-free utilities, and Module 10 does not take a hard
import dependency on Module 8's persistence package for them, the same way
Module 8's own persistence package does not depend on any other module's.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def strip_storage_id(document: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Drop the internal ``_id`` so callers only see contract-shaped fields."""

    if document is None:
        return None
    return {key: value for key, value in document.items() if key != "_id"}


def format_timestamp(value: datetime | str) -> str:
    """Render a timestamp as contract-style ISO 8601 UTC with a ``Z`` suffix."""

    if isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
