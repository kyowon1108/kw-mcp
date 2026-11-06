import io
import json
import re
import struct
import tracemalloc
import zipfile
import zlib
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Self

import olefile
import pydantic_core
import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions

from kw_mcp import attachments
from kw_mcp.attachments import UnreadableAttachment, extract_text, split_parts
from kw_mcp.klas import KlasClient, KlasError
from kw_mcp.service import FILE_LIST, KST, TASK_VIEW, KlasService
from tests.test_items import ItemClient


def make_pdf(text: str) -> bytes:
    """A one-page PDF with a correct xref table, built by hand (no PDF writer needed)."""
    stream = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [b"<</Type/Catalog/Pages 2 0 R>>", b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
               b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
               b"<</Length %d>>stream\n" % len(stream) + stream + b"\nendstream",
               b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>"]
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + body + b"endobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer<</Size %d/Root 1 0 R>>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(out)


MINI_PDF = make_pdf("Naive Bayes week 10")


def zipped(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def test_pdf_pages():
    kind, text = extract_text("w10.pdf", MINI_PDF)
    assert kind == "PDF" and text.startswith("--- 1 쪽 ---") and "Naive Bayes week 10" in text


def test_office_and_hwpx_text():
    slide = '<p:sld><a:p><a:r><a:t>로지스틱</a:t></a:r><a:r><a:t> 회귀</a:t></a:r></a:p><a:p><a:t>&lt;식&gt;</a:t></a:p></p:sld>'
    kind, text = extract_text("w.pptx", zipped({"ppt/slides/slide2.xml": slide, "ppt/slides/slide10.xml": slide,
                                                "ppt/slides/slide1.xml": "<a:p><a:t>표지</a:t></a:p>"}))
    assert kind == "PowerPoint"
    assert text.split("\n\n")[0] == "--- 슬라이드 1 ---\n표지"  # numeric order, not slide1, slide10, slide2
    assert "로지스틱 회귀\n<식>" in text
    _, doc = extract_text("a.docx", zipped({"word/document.xml": "<w:p><w:r><w:t>과제</w:t></w:r><w:r><w:t>안내</w:t></w:r></w:p>"}))
    assert doc == "과제안내"
    _, hwpx = extract_text("a.hwpx", zipped({"Contents/section0.xml": "<hp:p><hp:run><hp:t>제출 형식</hp:t></hp:run></hp:p>"}))
    assert hwpx == "제출 형식"
    sheet = '<row><c r="A1" t="s"><v>0</v></c><c r="B1"><v>95</v></c></row>'
    _, xlsx = extract_text("s.xlsx", zipped({"xl/sharedStrings.xml": "<sst><si><t>점수</t></si></sst>",
                                             "xl/worksheets/sheet1.xml": f"<worksheet><sheetData>{sheet}</sheetData></worksheet>"}))
    assert xlsx == "--- 시트 1 ---\n점수 | 95"


def test_hwp_paragraph_records():
    def record(tag: int, body: bytes) -> bytes:
        return struct.pack("<I", tag | (len(body) << 20)) + body
    text = "중간고사 범위".encode("utf-16-le")
    control = struct.pack("<8H", 11, 0, 0, 0, 0, 0, 0, 11)  # an extended inline control (8 units), skipped
    raw = record(66, b"\x00" * 8) + record(67, control + text + struct.pack("<H", 13)) + record(67, "2장".encode("utf-16-le"))
    assert attachments._hwp_paragraphs(raw) == ["중간고사 범위", "2장"]


def test_notebook_text_zip_and_unsupported():
    nb = {"cells": [{"cell_type": "markdown", "source": ["# 실습\n"]}, {"cell_type": "code", "source": "print(1)"}]}
    _, text = extract_text("lab.ipynb", json.dumps(nb).encode())
    assert text == "--- 셀 1 (markdown) ---\n# 실습\n\n--- 셀 2 (code) ---\nprint(1)"
    assert extract_text("a.txt", "가나다".encode("cp949")) == ("텍스트", "가나다")
    kind, listing = extract_text("src.zip", zipped({"src/main.py": "x" * 2048}))
    assert kind == "ZIP" and "src/main.py (2KB)" in listing
    with pytest.raises(UnreadableAttachment):
        extract_text("tool.dmg", b"\x00")
    with pytest.raises(UnreadableAttachment):
        extract_text("broken.pptx", b"not a zip")


def test_split_parts():
    text = "가" * (attachments.PART_CHARS * 2 + 5)
    first, total = split_parts(text, 1)
    assert total == 3 and len(first) == attachments.PART_CHARS
    assert split_parts(text, 9) == ("가" * 5, 3)  # past the end -> last part


# --- crafted and unusual files -------------------------------------------------------------------

def patch_central(data: bytes, name: str, **fields: int) -> bytes:
    """Rewrite fields (flags, crc, file_size) of one member's central-directory entry."""
    layout = {"flags": (8, "<H"), "crc": (16, "<I"), "file_size": (24, "<I")}
    out, raw_name = bytearray(data), name.encode()
    pos = next(m.start() for m in re.finditer(b"PK\x01\x02", data) if data[m.start() + 46:].startswith(raw_name))
    for field, value in fields.items():
        offset, fmt = layout[field]
        struct.pack_into(fmt, out, pos + offset, value)
    return bytes(out)


def padded_zip(name: str, megabytes: int) -> bytes:
    """A zip whose one member is `megabytes` MB of spaces, deflated about 1000:1 (built without holding it)."""
    buf, chunk = io.BytesIO(), b" " * (1 << 20)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, z.open(name, "w") as f:
        for _ in range(megabytes):
            f.write(chunk)
    return buf.getvalue()


def test_zip_bomb_is_refused_before_it_is_inflated():
    bomb = padded_zip("word/document.xml", 50)
    assert len(bomb) < 100_000
    with pytest.raises(UnreadableAttachment, match="압축을 풀면 너무 커지는"):
        extract_text("bomb.docx", bomb)
    # The same member claiming to be 1 KB: reading stops at the declared size, the CRC then fails.
    liar = patch_central(bomb, "word/document.xml", file_size=1000)
    tracemalloc.start()
    try:
        with pytest.raises(UnreadableAttachment, match="파일을 읽지 못했습니다"):
            extract_text("liar.docx", liar)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 8 * 1024 * 1024  # zipfile's read() would have inflated all 50 MB first


def test_total_size_and_member_count_caps(monkeypatch):
    sheet = "<worksheet><sheetData><row><c><v>1</v></c></row></sheetData></worksheet>"
    book = zipped({"xl/sharedStrings.xml": "<sst/>", "xl/worksheets/sheet1.xml": sheet, "xl/worksheets/sheet2.xml": sheet})
    assert extract_text("a.xlsx", book)[1].startswith("--- 시트 1 ---\n1")
    monkeypatch.setattr(attachments, "MAX_UNPACKED_BYTES", len(sheet) * 2)  # the shared strings tip it over
    with pytest.raises(UnreadableAttachment, match="압축을 풀면 너무 커지는"):
        extract_text("a.xlsx", book)
    monkeypatch.setattr(attachments, "MAX_UNPACKED_BYTES", 10**9)
    monkeypatch.setattr(attachments, "MAX_MEMBER_BYTES", len(sheet) - 1)
    with pytest.raises(UnreadableAttachment, match="압축을 풀면 너무 커지는"):
        extract_text("a.xlsx", book)
    monkeypatch.setattr(attachments, "MAX_MEMBERS", 2)
    for name in ("a.xlsx", "a.zip"):
        with pytest.raises(UnreadableAttachment, match="항목이 너무 많아"):
            extract_text(name, book)


@pytest.mark.parametrize(("name", "member", "body"), [
    ("a.docx", "word/document.xml", "<w:document><w:body><w:p><w:r><w:t>&l9;</w:t></w:r></w:p></w:body></w:document>"),
    ("a.pptx", "ppt/slides/slide1.xml", "<p:sld><a:p><a:r><a:t>&l9;</a:t></a:r></a:p></p:sld>"),
    ("a.xlsx", "xl/sharedStrings.xml", "<sst><si><t>&l9;</t></si></sst>"),
    ("a.hwpx", "Contents/section0.xml", "<hs:sec><hp:p><hp:run><hp:t>&l9;</hp:t></hp:run></hp:p></hs:sec>"),
])
def test_xml_entity_bombs_and_external_entities_are_refused(name, member, body):
    laughs = ['<!ENTITY l0 "ha">'] + [f'<!ENTITY l{i} "{f"&l{i - 1};" * 10}">' for i in range(1, 10)]  # 10^9
    files = {member: f'<?xml version="1.0"?><!DOCTYPE doc [{"".join(laughs)}]>{body}'}
    if name == "a.xlsx":
        files["xl/worksheets/sheet1.xml"] = '<worksheet><sheetData><row><c t="s"><v>0</v></c></row></sheetData></worksheet>'
    with pytest.raises(UnreadableAttachment, match="DTD"):
        extract_text(name, zipped(files))
    xxe = '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><w:p><w:r><w:t>&x;</w:t></w:r></w:p>'
    with pytest.raises(UnreadableAttachment, match="DTD"):
        extract_text("x.docx", zipped({"word/document.xml": xxe}))


def utf16(*parts: str | list[int]) -> bytes:
    """HWP paragraph text: strings and runs of raw UTF-16 units (control characters) in order."""
    return b"".join(p.encode("utf-16-le") if isinstance(p, str) else struct.pack(f"<{len(p)}H", *p) for p in parts)


def hwp_record(tag: int, body: bytes) -> bytes:
    return struct.pack("<I", tag | (len(body) << 20)) + body


def raw_deflate(data: bytes) -> bytes:
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    return packer.compress(data) + packer.flush()


class FakeOle:
    """Stands in for olefile.OleFileIO over a dict of streams, since no HWP writer exists to build fixtures."""

    def __init__(self, streams: dict[tuple[str, ...], bytes]):
        self.streams = streams
        self.root = SimpleNamespace(size=0)  # the root entry; its size is the mini stream's

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def listdir(self) -> list[list[str]]:
        return [list(k) for k in self.streams]

    def openstream(self, entry: str | list[str]) -> io.BytesIO:
        return io.BytesIO(self.streams[self._key(entry)])

    def get_size(self, entry: str | list[str]) -> int:
        return len(self.streams[self._key(entry)])

    @staticmethod
    def _key(entry: str | list[str]) -> tuple[str, ...]:
        return tuple(entry.split("/")) if isinstance(entry, str) else tuple(entry)


# What extract_text gets as the file with a FakeOle in place: at least as long as any fake stream, as a real
# file is (a stream declaring more than the file holds is refused).
HWP_BYTES = bytes(1 << 20)


def fake_hwp(monkeypatch, *sections: bytes, compressed: bool = True) -> None:
    header = b"HWP Document File".ljust(36, b"\0") + struct.pack("<I", int(compressed)) + bytes(216)
    streams: dict[tuple[str, ...], bytes] = {("FileHeader",): header}
    streams |= {("BodyText", f"Section{i}"): raw_deflate(s) if compressed else s for i, s in enumerate(sections)}
    monkeypatch.setattr(olefile, "OleFileIO", lambda f: FakeOle(streams))


def test_hwp_emoji_and_rare_hanja_come_out_whole_and_serialise(monkeypatch):
    fake_hwp(monkeypatch, hwp_record(67, utf16("📌 완료 😀 𠮷", [13])))
    kind, text = extract_text("과제.hwp", HWP_BYTES)
    assert (kind, text) == ("한글(HWP)", "📌 완료 😀 𠮷")
    json.dumps({"text": text}, ensure_ascii=False).encode()  # the PC agent's path
    pydantic_core.to_json({"text": text})  # the MCP server's path
    stray = attachments._hwp_text(utf16("a", [0xD83D], "b"))  # a lone half becomes U+FFFD
    assert stray == "a�b"


def test_hwp_inline_controls_leave_no_fake_characters():
    tab = [9, 0x0B54, 0, 0x0128, 0, 0, 0, 9]
    assert attachments._hwp_text(utf16("1.", tab, "문제를 푸시오")) == "1.\t문제를 푸시오"
    field_start, field_end = [3, 0x6C68, 0x256B, 0, 0, 0, 0, 3], [4, 0x6C68, 0x256B, 0, 0, 0, 0, 4]
    assert attachments._hwp_text(utf16("자료: ", field_start, "링크", field_end, "참고")) == "자료: 링크참고"
    assert attachments._hwp_text(utf16("제출", [30], "기한", [31], "11/20")) == "제출 기한 11/20"


def test_hwp_streams_are_capped_and_broken_ones_unreadable(monkeypatch):
    text = hwp_record(67, utf16("본문"))
    fake_hwp(monkeypatch, text, bytes(20 << 20))  # second section: 20 MB of zeros, about 1000:1
    with pytest.raises(UnreadableAttachment, match="압축을 풀면 너무 커지는"):
        extract_text("a.hwp", HWP_BYTES)
    fake_hwp(monkeypatch, text, text)
    assert extract_text("a.hwp", HWP_BYTES)[1] == "본문\n본문"
    monkeypatch.setattr(attachments, "MAX_UNPACKED_BYTES", len(raw_deflate(text)) * 2 + len(text) + 1)
    with pytest.raises(UnreadableAttachment, match="압축을 풀면 너무 커지는"):
        extract_text("a.hwp", HWP_BYTES)  # the second section's inflated bytes go past the total
    monkeypatch.undo()
    streams = {("FileHeader",): bytes(36) + struct.pack("<I", 1), ("BodyText", "Section0"): raw_deflate(text)[:-3]}
    monkeypatch.setattr(olefile, "OleFileIO", lambda f: FakeOle(streams))
    with pytest.raises(UnreadableAttachment, match="파일을 읽지 못했습니다"):
        extract_text("a.hwp", HWP_BYTES)  # truncated deflate stream
    fake_hwp(monkeypatch, text + struct.pack("<I", 67 | (0xFFF << 20)) + b"\x01")
    with pytest.raises(UnreadableAttachment, match="파일을 읽지 못했습니다"):
        extract_text("a.hwp", HWP_BYTES)  # a record whose extended size is cut off (struct.error)
    fake_hwp(monkeypatch, hwp_record(66, bytes(8)))
    with pytest.raises(UnreadableAttachment, match="글자가 없는 문서"):
        extract_text("a.hwp", HWP_BYTES)


def test_xlsx_empty_formatted_cells_and_rows_swallow_nothing():
    strings = "<sst><si><t>이름</t></si><si><t>점수</t></si><si><t>김광운</t></si><si/><si><r><t>비</t></r><r><t>고</t></r></si></sst>"
    sheet = ('<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" s="3"/><c r="C1" t="s"><v>1</v></c><c r="D1" s="3"/></row>'
             '<row r="2" s="1" customFormat="1"/>'
             '<row r="3"><c r="A3" t="s"><v>2</v></c><c r="B3" s="2"/><c r="C3"><v>95</v></c></row>'
             '<row r="4"><c r="A4" t="s"><v>4</v></c><c r="C4" t="inlineStr"><is><t>메모</t></is></c></row>')
    _, text = extract_text("s.xlsx", zipped({"xl/sharedStrings.xml": strings,
                                             "xl/worksheets/sheet1.xml": f"<worksheet><sheetData>{sheet}</sheetData></worksheet>"}))
    # A styled blank (B1, B3) or a left-out cell (B4) keeps its column; <si/> keeps index 4 on "비고".
    assert text == "--- 시트 1 ---\n이름 |  | 점수\n김광운 |  | 95\n비고 |  | 메모"


def test_hwpx_tabs_highlights_breaks_and_tables():
    section = ('<hs:sec><hp:p><hp:run><hp:t>1.<hp:tab width="4000" leader="0" type="1"/>다음 문제를 푸시오</hp:t></hp:run></hp:p>'
               '<hp:p><hp:run><hp:t>제출: <hp:markpenBegin color="#FFFF00"/>11월 20일<hp:markpenEnd/></hp:t></hp:run></hp:p>'
               '<hp:p><hp:run><hp:t>첫줄<hp:lineBreak/>둘째줄</hp:t><hp:t/><hp:t>끝</hp:t></hp:run></hp:p>'
               '<hp:p><hp:run><hp:t>표 앞</hp:t></hp:run><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList><hp:p><hp:run>'
               '<hp:t>항목</hp:t></hp:run></hp:p></hp:subList></hp:tc></hp:tr></hp:tbl></hp:run><hp:run><hp:t>표 뒤</hp:t>'
               '</hp:run></hp:p></hs:sec>')
    _, text = extract_text("a.hwpx", zipped({"Contents/section0.xml": section}))
    assert text == "1.\t다음 문제를 푸시오\n제출: 11월 20일\n첫줄\n둘째줄끝\n표 앞\n항목\n표 뒤"


def test_docx_text_box_keeps_the_rest_of_the_paragraph_once():
    box = '<w:txbxContent><w:p><w:r><w:t>상자1</w:t></w:r></w:p><w:p><w:r><w:t>상자2</w:t></w:r></w:p></w:txbxContent>'
    doc = ('<w:document><w:body><w:p><w:r><w:t xml:space="preserve">앞 </w:t></w:r><w:r><mc:AlternateContent>'
           f'<mc:Choice Requires="wps"><w:drawing>{box}</w:drawing></mc:Choice>'
           f'<mc:Fallback><w:pict><v:textbox>{box}</v:textbox></w:pict></mc:Fallback></mc:AlternateContent></w:r>'
           '<w:r><w:t>뒤 문장</w:t></w:r></w:p><w:p><w:r><w:t>다음 문단</w:t></w:r></w:p></w:body></w:document>')
    assert extract_text("a.docx", zipped({"word/document.xml": doc}))[1] == "앞\n상자1\n상자2\n뒤 문장\n다음 문단"


def test_documents_without_text_and_utf16_text():
    for name, files in [("pic.pptx", {"ppt/slides/slide1.xml": "<p:sld><p:pic/></p:sld>"}),
                        ("blank.docx", {"word/document.xml": "<w:document><w:body><w:p/></w:body></w:document>"}),
                        ("blank.hwpx", {"Contents/section0.xml": "<hs:sec><hp:p><hp:run/></hp:p></hs:sec>"})]:
        with pytest.raises(UnreadableAttachment, match="글자가 없는 문서"):
            extract_text(name, zipped(files))
    assert extract_text("a.txt", "UTF16 메모장\n둘째 줄".encode("utf-16")) == ("텍스트", "UTF16 메모장\n둘째 줄")
    assert extract_text("a.csv", "\ufeff이름,점수".encode("utf-16-be"))[1] == "이름,점수"


ALL_PERMISSIONS = UserAccessPermissions.all()


def encrypted_pdf(user: str = "", permissions: UserAccessPermissions = ALL_PERMISSIONS, algorithm: str = "AES-128") -> bytes:
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(MINI_PDF)))
    writer.encrypt(user_password=user, owner_password="prof-only", algorithm=algorithm, permissions_flag=permissions)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.parametrize("algorithm", ["RC4-128", "AES-128", "AES-256"])
