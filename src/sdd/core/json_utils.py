"""Canonical JSON serialization for SDD (I-EL-CANON-1)."""
from __future__ import annotations

import datetime
import json
from typing import Any


def canonical_json(data: dict[str, Any]) -> str:
    """Stable JSON for payload_hash (I-CMD-2b): sorted keys, no whitespace, ISO8601 UTC, no sci notation."""

    def _default(obj: Any) -> Any:
        if isinstance(obj, datetime.datetime):
            if obj.tzinfo is None:
                return obj.strftime("%Y-%m-%dT%H:%M:%SZ")
            return obj.astimezone(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        raise TypeError(f"Not serializable: {type(obj)!r}")

    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=_default)
