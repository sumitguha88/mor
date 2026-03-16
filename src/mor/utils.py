"""Utility helpers for MOR."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable

from mor.constants import STOPWORDS

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_SPACE_RE = re.compile(r"\s+")


def normalize_term(value: str) -> str:
    text = value.strip().lower()
    text = _NON_ALNUM_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def slugify(value: str) -> str:
    normalized = normalize_term(value)
    return normalized.replace(" ", "-")


def tokenize(value: str) -> list[str]:
    tokens = [token for token in normalize_term(value).split(" ") if token and token not in STOPWORDS]
    return tokens


def unique_preserve(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        normalized = normalize_term(item)
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(item)
    return ordered


def json_dumps(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=False, ensure_ascii=True)

