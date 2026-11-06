"""Text out of KLAS attachments (lecture slides, assignment sheets), so Claude can read them.

Supported: PDF, PPTX, DOCX, XLSX, HWPX, HWP (Hangul 5.x), Jupyter notebooks and plain text/code.
ZIP archives are listed, not unpacked. Anything else is reported as unreadable.

The files come from other people, so reading them is bounded. Zip members and HWP body streams are checked
against count, size and compression-ratio limits before anything is inflated, and inflating never goes past
the checked size. The XML is scanned with linear regexes, not an XML parser, so there is no entity expansion
and nothing external is fetched; a part with a DTD is refused outright. Any failure comes out as
UnreadableAttachment with a short Korean reason.
"""

from __future__ import annotations

import io
import json
import logging
import re
import struct
import zipfile
import zlib
from collections.abc import Iterator
from html import unescape
from pathlib import PurePath

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

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            if not reader.decrypt(""):
                raise UnreadableAttachment("암호가 걸린 PDF라 읽을 수 없습니다.")
            # The author turned off "copy text" (bit 5). Respected, like 배포용 HWP documents.
            if not (reader.user_access_permissions or 0) & UserAccessPermissions.EXTRACT:
                raise UnreadableAttachment("복사가 금지된 PDF라 내용을 읽지 않았습니다.")
        pages = [f"--- {i} 쪽 ---\n{(page.extract_text() or '').strip()}" for i, page in enumerate(reader.pages, 1)]
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


def _xlsx(z: zipfile.ZipFile) -> str:
    names = z.namelist()
    has_shared = "xl/sharedStrings.xml" in names
    sheets = _numbered(names, r"xl/worksheets/sheet\d+\.xml")
    xmls = _read_xml(z, (["xl/sharedStrings.xml"] if has_shared else []) + sheets)
    shared = _shared_strings(next(xmls)) if has_shared else []
    return "\n\n".join(f"--- 시트 {i} ---\n" + "\n".join(_sheet_rows(xml, shared)) for i, xml in enumerate(xmls, 1))


def _shared_strings(xml: str) -> list[str]:
    """One string per <si> (an empty <si/> too, so the indexes stay right), joining its <t> runs."""
    out: list[str] = []
    parts: list[str] | None = None
    in_t, pos = False, 0
    for m in re.finditer(r"<(/?)(si|t)(?=[\s/>])([^<>]*)>", xml):
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


def _sheet_rows(xml: str, shared: list[str]) -> list[str]:
    """A worksheet's rows as "a | b". A self-closing cell or row only carries formatting and is empty."""
    rows: list[str] = []
    cells: list[str] = []
    cell_attrs: str | None = None  # attributes of the open <c>
    value: list[str] | None = None  # text of its <v>, or of its inline <t> runs
    in_value, pos = False, 0
    for m in re.finditer(r"<(/?)(row|c|v|t)(?=[\s/>])([^<>]*)>", xml):
        if in_value and value is not None:
            value.append(xml[pos:m.start()])
        pos = m.end()
        closing, name, attrs = m.group(1), m.group(2), m.group(3)
        empty = attrs.endswith("/")
        if name == "row":
            if not empty:
                if closing and cells:
                    rows.append(" | ".join(cells))
                cells = []
        elif name == "c":
            if closing and cell_attrs is not None and value is not None:
                text = unescape("".join(value))
                index = text.strip()
                if (re.search(r"""(?:^|\s)t\s*=\s*["']s["']""", cell_attrs) and index.isdecimal()
                        and len(index) < 10 and int(index) < len(shared)):
                    text = shared[int(index)]
                cells.append(text)
            cell_attrs = None if closing or empty else attrs
            value, in_value = None, False
        elif cell_attrs is not None and not empty:  # <v> or <t>; a <v> wins over inline text
            in_value = not closing
            if in_value and (value is None or name == "v"):
                value = []
    return rows


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


def _hwp(data: bytes) -> str:
    import olefile

    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except OSError as e:
        raise UnreadableAttachment("한글 파일을 열지 못했습니다(손상됐거나 HWP 3.0 이전 형식).") from e
    with ole:
        header = ole.openstream("FileHeader").read()
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
            if ole.get_size(entry) > min(MAX_MEMBER_BYTES, MAX_UNPACKED_BYTES - total):
                raise UnreadableAttachment(TOO_BIG)
            raw = ole.openstream(entry).read()
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