def test_encrypted_pdf_copy_protection_is_respected(algorithm):
    no_copy = UserAccessPermissions.PRINT | UserAccessPermissions.EXTRACT_TEXT_AND_GRAPHICS
    with pytest.raises(UnreadableAttachment, match="복사가 금지된 PDF라 내용을 읽지 않았습니다"):
        extract_text("강의자료.pdf", encrypted_pdf(permissions=no_copy, algorithm=algorithm))
    with pytest.raises(UnreadableAttachment, match="암호가 걸린 PDF"):
        extract_text("강의자료.pdf", encrypted_pdf(user="secret", algorithm=algorithm))
    # Encrypted only to set an owner password, copying allowed: still read.
    assert "Naive Bayes week 10" in extract_text("강의자료.pdf", encrypted_pdf(algorithm=algorithm))[1]


def test_every_parser_failure_is_unreadable_with_a_korean_reason(monkeypatch):
    doc = zipped({"word/document.xml": "<w:p><w:r><w:t>과제</w:t></w:r></w:p>"})
    with pytest.raises(UnreadableAttachment, match="파일을 읽지 못했습니다"):
        extract_text("crc.docx", patch_central(doc, "word/document.xml", crc=0))  # BadZipFile at the CRC
    with pytest.raises(UnreadableAttachment, match="암호가 걸린 파일"):
        extract_text("locked.docx", patch_central(doc, "word/document.xml", flags=0x1))
    for notebook in (b"[1, 2]", b'{"cells": 3}', b"[" * 100_000 + b"]" * 100_000):
        with pytest.raises(UnreadableAttachment, match="노트북 파일 형식"):
            extract_text("lab.ipynb", notebook)
    assert extract_text("lab.ipynb", b'{"cells": [1, {"source": ["a", 1]}]}')[1] == "--- 셀 2 (?) ---\na1"
    for error in (TypeError("x"), KeyError("x"), AttributeError("x"), RecursionError(), NotImplementedError()):
        def boom(z: zipfile.ZipFile, error: Exception = error) -> str:
            raise error
        monkeypatch.setitem(attachments.ZIP_READERS, "pptx", ("PowerPoint", boom))
        with pytest.raises(UnreadableAttachment) as info:
            extract_text("a.pptx", zipped({"ppt/slides/slide1.xml": ""}))
        assert "KLAS" not in str(info.value) and str(info.value)


