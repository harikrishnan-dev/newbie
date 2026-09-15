"""Synthesize handbook data: replace real information with fake stand-ins.

Currently applies one rule - swapping every mention of the real org name for
a fictional one - but is structured as a list of replacement rules so more
can be added later (e.g. person names, emails) without reshaping the module.
"""

import re

from src.backfill.util import MarkdownDocument

FAKE_COMPANY_NAME = "Wall-E Waste Solutions"

# (pattern, replacement) rules, applied in order to every string in a document.
_REPLACEMENTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"gitlab", re.IGNORECASE), FAKE_COMPANY_NAME),
]


def _synthesize_text(text: str) -> str:
    """Apply every replacement rule to a single string."""
    for pattern, replacement in _REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def _synthesize_value(value):
    """Recursively apply `_synthesize_text` to every string in a (possibly
    nested) frontmatter value - dicts/lists/strings; other types pass through."""
    if isinstance(value, str):
        return _synthesize_text(value)
    if isinstance(value, dict):
        return {key: _synthesize_value(v) for key, v in value.items()}
    if isinstance(value, list):
        return [_synthesize_value(v) for v in value]
    return value


def synthesize_records(docs: list[MarkdownDocument]) -> list[MarkdownDocument]:
    """Replace real information (currently: the org name) with fake stand-ins.

    Applies the replacement rules throughout each document: its `path`, its
    `metadata` (recursively), and every section's heading and content.
    """
    return [
        MarkdownDocument(
            path=_synthesize_text(doc.path),
            metadata=_synthesize_value(doc.metadata),
            content=[
                {_synthesize_text(heading): _synthesize_text(text) for heading, text in section.items()}
                for section in doc.content
            ],
        )
        for doc in docs
    ]
