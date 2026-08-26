"""Shared helpers for Module 8 repositories.

Repositories accept any object exposing pymongo's ``Database``/``Collection``
interface. Real code passes a ``pymongo.database.Database``; tests pass a
``mongomock.database.Database``. Neither this module nor any repository
imports pymongo directly, so the metric engine's zero-MongoDB-dependency
boundary in ``backend/app/analytics/domain`` is never touched by persistence
code, and persistence code stays swappable between the real driver and its
in-memory double.
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
