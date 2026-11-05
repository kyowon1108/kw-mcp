import io
import json
import struct
import zipfile
from datetime import datetime
from typing import Any

import pytest

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


class FileClient(ItemClient):
    downloads: list[str] = []

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


async def test_download_only_fetches_attachment_paths():
    client = KlasClient("id", "pw")
    with pytest.raises(KlasError, match="only attachment downloads"):
        await client.download("/std/cmn/frame/StdHome.do", 1000)
    await client.aclose()
