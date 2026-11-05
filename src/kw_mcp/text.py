"""KLAS bodies (assignments, posts, syllabi) are HTML; tools return them as plain text."""

from __future__ import annotations

import re
from html.parser import HTMLParser

MAX_TEXT_CHARS = 8000

_BLOCK = {"p", "div", "br", "tr", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr"}
_SKIP = {"script", "style"}


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
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …(이하 생략)"