def test_text_is_capped_and_lone_surrogates_are_replaced(monkeypatch):
    _, text = extract_text("lab.ipynb", b'{"cells": [{"source": "\\ud83d \\ud83d\\udccc"}]}')
    assert text.endswith("� 📌")
    pydantic_core.to_json(text)
    monkeypatch.setattr(attachments, "MAX_TEXT_CHARS", 10)
    _, text = extract_text("a.txt", b"0123456789abcdef")
    assert text.startswith("0123456789\n\n(") and "10자까지만" in text and "abc" not in text


def test_zip_listing_decodes_korean_names_and_neutralises_controls():
    data = zipped({"abcd1.py": "x", "a\nb.py": "y", "\u202eyp.exe": "z"})
    data = data.replace(b"abcd1.py", "과제1.py".encode("cp949"))  # Korean Windows: cp949, no UTF-8 flag
    _, listing = extract_text("src.zip", data)
    assert listing.splitlines()[1:] == ["과제1.py (0KB)", "a?b.py (0KB)", "?yp.exe (0KB)"]


class FileClient(ItemClient):
    downloads: list[str]  # set by service()

    async def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        if path == FILE_LIST:
            self.calls.append((path, body or {}))
            return [{"fileName": "10주차.pdf", "fileSize": 2048, "download": "/common/file/DownloadFile/B1/1"},
                    {"fileName": "실습.ipynb", "fileSize": 1024, "download": "/common/file/DownloadFile/B1/2"}]
        return await super().post(path, body)

    async def download(self, path: str, max_bytes: int) -> bytes:
        self.downloads.append(path)
        return MINI_PDF if path.endswith("/1") else b'{"cells": []}'


