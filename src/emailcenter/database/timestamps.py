"""Shared UTC timestamp formatting for persisted records."""

from datetime import datetime, timezone


def utc_timestamp() -> str:
    """Return a UTC ISO-8601 timestamp with a trailing Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

