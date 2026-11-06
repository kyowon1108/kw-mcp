"""Text out of KLAS attachments (lecture slides, assignment sheets), so Claude can read them.

Supported: PDF, PPTX, DOCX, XLSX, HWPX, HWP (Hangul 5.x), Jupyter notebooks and plain text/code.
ZIP archives are listed, not unpacked. Anything else is reported as unreadable.

The files come from other people, so reading them is bounded. Zip members and HWP body streams are checked
against count, size and compression-ratio limits before anything is inflated, and inflating never goes past
the checked size. An HWP file's OLE header and every stream's declared size are checked against the file's
own size before olefile reads anything, and olefile's directory check runs in linear time (_ole_class).
PDF text stops at MAX_TEXT_CHARS and after PDF_SECONDS. The XML is
scanned with linear regexes, not an XML parser, so there is no entity expansion and nothing external is
fetched; a part with a DTD is refused outright. Any failure comes out as UnreadableAttachment with a short
Korean reason.
"""

from __future__ import annotations

import functools
import io
import json
import logging
import re
import struct
import time
import zipfile
import zlib
from collections.abc import Iterator
from datetime import date, timedelta
from html import unescape
from pathlib import PurePath
from typing import Any

from .text import html_to_text

log = logging.getLogger("kw_mcp.attachments")

MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
PART_CHARS = 20_000
MAX_TEXT_CHARS = 100 * PART_CHARS  # longer texts are cut here, with a note
# What one attachment may unpack to (zip members, HWP body streams).
MAX_MEMBERS = 10_000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_UNPACKED_BYTES = 128 * 1024 * 1024
# unpacked : packed, checked above RATIO_FREE_BYTES. Padding bombs reach about 1000:1; a blank 10x1000 Word
# table is about 190:1 and the same sentence 50,000 times about 340:1, so real files stay under it.
MAX_RATIO = 500
RATIO_FREE_BYTES = 1024 * 1024
# PDF text extraction gives up after this long (checked between pages): pages that share one big content
# stream each parse all of it, so a crafted file costs pages x stream (10 tiny pages took 7.7 s).
PDF_SECONDS = 60
MAX_COLUMNS = 16_384  # Excel's last column, XFD
TEXT_EXTS = {"txt", "md", "csv", "tsv", "json", "py", "c", "h", "cpp", "hpp", "java", "js", "ts", "m", "r",
             "sql", "sh", "yaml", "yml", "xml", "tex", "ini", "log"}
HTML_EXTS = {"html", "htm"}

TOO_BIG = "압축을 풀면 너무 커지는 파일이라 읽지 않았습니다."
TOO_MANY = "파일 안에 든 항목이 너무 많아 읽지 않았습니다."
DAMAGED = "파일을 읽지 못했습니다(손상됐거나 암호가 걸렸거나 지원하지 않는 형식)."


class UnreadableAttachment(ValueError):
    pass


def extract_text(name: str, data: bytes) -> tuple[str, str]:
    """(kind, text) for an attachment's bytes. Every failure is an UnreadableAttachment with a short reason."""
    try:
        kind, text = _extract(PurePath(name).suffix.lower().lstrip("."), data)
    except UnreadableAttachment:
        raise
    except MemoryError as e:
        raise UnreadableAttachment("파일이 너무 커서 읽지 못했습니다.") from e
    except Exception as e:  # corrupt or unusual files: zip/zlib/struct/pypdf errors, deep nesting, ...
        log.warning("could not read an attachment: %s", type(e).__name__)  # never the file's contents
        raise UnreadableAttachment(DAMAGED) from e
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n(너무 길어 앞의 {MAX_TEXT_CHARS:,}자까지만 읽었습니다.)"
    # Lone UTF-16 surrogates (a broken PDF font map, a "\ud83d" escape in a notebook) can't be encoded as
    # JSON: rejoin halves that belong together and turn the rest into U+FFFD.
    return kind, text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def _extract(ext: str, data: bytes) -> tuple[str, str]:
    if ext == "pdf":
        return "PDF", _pdf(data)
    if ext in ZIP_READERS:
        kind, reader = ZIP_READERS[ext]
        # Every central-directory entry starts with this signature, so this bounds the entries
        # zipfile would build before it builds them.
        if data.count(b"PK\x01\x02") > MAX_MEMBERS:
            raise UnreadableAttachment(TOO_MANY)
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise UnreadableAttachment("파일이 손상됐거나 형식이 맞지 않습니다.") from e
        with archive:
            try:
                text = reader(archive)
            except KeyError as e:
                raise UnreadableAttachment("파일 안의 구성이 예상과 달라 읽지 못했습니다.") from e
        return kind, text if ext == "zip" else _with_text(text)
    if ext == "hwp":
        return "한글(HWP)", _with_text(_hwp(data))
    if ext == "ipynb":
        return "Jupyter 노트북", _ipynb(data)
    if ext in HTML_EXTS:
        return "HTML", html_to_text(_decode(data), limit=10**9)
    if ext in TEXT_EXTS:
        return "텍스트", _decode(data)
    raise UnreadableAttachment(f"'.{ext}' 파일은 텍스트로 읽을 수 없습니다(이름만 확인 가능).")


