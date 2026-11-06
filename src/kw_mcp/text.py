"""KLAS bodies (assignments, posts, syllabi) are HTML; tools return them as plain text.

Text written by other people (professors' posts, assignment sheets, attachments, syllabus notes)
goes to the model inside a fixed marker, so it can tell that text apart from instructions.
"""

from __future__ import annotations

import functools
import re
import unicodedata
from html.parser import HTMLParser

MAX_TEXT_CHARS = 8000

# Untrusted text goes out as OPEN + "\n" + text + "\n" + CLOSE. Any copy of the marker word inside
# the text is removed first, so a post can't close the block early and write "outside" it.
MARKER_WORD = "KLAS_CONTENT"
CONTENT_OPEN = f"<<<{MARKER_WORD}"
CONTENT_CLOSE = f"{MARKER_WORD}>>>"
_LINE_BREAKS = str.maketrans({"\r": "\n", "\x0b": "\n", "\x0c": "\n", "\u2028": "\n", "\u2029": "\n"})
# Default_Ignorable_Code_Point (Unicode DerivedCoreProperties): drawn as nothing at all. Most of these
# are category Cf; the rest are U+034F (combining grapheme joiner), the variation selectors, the
# Hangul fillers (U+115F, U+1160, U+3164, U+FFA0) and a few Mongolian and Khmer marks.
_IGNORABLE = re.compile("[\u00ad\u034f\u061c\u115f\u1160\u17b4\u17b5\u180b-\u180f\u200b-\u200f\u202a-\u202e"
                        "\u2060-\u206f\u3164\ufe00-\ufe0f\ufeff\uffa0\ufff0-\ufff8\U0001bca0-\U0001bca3"
                        "\U0001d173-\U0001d17a\U000e0000-\U000e0fff]")
# Half of a UTF-16 pair with no other half: it can't be written as UTF-8, so the MCP SDK fails the
# whole tool answer on one. KLAS JSON can carry one as a "\ud83d" escape.
_SURROGATE = re.compile("[\ud800-\udfff]")
# For finding the marker only: characters that read as the marker's letters. NFKD already folds
# fullwidth and other compatibility forms (fullwidth K or _, script l); these are Cyrillic and Greek
# look-alikes, digits written for letters (C0NTENT, KLA5) and underscores NFKD doesn't map to "_".
_LOOK_ALIKES = str.maketrans(
    "\u0410\u0430\u0391\u03b1"  # Cyrillic and Greek A
    "\u0421\u0441\u03f9\u03f2"  # C (Cyrillic Es, Greek lunate sigma)
    "\u0415\u0435\u0395\u03b5"  # E
    "\u041a\u043a\u039a\u03ba"  # K
    "\u039d\u03bd"  # Greek Nu
    "\u041e\u043e\u039f\u03bf"  # O
    "\u0405\u0455"  # Cyrillic Dze
    "\u0422\u0442\u03a4\u03c4"  # T
    "013457"  # digits
    "\u2017\u02cd",  # double low line, modifier low macron
    "aaaa" "cccc" "eeee" "kkkk" "nn" "oooo" "ss" "tttt" "oleast" "__")
# The marker word on folded text: case, width, accents and invisible characters don't matter, and
# neither does what stands between the two words if it isn't a letter or digit: nothing, spaces,
# dashes, underscores, a braille blank. _without_marker matches exactly this, in one pass.
_FOLDED_MARKER = re.compile(r"klas[\W_]*content")
_WORD, _TAIL = "klas", "content"
_WHOLE = len(_WORD) + len(_TAIL)  # the matcher state of a whole marker word

_BLOCK = {"p", "div", "br", "tr", "table", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "hr"}
_SKIP = {"script", "style"}


def clean(text: str | None) -> str:
    """Drop what a reader can't see: format characters (zero-width, bidi overrides, the Unicode tag
    block: category Cf), every other default-ignorable character (variation selectors, U+034F, the
    Hangul fillers) and control characters other than line breaks and tabs. Hidden text of this
    kind is a known way to slip instructions past a reader. A lone surrogate becomes U+FFFD."""
    if not text:
        return ""
    text = _IGNORABLE.sub("", text.replace("\r\n", "\n").translate(_LINE_BREAKS))
    text = _SURROGATE.sub("\ufffd", text)
    return "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch) not in ("Cf", "Cc"))


def scrub(value: object) -> object:
    """`value` with a lone surrogate in any string (keys too) replaced by U+FFFD; lists, tuples and
    dicts are walked. The last step before a tool answer is sent, for text that never went
    through clean()."""
    if isinstance(value, str):
        return _SURROGATE.sub("\ufffd", value)
    if isinstance(value, dict):
        return {scrub(k): scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    return value


def _fold(text: str) -> str:
    """How `text` reads, for finding the marker: compatibility forms and look-alikes as plain
    letters, lower case, without combining marks (Mn) or default-ignorable characters."""
    text = unicodedata.normalize("NFKD", text.translate(_LOOK_ALIKES)).casefold().translate(_LOOK_ALIKES)
    return "".join(ch for ch in _IGNORABLE.sub("", text) if unicodedata.category(ch) != "Mn")


_fold_char = functools.lru_cache(maxsize=4096)(_fold)


def _step(state: int, ch: str) -> int:
    """The marker matcher after one more folded character. State n <= 4 has just read "klas"[:n]
    (4 also with a run of non-alphanumerics after it), 4 + n "klas…" and "content"[:n]; _WHOLE is
    a whole marker word. No letter after the first is a "k", so a miss falls back to 0, or to 1 on
    a "k"."""
    if state < len(_WORD):
        if ch == _WORD[state]:
            return state + 1
    elif state == len(_WORD) and not ch.isalnum():  # [\W_] in _FOLDED_MARKER
        return state
    elif ch == _TAIL[state - len(_WORD)]:
        return state + 1
    return 1 if ch == _WORD[0] else 0


def _without_marker(body: str) -> str:
    """`body` with every span that reads as the marker word removed, however it is spelled.

    One pass, so a crafted text can't make it slow: the folded characters go on a stack with the
    matcher state after each. When a marker word completes, the characters it came from (from the
    one its "k" folded out of to this one, invisible ones between included) are dropped and the
    matcher goes back to the state before them, so the halves of a copy joined by the removal
    ("KLAS_CONTKLAS_CONTENTENT") are found as the scan goes on."""
    if not _FOLDED_MARKER.search(_fold(body)):  # the usual case; folding per character gives the same
        return body
    kept: list[int] = []  # indices in `body` that stay
    origin: list[int] = []  # per folded character on the stack: the index in `body` it came from
    states: list[int] = []  # and the matcher state after it
    for i, ch in enumerate(body):
        kept.append(i)
        for f in _fold_char(ch):
            state = _step(states[-1] if states else 0, f)
            if state != _WHOLE:
                origin.append(i)
                states.append(state)
                continue
            while states.pop() != 1:  # back to the "k" the word started with
                origin.pop()
            start = origin.pop()
            while origin and origin[-1] == start:  # that character folded to more than the "k"
                origin.pop()
                states.pop()
            while kept and kept[-1] >= start:
                kept.pop()
            break  # the rest of this character's fold goes with it
    return "".join(body[i] for i in kept)


def untrusted(text: str | None) -> str | None:
    """Text someone else wrote, cleaned and wrapped in the content marker; None when empty. A copy
    of the marker word inside is removed, also one written with fullwidth or look-alike letters,
    accents, invisible characters or anything but a letter or digit between the two words, so the
    text can't close the block early."""
    body = _without_marker(clean(text)).strip("\n")
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