def service() -> tuple[KlasService, FileClient]:
    client = FileClient()
    client.downloads = []
    return KlasService(client, now=lambda: datetime(2026, 11, 5, 12, 0, tzinfo=KST)), client


async def test_read_attachment_from_a_post_picks_the_named_file():
    svc, client = service()
    out = await svc.read_attachment("데이터", "10주차 자료", "pdf")
    assert out["file"] == "10주차.pdf" and out["kind"] == "PDF" and "Naive Bayes" in out["text"]
    assert out["part"] == 1 and out["total_parts"] == 1 and client.downloads == ["/common/file/DownloadFile/B1/1"]
    assert [b for p, b in client.calls if p == FILE_LIST][-1] == {"storageId": "CLS_BOARD", "attachId": "B1"}
    with pytest.raises(LookupError, match="파일 이름을 정해"):
        await svc.read_attachment("데이터", "10주차 자료")  # two files, none named


async def test_read_attachment_from_an_assignment():
    svc, client = service()
    out = await svc.read_attachment("데이터", "HW3", "ipynb", source="assignment")
    assert out["from"] == "HW3" and out["kind"] == "Jupyter 노트북"
    assert [b for p, b in client.calls if p == FILE_LIST][-1]["storageId"] == "CLS_PROF_TASK"
    assert any(p == TASK_VIEW for p, _ in client.calls)


async def test_read_attachment_names_a_broken_file_instead_of_blaming_klas(monkeypatch):
    svc, client = service()

    async def broken(path: str, max_bytes: int) -> bytes:
        return b"[1, 2]"
    monkeypatch.setattr(client, "download", broken)
    with pytest.raises(LookupError, match="^실습.ipynb: 노트북 파일 형식이 올바르지 않습니다"):
        await svc.read_attachment("데이터", "HW3", "ipynb", source="assignment")


async def test_download_only_fetches_attachment_paths():
    client = KlasClient("id", "pw")
    with pytest.raises(KlasError, match="only attachment downloads"):
        await client.download("/std/cmn/frame/StdHome.do", 1000)
    await client.aclose()
