"""Shared constants for MOR."""

from __future__ import annotations

from collections.abc import Mapping

CONCEPT_HEADER_PREFIX = "# Concept:"
REQUIRED_SECTIONS = (
    "Canonical",
    "Aliases",
    "Definition",
    "Related",
    "NotSameAs",
    "QueryHints",
    "AnswerRequirements",
)
OPTIONAL_SECTIONS = ("Parents",)
ALL_SECTIONS = REQUIRED_SECTIONS + OPTIONAL_SECTIONS
LIST_SECTIONS = ("Aliases", "Related", "NotSameAs", "QueryHints", "AnswerRequirements", "Parents")
TEXT_SECTIONS = ("Canonical", "Definition")

DEFAULT_INTENT_SECTIONS: Mapping[str, tuple[str, ...]] = {
    "architecture_explanation": ("definition", "mechanism", "tradeoffs", "comparison"),
    "concept_comparison": ("definition", "similarities", "differences", "tradeoffs"),
    "troubleshooting": ("context", "signals", "causes", "actions"),
    "implementation_guide": ("definition", "mechanism", "implementation", "tradeoffs"),
}

SECTION_TITLES: Mapping[str, str] = {
    "definition": "Definition",
    "mechanism": "Mechanism",
    "tradeoffs": "Tradeoffs",
    "comparison": "Comparison",
    "similarities": "Similarities",
    "differences": "Differences",
    "context": "Context",
    "signals": "Signals",
    "causes": "Causes",
    "actions": "Actions",
    "implementation": "Implementation",
}

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "no",
    "of",
    "on",
    "or",
    "same",
    "the",
    "to",
    "where",
    "with",
}

MCP_SERVER_INFO = {
    "name": "mor",
    "version": "0.1.0",
}

