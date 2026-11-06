"""KLAS bodies (assignments, posts, syllabi) are HTML; tools return them as plain text.

Text written by other people (professors' posts, assignment sheets, attachments, syllabus notes)
goes to the model inside a fixed marker, so it can tell that text apart from instructions.
"""

from __future__ import annotations

import re
import unicodedata
from html.parser import HTMLParser

MAX_TEXT_CHARS = 8000

# Untrusted text goes out as OPEN + "\n" + text + "\n" + CLOSE. Any copy of the marker word inside
# the text is removed first, so a post can't close the block early and write "outside" it.
MARKER_WORD = "KLAS_CONTENT"
CONTENT_OPEN = f"<<<{MARKER_WORD}"
CONTENT_CLOSE = f"{MARKER_WORD}>>>"
_MARKER = re.compile(re.escape(MARKER_WORD), re.IGNORECASE)
_LINE_BREAKS = str.maketrans({"\r": "\n", "\x0b": "\n", "\x0c": "\n", "\u2028": "\n", "\u2029": "\n"})

_BLOCK = {"p", "div", "br", "tr", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr"}
_SKIP = {"script", "style"}


def clean(text: str | None) -> str:
    """Drop invisible format characters (zero-width, bidi overrides, the Unicode tag block: all
    category Cf) and control characters other than line breaks and tabs. Hidden text of this
    kind is a known way to slip instructions past a reader."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").translate(_LINE_BREAKS)
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cf", "Cc"))


def untrusted(text: str | None) -> str | None:
    """Text someone else wrote, cleaned and wrapped in the content marker; None when empty."""
    body = clean(text)
    while _MARKER.search(body):  # removing one copy can join the halves of another
        body = _MARKER.sub("", body)
    body = body.strip("\n")
    if not body.strip():
        return None
    return f"{CONTENT_OPEN}\n{body}\n{CONTENT_CLOSE}"


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self._skip += 1
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in ("td", "th"):
            self.parts.append(" | ")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def html_to_text(html: str | None, limit: int = MAX_TEXT_CHARS) -> str:
    """Readable text: block tags become line breaks, list items "- ", whitespace squeezed."""
    if not html:
        return ""
    parser = _Text()
    parser.feed(html)
    parser.close()
    text = clean("".join(parser.parts).replace("\xa0", " "))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …(이하 생략)"