def split_parts(text: str, part: int) -> tuple[str, int]:
    """The requested PART_CHARS-sized slice (1-based) and the number of parts."""
    total = max(1, -(-len(text) // PART_CHARS))
    part = min(max(part, 1), total)
    return text[(part - 1) * PART_CHARS: part * PART_CHARS], total


def _with_text(text: str) -> str:
    """The text, unless nothing is left once slide and sheet headers are removed (an image-only deck)."""
    if not re.sub(r"--- (?:슬라이드|시트) \d+ ---|\s", "", text):
        raise UnreadableAttachment("글자가 없는 문서입니다(이미지로만 된 슬라이드·문서일 수 있음).")
    return text


def _decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):  # UTF-16 with a BOM (Notepad "Unicode", Excel "Unicode text")
        return data.decode("utf-16", "replace")
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.constants import UserAccessPermissions
    from pypdf.errors import PyPdfError

    deadline = time.monotonic() + PDF_SECONDS
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            if not reader.decrypt(""):
                raise UnreadableAttachment("암호가 걸린 PDF라 읽을 수 없습니다.")
            # The author turned off "copy text" (bit 5). Respected, like 배포용 HWP documents.
            if not (reader.user_access_permissions or 0) & UserAccessPermissions.EXTRACT:
                raise UnreadableAttachment("복사가 금지된 PDF라 내용을 읽지 않았습니다.")
        pages: list[str] = []
        size = 0  # the length of "\n\n".join(pages)
        for i, page in enumerate(reader.pages, 1):
            if size > MAX_TEXT_CHARS:  # extract_text cuts the text there, with a note
                break
            if i > 1 and time.monotonic() > deadline:
                raise UnreadableAttachment("PDF를 읽는 데 시간이 너무 오래 걸려 중간에 멈췄습니다.")
            pages.append(f"--- {i} 쪽 ---\n{(page.extract_text() or '').strip()}")
            size += len(pages[-1]) + (2 if i > 1 else 0)
    except PyPdfError as e:
        raise UnreadableAttachment("PDF를 읽지 못했습니다(손상된 파일일 수 있음).") from e
    text = "\n\n".join(pages)
    if not re.sub(r"--- \d+ 쪽 ---|\s", "", text):
        raise UnreadableAttachment("글자가 없는 PDF입니다(스캔 이미지로 된 문서일 수 있음).")
    return text


def _unpack_limit(packed: int, total: int) -> int:
    """How far a member of `packed` bytes may unpack, when the file has unpacked `total` bytes so far."""
    return min(MAX_MEMBER_BYTES, MAX_UNPACKED_BYTES - total, max(RATIO_FREE_BYTES, packed * MAX_RATIO))


def _read_xml(z: zipfile.ZipFile, names: list[str]) -> Iterator[str]:
    """The members' XML one at a time, after checking the sizes they declare against the limits.

    read(n) never inflates past n bytes (read() would inflate up to 2 GB before trimming), and zipfile stops
    at the declared size and fails the CRC if the data runs on, so a member that lies about its size can't
    grow memory either.
    """
    infos, total = [z.getinfo(n) for n in names], 0
    for info in infos:
        if info.flag_bits & 0x1:
            raise UnreadableAttachment("암호가 걸린 파일이라 읽을 수 없습니다.")
        if info.file_size > _unpack_limit(info.compress_size, total):
            raise UnreadableAttachment(TOO_BIG)
        total += info.file_size
    for info in infos:
        with z.open(info) as f:
            xml = f.read(info.file_size).decode("utf-8", "replace")
        if "<!DOCTYPE" in xml:  # Office and HWPX parts never have one; entity bombs and XXE need one
            raise UnreadableAttachment("문서 안에 DTD 선언이 있어 읽지 않았습니다.")
        yield xml


def _paragraphs(xml: str, para: str, run: str, inline: dict[str, str] | None = None) -> list[str]:
    """Paragraph texts from Office/HWPX XML: the <run> texts inside each <para>, in one linear pass.

    A paragraph inside another (a text box, a table cell in HWPX) becomes its own line, and the outer
    paragraph's text before and after it is kept. mc:Fallback, Word's second copy of a text box, is skipped.
    `inline` maps elements inside a run (HWPX tab, line break) to text. Other tags inside a run (HWPX
    highlighter marks) are dropped, and the text around them is kept.
    """
    inline = inline or {}
    names = "|".join(re.escape(n) for n in (para, run, "mc:Fallback", *inline))
    out: list[str] = []
    open_paras: list[list[str]] = []
    in_run, skipping, pos = False, 0, 0

    def flush(parts: list[str]) -> None:
        line = "".join(parts).strip()
        if line:
            out.append(line)
        parts.clear()

    # [^<>]* stops at the next "<", so a tag that never closes costs only up to there (no quadratic scan).
    for m in re.finditer(rf"<(/?)({names})(?=[\s/>])([^<>]*)>", xml):
        if in_run and open_paras and not skipping:
            open_paras[-1].append(unescape(re.sub(r"<[^<>]*>", "", xml[pos:m.start()])))
        pos = m.end()
        closing, name, empty = m.group(1), m.group(2), m.group(3).endswith("/")
        if name == "mc:Fallback":
            if not empty:
                skipping = max(skipping - 1, 0) if closing else skipping + 1
        elif skipping:
            continue
        elif name in inline:
            if in_run and open_paras and not closing:
                open_paras[-1].append(inline[name])
        elif empty:
            continue
        elif name == run:
            in_run = not closing
        elif closing:
            if open_paras:
                flush(open_paras.pop())
        else:
            if open_paras:  # a nested paragraph: the outer one's text so far is a line of its own
                flush(open_paras[-1])
            open_paras.append([])
    return out


def _numbered(names: list[str], pattern: str) -> list[str]:
    return sorted((n for n in names if re.fullmatch(pattern, n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))


def _pptx(z: zipfile.ZipFile) -> str:
    slides = _read_xml(z, _numbered(z.namelist(), r"ppt/slides/slide\d+\.xml"))
    return "\n\n".join(f"--- 슬라이드 {i} ---\n" + "\n".join(_paragraphs(xml, "a:p", "a:t"))
                       for i, xml in enumerate(slides, 1))


def _docx(z: zipfile.ZipFile) -> str:
    return "\n".join(_paragraphs(next(_read_xml(z, ["word/document.xml"])), "w:p", "w:t"))


_BOOK_PARTS = ("xl/sharedStrings.xml", "xl/styles.xml", "xl/workbook.xml")


def _xlsx(z: zipfile.ZipFile) -> str:
    names = z.namelist()
    parts = [n for n in _BOOK_PARTS if n in names]
    xmls = _read_xml(z, parts + _numbered(names, r"xl/worksheets/sheet\d+\.xml"))
    book = {name: next(xmls) for name in parts}
    shared = _shared_strings(book.get("xl/sharedStrings.xml", ""))
    formats = _cell_formats(book.get("xl/styles.xml", ""))
    date1904 = _date1904(book.get("xl/workbook.xml", ""))
    sheets: list[str] = []
    size = 0  # the length of "\n\n".join(sheets)
    for i, xml in enumerate(xmls, 1):
        size += 2 if sheets else 0
        rows = _sheet_rows(xml, shared, formats, date1904, MAX_TEXT_CHARS - size)
        sheets.append(f"--- 시트 {i} ---\n" + "\n".join(rows))
        size += len(sheets[-1])
        if size > MAX_TEXT_CHARS:  # extract_text cuts the text there, with a note; later sheets are not read
            break
    return "\n\n".join(sheets)


def _attr(attrs: str, name: str) -> str | None:
    """The value of attribute `name` in a tag's attribute text, entities decoded."""
    m = re.search(rf"""(?:^|\s){name}\s*=\s*(["'])(.*?)\1""", attrs, re.DOTALL)
    return unescape(m.group(2)) if m else None


def _int(text: str | None) -> int | None:
    text = (text or "").strip()
    return int(text) if text.isdecimal() and len(text) < 10 else None


def _column(ref: str | None) -> int | None:
    """The 0-based column of a cell reference ("C7" is 2), or None for a missing or unusable one."""
    m = re.fullmatch(r"([A-Za-z]{1,3})\d*", ref or "")
    if not m:
        return None
    column = 0
    for letter in m.group(1).upper():
        column = column * 26 + ord(letter) - 64
    return column - 1 if column <= MAX_COLUMNS else None


def _shared_strings(xml: str) -> list[str]:
    """One string per <si> (an empty <si/> too, so the indexes stay right), joining its <t> runs."""
    out: list[str] = []
    parts: list[str] | None = None
    in_t, pos = False, 0
    for m in re.finditer(r"<(/?)(?:\w+:)?(si|t)(?=[\s/>])([^<>]*)>", xml):
        if in_t and parts is not None:
            parts.append(xml[pos:m.start()])
        pos = m.end()
        closing, name, empty = m.group(1), m.group(2), m.group(3).endswith("/")
        if name == "t":
            in_t = not closing and not empty
        elif empty:
            out.append("")
        elif closing:
            out.append(unescape("".join(parts or [])))
            parts = None
        else:
            parts = []
    return out


def _sheet_rows(xml: str, shared: list[str], formats: list[str | None], date1904: bool, budget: int) -> list[str]:
    """A worksheet's rows as "a | b", each value in the column its r="C7" names: a blank cell (left out,
    self-closing, or a formula with no saved value) is an empty field, so the values after it stay under
    their headers. A cell without r= follows the one before it, and one that would land past XFD, Excel's last
    column, is dropped. Empty cells at the end of a row, columns empty in every row on the left, and rows
    with no text are left out.

    The rows stop once their text passes `budget` characters (the count is exact, so the text is longer
    than the budget whenever rows were left out): one long shared string named by many cells, or cells
    far to the right, make much more text than the sheet itself holds.
    """
    rows: list[tuple[int, list[str]]] = []  # (column of the first value, the cells from there on)
    cells: list[str] = []  # the open row's, from its first value on
    first = row_size = 0  # the open row's first value column, and its length from there
    next_column = 0  # where a cell without r= goes
    size = 0  # length of the kept rows from their first values on, line breaks included
    starts = 0  # the sum of their first columns
    lead = MAX_COLUMNS  # the smallest first column; 3 * (starts - len(rows) * lead) is the padding before
    cell_attrs: str | None = None  # attributes of the open <c>
    value: list[str] | None = None  # text of its <v>, or of its inline <t> runs
    in_value, pos = False, 0

    def place(text: str, attrs: str) -> None:
        nonlocal first, next_column, row_size
        column = _column(_attr(attrs, "r")) if "r" in attrs else None  # most blanks are a bare <c/>
        if column is None or column < next_column:  # no r=, or out of order: the next column
            column = next_column
        if column >= MAX_COLUMNS:  # past XFD, Excel's last column: dropped, so no gap is wider than a row
            return
        next_column = column + 1
        if not text.strip():
            return  # a blank only matters as the gap it leaves
        if cells:
            gap = column - first - len(cells)
            cells.extend([""] * gap)
            row_size += 3 * (gap + 1) + len(text)  # " | " before each empty field and before the text
        else:
            first, row_size = column, len(text)
        cells.append(text)

    def end_row() -> None:
        nonlocal cells, next_column, row_size, size, starts, lead
        if cells:
            size += row_size + (1 if rows else 0)
            rows.append((first, cells))
            starts, lead = starts + first, min(lead, first)
        cells, next_column, row_size = [], 0, 0

    def over_budget() -> bool:
        open_row = row_size + (1 if rows and cells else 0)
        return size + open_row + 3 * (starts - len(rows) * lead) > budget

    for m in re.finditer(r"<(/?)(?:\w+:)?(row|c|v|t)(?=[\s/>])([^<>]*)>", xml):
        if in_value and value is not None:
            value.append(xml[pos:m.start()])
        pos = m.end()
        closing, name, attrs = m.group(1), m.group(2), m.group(3)
        empty = attrs.endswith("/")
        if name == "c":
            if next_column < MAX_COLUMNS:  # else the row is full, and the rest of its cells are skipped unread
                if closing and cell_attrs is not None:
                    place(_cell_text(cell_attrs, value, shared, formats, date1904), cell_attrs)
                    if over_budget():  # only a value or the end of a row adds text
                        break
                elif empty and not closing:
                    place("", attrs)
            cell_attrs = None if closing or empty else attrs
            value, in_value = None, False
        elif name == "row":
            if not empty:
                if closing:
                    end_row()
                    if over_budget():
                        break
                else:  # a row left open (broken XML) is dropped
                    cells, next_column, row_size = [], 0, 0
        elif cell_attrs is not None and not empty:  # <v> or <t>; a <v> wins over inline text
            in_value = not closing
            if in_value and (value is None or name == "v"):
                value = []
    end_row()  # a row cut short by the budget
    # The shared left margin can drop after earlier rows were kept, which pads every earlier row
    # again; so the budget is applied to the lines as written, not to the estimate above.
    out, total = [], 0
    for column, row in rows:
        out.append(" | " * (column - lead) + " | ".join(row))
        total += len(out[-1]) + 1
        if total > budget:
            break
    return out


def _cell_text(attrs: str, value: list[str] | None, shared: list[str], formats: list[str | None],
               date1904: bool) -> str:
    """A cell's text: its shared string, a date or time in ISO form, or the value as written."""
    if value is None:
        return ""
    text = unescape("".join(value))
    kind = _attr(attrs, "t")
    if kind == "s":
        index = _int(text)
        return shared[index] if index is not None and index < len(shared) else text
    if kind in (None, "n"):
        style = _int(_attr(attrs, "s")) or 0
        if style < len(formats) and formats[style]:
            return _excel_date(text, formats[style], date1904)
    return text


# Built-in number formats that show a date or time (ECMA-376 18.8.30). 27-36 and 50-58 are East Asian
# (yyyy"년" mm"월" dd"일", h"시" mm"분" and the like) and differ by locale, so the value decides ("auto").
_BUILTIN_DATES: dict[int, str] = {
    14: "date", 15: "date", 16: "date", 17: "date", 18: "time", 19: "time", 20: "time", 21: "time",
    22: "datetime", 45: "time", 46: "elapsed", 47: "time", **dict.fromkeys([*range(27, 37), *range(50, 59)], "auto"),
}


def _cell_formats(xml: str) -> list[str | None]:
    """For each cell style (an <xf> in <cellXfs>; a cell's s= counts into them), how its number format shows
    a date or time: "date", "time", "datetime", "elapsed" or "auto"; None for other formats."""
    codes: dict[int, str] = {}
    styles: list[int] = []
    in_codes = in_styles = False
    for m in re.finditer(r"<(/?)(?:\w+:)?(numFmts|numFmt|cellXfs|xf)(?=[\s/>])([^<>]*)>", xml):
        closing, name, attrs = m.group(1), m.group(2), m.group(3)
        if name == "numFmts":
            in_codes = not closing and not attrs.endswith("/")
        elif name == "cellXfs":
            in_styles = not closing and not attrs.endswith("/")
        elif closing:
            continue
        elif name == "numFmt" and in_codes:  # not the ones inside conditional formats (<dxf>)
            number, code = _int(_attr(attrs, "numFmtId")), _attr(attrs, "formatCode")
            if number is not None and code is not None:
                codes[number] = code
        elif name == "xf" and in_styles:
            styles.append(_int(_attr(attrs, "numFmtId")) or 0)
    kinds = {number: _format_kind(code) for number, code in codes.items()}
    return [kinds[n] if n in kinds else _BUILTIN_DATES.get(n) for n in styles]


def _format_kind(code: str) -> str | None:
    """How a custom number format shows a date or time (as for _cell_formats), or None."""
    code = re.sub(r'"[^"]*"|\\.|[_*].', "", code).split(";")[0].lower()  # literals; the positive-number part
    elapsed = re.search(r"\[(?:h+|m+|s+)\]", code) is not None
    code = re.sub(r"\[[^\]]*\]|general|e[+-]", "", code)  # colours, conditions, locales; scientific notation
    has_time = elapsed or re.search(r"[hs]|am/pm|a/p", code) is not None
    code = re.sub(r"am/pm|a/p|(h[^a-z]*)m+|m+(?=[^a-z]*s)", r"\1", code)  # an m next to h or s is minutes
    has_date = re.search(r"[ydm]", code) is not None
    if elapsed:
        return "elapsed"
    return "datetime" if has_date and has_time else "date" if has_date else "time" if has_time else None


def _date1904(xml: str) -> bool:
    """Whether the workbook counts dates from 1904 (old Mac Excel) instead of 1900."""
    m = re.search(r"<(?:\w+:)?workbookPr(?=[\s/>])([^<>]*)>", xml)
    return m is not None and (_attr(m.group(1), "date1904") or "").strip().lower() in ("1", "true")


def _excel_date(text: str, kind: str, date1904: bool) -> str:
    """An Excel serial as ISO text: "2026-11-09", "09:30" ("09:30:15" with seconds), "2026-11-09 09:30", or
    hours past 24 for an elapsed time ("27:30"). Text that is not a serial in range is kept as it was."""
    try:
        serial = float(text)
    except ValueError:
        return text
    if not 0 <= serial < 2_958_466:  # also NaN; 2958466 would be 10000-01-01
        return text
    days, seconds = divmod(round(serial * 86_400), 86_400)
    hours, rest = divmod(seconds, 3_600)
    minutes = f"{rest // 60:02}" + (f":{rest % 60:02}" if rest % 60 else "")
    if kind == "elapsed":
        return f"{days * 24 + hours}:{minutes}"
    if kind == "auto":
        kind = "time" if days == 0 else "date" if seconds == 0 else "datetime"
    clock = f"{hours:02}:{minutes}"
    if kind == "time":
        return clock
    try:
        # The 1900 system counts a 1900-02-29 that never was, so serials before it are one day off.
        day = date(1904, 1, 1) + timedelta(days) if date1904 else date(1899, 12, 30) + timedelta(days + (days < 61))
    except OverflowError:
        return text
    return day.isoformat() if kind == "date" else f"{day.isoformat()} {clock}"


_HWPX_INLINE = {"hp:tab": "\t", "hp:lineBreak": "\n", "hp:nbSpace": " ", "hp:fwSpace": " "}


def _hwpx(z: zipfile.ZipFile) -> str:
    sections = _read_xml(z, _numbered(z.namelist(), r"Contents/section\d+\.xml"))
    return "\n\n".join("\n".join(_paragraphs(xml, "hp:p", "hp:t", _HWPX_INLINE)) for xml in sections)


_UNSAFE_NAME_CHARS = re.compile("[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028-\u202e\u2066-\u2069]")


def _zip_name(info: zipfile.ZipInfo) -> str:
    """The member's name as the uploader saw it, with control and bidi characters made visible as '?'."""
    name = info.filename
    if not info.flag_bits & 0x800:  # no UTF-8 flag: zipfile assumed cp437; Korean Windows tools write cp949
        raw = info.orig_filename.encode("cp437")
        for encoding in ("utf-8", "cp949"):
            try:
                name = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
    return _UNSAFE_NAME_CHARS.sub("?", name)


def _zip_listing(z: zipfile.ZipFile) -> str:
    files = [f"{_zip_name(i)} ({round(i.file_size / 1024)}KB)" for i in z.infolist() if not i.is_dir()]
    return "압축 파일 안의 파일 목록(내용은 풀지 않음):\n" + "\n".join(files)


def _ipynb(data: bytes) -> str:
    try:
        nb = json.loads(_decode(data))
    except (ValueError, RecursionError) as e:
        raise UnreadableAttachment("노트북 파일 형식이 올바르지 않습니다.") from e
    if not isinstance(nb, dict) or not isinstance(nb.get("cells") or [], list):
        raise UnreadableAttachment("노트북 파일 형식이 올바르지 않습니다.")
    cells = []
    for i, cell in enumerate(nb.get("cells") or [], 1):
        if not isinstance(cell, dict):
            continue
        source = cell.get("source") or ""
        source = "".join(map(str, source)) if isinstance(source, list) else str(source)
        cells.append(f"--- 셀 {i} ({cell.get('cell_type', '?')}) ---\n{source.strip()}")
    return "\n\n".join(cells)


ZIP_READERS = {"pptx": ("PowerPoint", _pptx), "docx": ("Word", _docx), "xlsx": ("Excel", _xlsx),
               "hwpx": ("한글(HWPX)", _hwpx), "zip": ("ZIP", _zip_listing)}


# HWP 5.x: an OLE file whose BodyText/SectionN streams are (usually deflated) records; paragraph
# text is record tag 67 in UTF-16LE with control characters mixed in.
_HWPTAG_PARA_TEXT = 67
# Inline (4-9, 19, 20) and extended controls take 8 UTF-16 units: the code, 6 units of data, the code again.
# The other codes below 32 take one unit.
_WIDE_CONTROLS = frozenset(range(1, 10)) | {11, 12} | frozenset(range(14, 24))


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _check_ole_header(data: bytes) -> None:
    """Refuse an OLE header whose counts can't be right for a file this size, before olefile acts on them.

    olefile reads as many sectors as a count or a declared size asks for, following the FAT even where it
    loops back on itself, and adds FAT sectors to its table one copy at a time (quadratic in their number),
    so a 2 KB file could make it read gigabytes. One FAT sector covers sector_size / 4 sectors, and twice
    the FAT the file needs is allowed. The MiniFAT's sectors are part of the file.
    """
    if len(data) < 512 or not data.startswith(_OLE_MAGIC):
        return  # olefile turns it down itself
    sector_shift, mini_shift = struct.unpack_from("<HH", data, 30)
    fat_sectors = struct.unpack_from("<I", data, 44)[0]
    minifat_sectors = struct.unpack_from("<I", data, 64)[0]
    if sector_shift not in (9, 12) or mini_shift != 6:  # 512- or 4096-byte sectors, 64-byte mini sectors
        raise UnreadableAttachment(DAMAGED)
    sectors = (len(data) - 1) >> sector_shift  # after the header
    if minifat_sectors > sectors or fat_sectors > 2 * ((sectors >> (sector_shift - 2)) + 1):
        raise UnreadableAttachment(DAMAGED)


def _ole_read(ole: Any, entry: str | list[str], file_size: int, limit: int) -> bytes:
    """A stream's bytes, after checking the size it declares: olefile reads that many bytes' worth of
    sectors, following a FAT that loops back on itself."""
    size = ole.get_size(entry)
    if size > file_size:  # no stream holds more than the whole file
        raise UnreadableAttachment(DAMAGED)
    if size > limit:
        raise UnreadableAttachment(TOO_BIG)
    return ole.openstream(entry).read()


@functools.cache
def _ole_class(base: Any) -> Any:
    """olefile.OleFileIO (`base`) with its check that no two streams start at the same sector done in sets.

    olefile 0.47 searches a list for each stream it meets in the directory, so opening is quadratic in the
    stream count: 40,000 tiny streams (a 5 MB file) took 2.8 s, and a file at the download cap would take
    minutes, all inside the constructor, before _hwp can count the streams.
    """
    import olefile

    not_streams = (olefile.DIFSECT, olefile.FATSECT, olefile.ENDOFCHAIN, olefile.FREESECT)

    class OleFile(base):  # type: ignore[misc, valid-type]
        def open(self, *args: Any, **kwargs: Any) -> Any:
            self._seen = {False: set(), True: set()}  # first sectors in the FAT, in the MiniFAT
            return super().open(*args, **kwargs)

        def _check_duplicate_stream(self, first_sect: int, minifat: bool = False) -> None:
            if not minifat and first_sect in not_streams:  # as olefile: these are not a stream's first sector
                return
            seen = self._seen[bool(minifat)]
            if first_sect in seen:
                self._raise_defect(olefile.DEFECT_INCORRECT, "Stream referenced twice")
            seen.add(first_sect)

    return OleFile


def _hwp(data: bytes) -> str:
    import olefile

    _check_ole_header(data)
    opener = olefile.OleFileIO
    if isinstance(opener, type):  # not a test's stand-in function
        opener = _ole_class(opener)
    try:
        ole = opener(io.BytesIO(data))
    except OSError as e:
        raise UnreadableAttachment("한글 파일을 열지 못했습니다(손상됐거나 HWP 3.0 이전 형식).") from e
    with ole:
        # Streams under 4 KB (FileHeader among them) live in the mini stream, which olefile reads whole,
        # at the size the root entry declares, before the first of them.
        if ole.root.size > len(data):
            raise UnreadableAttachment(DAMAGED)
        header = _ole_read(ole, "FileHeader", len(data), MAX_MEMBER_BYTES)
        flags = struct.unpack("<I", header[36:40])[0]
        if flags & 0x2 or flags & 0x4:
            raise UnreadableAttachment("암호가 걸렸거나 배포용으로 저장된 한글 문서라 읽을 수 없습니다.")
        compressed = bool(flags & 0x1)
        streams = ole.listdir()
        if len(streams) > MAX_MEMBERS:
            raise UnreadableAttachment(TOO_MANY)
        sections = sorted((e for e in streams if len(e) == 2 and e[0] == "BodyText"),
                          key=lambda e: int(re.sub(r"\D", "", e[1]) or 0))
        paragraphs, total = [], 0  # total counts stored and inflated bytes alike
        for entry in sections:
            raw = _ole_read(ole, entry, len(data), min(MAX_MEMBER_BYTES, MAX_UNPACKED_BYTES - total))
            total += len(raw)
            if compressed:
                raw = _inflate(raw, _unpack_limit(len(raw), total))
                total += len(raw)
            paragraphs += _hwp_paragraphs(raw)
    return "\n".join(p for p in paragraphs if p.strip())


def _inflate(raw: bytes, limit: int) -> bytes:
    """Raw deflate data, refused as soon as it would grow past `limit` bytes (it is never inflated further)."""
    inflater = zlib.decompressobj(-15)
    out = inflater.decompress(raw, max(limit, 0) + 1)
    if len(out) > limit:
        raise UnreadableAttachment(TOO_BIG)
    if not inflater.eof:
        raise UnreadableAttachment(DAMAGED)
    return out


def _hwp_paragraphs(raw: bytes) -> list[str]:
    out, pos = [], 0
    while pos + 4 <= len(raw):
        head = struct.unpack("<I", raw[pos:pos + 4])[0]
        pos += 4
        tag, size = head & 0x3FF, (head >> 20) & 0xFFF
        if size == 0xFFF:
            size = struct.unpack("<I", raw[pos:pos + 4])[0]
            pos += 4
        body = raw[pos:pos + size]
        pos += size
        if tag == _HWPTAG_PARA_TEXT:
            out.append(_hwp_text(body))
    return out


def _hwp_text(body: bytes) -> str:
    units = struct.unpack(f"<{len(body) // 2}H", body[:len(body) // 2 * 2])
    kept, i = [], 0
    while i < len(units):
        u = units[i]
        if u >= 32:
            kept.append(u)
        elif u in _WIDE_CONTROLS:
            if u == 9:
                kept.append(9)  # tab
            i += 8
            continue
        elif u in (10, 13):
            kept.append(10)
        elif u in (30, 31):  # 묶음 빈칸, 고정폭 빈칸
            kept.append(32)
        i += 1
    # Decode once, so surrogate pairs (emoji, rare hanja) join up and stray halves become U+FFFD.
    return struct.pack(f"<{len(kept)}H", *kept).decode("utf-16-le", "replace").strip()
