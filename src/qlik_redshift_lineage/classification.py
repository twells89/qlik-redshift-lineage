"""Explicit source-system classification."""

from __future__ import annotations

import re
from typing import Iterable, Optional


def _normal(value: object) -> str:
    return str(value or "").strip().lower()


def classify(connection: dict, rules: Iterable[dict] = ()) -> str:
    values = [connection.get(key) for key in ("id", "name", "host", "source_system", "raw")]
    text = " ".join(_normal(value) for value in values)
    raw = connection.get("raw") if isinstance(connection.get("raw"), dict) else {}
    explicit = raw.get("source_system") or raw.get("sourceSystem") or raw.get("technology") or raw.get("engine")
    if explicit:
        explicit_text = _normal(explicit)
        if "redshift" in explicit_text:
            return "redshift"
        if "snowflake" in explicit_text:
            return "snowflake"
    for rule in rules:
        pattern = str(rule.get("match", ""))
        if pattern and re.search(pattern, text, flags=re.I):
            source_system = _normal(rule.get("source_system"))
            if source_system in {"redshift", "snowflake"}:
                return source_system
    return "unknown"
