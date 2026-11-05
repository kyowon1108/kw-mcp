"""Text out of KLAS attachments (lecture slides, assignment sheets), so Claude can read them.

Supported: PDF, PPTX, DOCX, XLSX, HWPX, HWP (Hangul 5.x), Jupyter notebooks and plain text/code.
ZIP archives are listed, not unpacked. Anything else is reported as unreadable.
"""

from __future__ import annotations

import io
import json
import re
import struct
import zipfile
import zlib
from html import unescape
from pathlib import PurePath

from .text import html_to_text

MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024
PART_CHARS = 20_000
TEXT_EXTS = {"txt", "md", "csv", "tsv", "json", "py", "c", "h", "cpp", "hpp", "java", "js", "ts", "m", "r",
             "sql", "sh", "yaml", "yml", "xml", "tex", "ini", "log"}
HTML_EXTS = {"html", "htm"}


class UnreadableAttachment(ValueError):
    pass


def extract_text(name: str, data: bytes) -> tuple[str, str]:
    """(kind, text) for an attachment's bytes."""
    ext = PurePath(name).suffix.lower().lstrip(".")
    if ext == "pdf":
        return "PDF", _pdf(data)
    if ext in ZIP_READERS:
        kind, reader = ZIP_READERS[ext]
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise UnreadableAttachment("파일이 손상됐거나 형식이 맞지 않습니다.") from e
        with archive:
            try:
                return kind, reader(archive)
            except KeyError as e:
                raise UnreadableAttachment("파일 안의 구성이 예상과 달라 읽지 못했습니다.") from e
    if ext == "hwp":
        return "한글(HWP)", _hwp(data)
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


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _pdf(data: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise UnreadableAttachment("암호가 걸린 PDF라 읽을 수 없습니다.")
        pages = [f"--- {i} 쪽 ---\n{(page.extract_text() or '').strip()}" for i, page in enumerate(reader.pages, 1)]
    except PdfReadError as e:
        raise UnreadableAttachment("PDF를 읽지 못했습니다(손상된 파일일 수 있음).") from e
    text = "\n\n".join(pages)
    if not re.sub(r"--- \d+ 쪽 ---|\s", "", text):
        raise UnreadableAttachment("글자가 없는 PDF입니다(스캔 이미지로 된 문서일 수 있음).")
    return text


def _xml_text(xml: str, paragraph: str, run: str) -> list[str]:
    """Paragraph texts from Office/HWPX XML: join <run> texts inside each <paragraph>."""
    out = []
    for para in re.findall(rf"<{paragraph}\b[^>]*>(.*?)</{paragraph}>", xml, flags=re.S):
        line = "".join(unescape(t) for t in re.findall(rf"<{run}\b[^>]*>([^<]*)</{run}>", para))
        if line.strip():
            out.append(line.strip())
    return out


def _numbered(names: list[str], pattern: str) -> list[str]:
    return sorted((n for n in names if re.fullmatch(pattern, n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))


def _pptx(z: zipfile.ZipFile) -> str:
    slides = []
    for i, name in enumerate(_numbered(z.namelist(), r"ppt/slides/slide\d+\.xml"), 1):
        lines = _xml_text(z.read(name).decode("utf-8", "replace"), "a:p", "a:t")
        slides.append(f"--- 슬라이드 {i} ---\n" + "\n".join(lines))
    return "\n\n".join(slides)


def _docx(z: zipfile.ZipFile) -> str:
    return "\n".join(_xml_text(z.read("word/document.xml").decode("utf-8", "replace"), "w:p", "w:t"))


def _xlsx(z: zipfile.ZipFile) -> str:
    names = z.namelist()
    shared = []
    if "xl/sharedStrings.xml" in names:
        xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
        shared = ["".join(unescape(t) for t in re.findall(r"<t\b[^>]*>([^<]*)</t>", si))
                  for si in re.findall(r"<si>(.*?)</si>", xml, flags=re.S)]
    sheets = []
    for i, name in enumerate(_numbered(names, r"xl/worksheets/sheet\d+\.xml"), 1):
        rows = []
        for row in re.findall(r"<row\b[^>]*>(.*?)</row>", z.read(name).decode("utf-8", "replace"), flags=re.S):
            cells = []
            for attrs, body in re.findall(r"<c\b([^>]*)>(.*?)</c>", row, flags=re.S):
                value = re.search(r"<v>([^<]*)</v>", body) or re.search(r"<t\b[^>]*>([^<]*)</t>", body)
                if not value:
                    continue
                v = unescape(value.group(1))
                cells.append(shared[int(v)] if 't="s"' in attrs and v.isdigit() and int(v) < len(shared) else v)
            if cells:
                rows.append(" | ".join(cells))
        sheets.append(f"--- 시트 {i} ---\n" + "\n".join(rows))
    return "\n\n".join(sheets)


def _hwpx(z: zipfile.ZipFile) -> str:
    parts = []
    for name in _numbered(z.namelist(), r"Contents/section\d+\.xml"):
        parts.append("\n".join(_xml_text(z.read(name).decode("utf-8", "replace"), "hp:p", "hp:t")))
    return "\n\n".join(parts)


def _zip_listing(z: zipfile.ZipFile) -> str:
    files = [f"{i.filename} ({round(i.file_size / 1024)}KB)" for i in z.infolist() if not i.is_dir()]
    return "압축 파일 안의 파일 목록(내용은 풀지 않음):\n" + "\n".join(files)


def _ipynb(data: bytes) -> str:
    try:
        nb = json.loads(_decode(data))
    except ValueError as e:
        raise UnreadableAttachment("노트북 파일 형식이 올바르지 않습니다.") from e
    cells = []
    for i, cell in enumerate(nb.get("cells") or [], 1):
        source = cell.get("source") or ""
        source = "".join(source) if isinstance(source, list) else str(source)
        cells.append(f"--- 셀 {i} ({cell.get('cell_type', '?')}) ---\n{source.strip()}")
    return "\n\n".join(cells)


ZIP_READERS = {"pptx": ("PowerPoint", _pptx), "docx": ("Word", _docx), "xlsx": ("Excel", _xlsx),
               "hwpx": ("한글(HWPX)", _hwpx), "zip": ("ZIP", _zip_listing)}


# HWP 5.x: an OLE file whose BodyText/SectionN streams are (usually deflated) records; paragraph
# text is record tag 67 in UTF-16LE with inline control characters.
_HWPTAG_PARA_TEXT = 67
_EXTENDED_CONTROLS = {1, 2, 3, 11, 12, 14, 15, 16, 17, 18, 21, 22, 23}  # take 8 UTF-16 units


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
        sections = sorted((e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText"),
                          key=lambda e: int(re.sub(r"\D", "", e[1]) or 0))
        paragraphs = []
        for entry in sections:
            raw = ole.openstream(entry).read()
            if compressed:
                raw = zlib.decompress(raw, -15)
            paragraphs += _hwp_paragraphs(raw)
    return "\n".join(p for p in paragraphs if p.strip())


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
    chars, i = [], 0
    while i < len(units):
        u = units[i]
        if u < 32:
            if u in _EXTENDED_CONTROLS:
                i += 8
                continue
            if u == 9:
                chars.append("\t")
            elif u in (10, 13):
                chars.append("\n")
            i += 1
            continue
        chars.append(chr(u))
        i += 1
    return "".join(chars).strip()
