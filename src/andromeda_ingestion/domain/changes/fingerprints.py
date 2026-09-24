"""Stable canonical fingerprints for idempotency and change detection."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(value: Any) -> str:
    return sha256(canonical_json(value).encode("utf-8")).hexdigest()


def natural_key(*parts: Any) -> str:
    return fingerprint(list(parts))
