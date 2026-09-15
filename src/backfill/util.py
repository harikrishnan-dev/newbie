"""Private helpers for parsing, cleaning, and filtering handbook markdown."""

import re
from dataclasses import dataclass

import frontmatter
import yaml


@dataclass
class MarkdownDocument:
    path: str
    metadata: dict
    content: list[dict[str, str]]


# Backslash-escaped markdown special characters, e.g. "\_" -> "_".
_ESCAPED_MARKDOWN_CHAR = re.compile(r"\\([\\`*_{}\[\]()#+\-.!])")
# Three or more consecutive newlines (with optional whitespace-only lines in between).
_EXCESS_BLANK_LINES = re.compile(r"[ \t]*\n{3,}[ \t]*")
# Trailing whitespace at the end of a line.
_TRAILING_WHITESPACE = re.compile(r"[ \t]+\n")
# Fenced code blocks, kept verbatim while unwrapping the rest of the content.
_FENCED_CODE_BLOCK = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
# A line that starts a markdown block element (heading, list item, blockquote,
# table row, code fence, horizontal rule, or Hugo shortcode) rather than plain
# prose - these are left on their own line instead of being unwrapped.
_BLOCK_MARKER_LINE = re.compile(
    r"^(#{1,6}\s|[-*+]\s|\d+\.\s|>|\||```|~~~|-{3,}$|\*{3,}$|_{3,}$|\{\{)"
)
# A heading line, outside of fenced code blocks - splits content into sections.
_HEADING_LINE = re.compile(r"^#{1,6}[ \t]+(.+)$", re.MULTILINE)
# Markdown images and Hugo shortcodes, stripped out when checking for noise -
# a section with nothing but these has no searchable text of its own.
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_SHORTCODE = re.compile(r"\{\{[%<].*?[%>]\}\}", re.DOTALL)
# Hugo auto-generates near-empty stub pages for sections with only child
# pages, starting with one of these phrases.
_PLACEHOLDER_PREFIXES = ("this is a placeholder page", "placeholder page")
_MAX_PLACEHOLDER_LENGTH = 150
_MIN_CONTENT_LENGTH = 15


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a markdown file's leading YAML frontmatter from its body content."""
    try:
        metadata, body = frontmatter.parse(text)
    except yaml.YAMLError:
        return {}, _clean_content(text)
    return metadata, _clean_content(body)


def _split_sections(content: str, title: str = "") -> list[dict[str, str]]:
    """Break cleaned body content into sections keyed by their heading text.

    Returns a list of single-key dicts, in document order:
    `{heading_text: section_body}`. Any text before the first heading is kept
    under `title` (or an empty string if there's no title and no preamble).
    """
    code_spans = [m.span() for m in _FENCED_CODE_BLOCK.finditer(content)]

    def in_code_block(pos: int) -> bool:
        return any(start <= pos < end for start, end in code_spans)

    headings = [m for m in _HEADING_LINE.finditer(content) if not in_code_block(m.start())]

    if not headings:
        stripped = content.strip()
        return [{title: stripped}] if stripped else []

    sections = []
    if headings[0].start() > 0:
        preamble = content[: headings[0].start()].strip()
        if preamble:
            sections.append({title: preamble})

    for i, match in enumerate(headings):
        heading = match.group(1).strip()
        start = match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
        body = content[start:end].strip()
        sections.append({heading: body})
    return sections


def _clean_content(text: str) -> str:
    """Normalize whitespace and unescape markdown escape sequences in body text."""
    text = _ESCAPED_MARKDOWN_CHAR.sub(r"\1", text)
    text = _unwrap_paragraphs(text)
    text = _TRAILING_WHITESPACE.sub("\n", text)
    text = _EXCESS_BLANK_LINES.sub("\n\n", text)
    return text.strip()


def _unwrap_paragraphs(text: str) -> str:
    """Join hard-wrapped prose lines within a paragraph into a single line.

    A single "\\n" in markdown source is a soft line break (rendered as a
    space), while a blank line marks a real paragraph break. The handbook's
    source is hard-wrapped at a column width, so plain paragraphs are full of
    mid-sentence newlines; this joins those back into flowing text while
    leaving headings, lists, blockquotes, tables, and fenced code blocks
    untouched.
    """
    segments = _FENCED_CODE_BLOCK.split(text)
    unwrapped_segments = []
    for segment in segments:
        if _FENCED_CODE_BLOCK.fullmatch(segment):
            unwrapped_segments.append(segment)
            continue
        blocks = re.split(r"\n[ \t]*\n", segment)
        unwrapped_segments.append("\n\n".join(_unwrap_block(block) for block in blocks))
    return "".join(unwrapped_segments)


def _unwrap_block(block: str) -> str:
    """Reflow a single blank-line-delimited block line by line: each markdown
    block element (heading, list item, blockquote, table row, ...) starts a
    new output line, and any wrapped continuation line - including a list
    item's own hard-wrapped continuation - is joined onto it with a space."""
    lines = [line for line in block.split("\n") if line.strip()]
    if not lines:
        return block
    reflowed = [lines[0].rstrip() if _BLOCK_MARKER_LINE.match(lines[0].strip()) else lines[0].strip()]
    for line in lines[1:]:
        if _BLOCK_MARKER_LINE.match(line.strip()):
            reflowed.append(line.rstrip())
        else:
            reflowed[-1] = f"{reflowed[-1]} {line.strip()}"
    return "\n".join(reflowed)


def _is_noisy_content(content: str, min_content_length: int = _MIN_CONTENT_LENGTH) -> bool:
    """Whether a section's content is too sparse/boilerplate to be worth indexing.

    Flags content that's empty, is an auto-generated "placeholder page" stub
    (Hugo's default for a section with only child pages, e.g. "This is a
    placeholder page. Please see the links below..."), or has nothing left
    but Hugo shortcodes / markdown images once those are stripped out (no
    searchable prose of its own).
    """
    content = content.strip()
    if not content:
        return True

    lowered = content.lower()
    if len(content) < _MAX_PLACEHOLDER_LENGTH and lowered.startswith(_PLACEHOLDER_PREFIXES):
        return True

    stripped = _MARKDOWN_IMAGE.sub("", _SHORTCODE.sub("", content)).strip()
    return len(stripped) < min_content_length
