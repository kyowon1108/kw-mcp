"""Review 3 fixes in attachments.py: xlsx columns, dates and prefixes; bounded HWP (OLE) and PDF reading."""

import io
import struct
import time
import tracemalloc
import zlib

import olefile
import pytest
from pypdf import PageObject, PdfReader, PdfWriter

from kw_mcp import attachments
from kw_mcp.attachments import UnreadableAttachment, extract_text
from tests.test_attachments import MINI_PDF, hwp_record, utf16, zipped

# --- xlsx -----------------------------------------------------------------------------------------


def workbook(rows: str, strings: str | None = None, styles: str | None = None, book: str | None = None,
             sheet: str = "<worksheet><sheetData>{}</sheetData></worksheet>") -> bytes:
    files = {"xl/worksheets/sheet1.xml": sheet.format(rows)}
    for name, xml in (("xl/sharedStrings.xml", strings), ("xl/styles.xml", styles), ("xl/workbook.xml", book)):
        if xml is not None:
            files[name] = xml
    return zipped(files)


def sheet_text(data: bytes) -> str:
    kind, text = extract_text("성적.xlsx", data)
    assert kind == "Excel" and text.startswith("--- 시트 1 ---\n")
    return text.removeprefix("--- 시트 1 ---\n")


SCORES = "<sst>" + "".join(f"<si><t>{s}</t></si>" for s in ("이름", "중간", "기말", "과제", "학생A", "학생B")) + "</sst>"


def test_xlsx_interior_blanks_keep_later_values_under_their_headers():
    rows = ('<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c>'
            '<c r="C1" t="s"><v>2</v></c><c r="D1" t="s"><v>3</v></c></row>'
            # B2 left out (Excel writes no cell for it): 90 is the final, not the midterm
            '<row r="2"><c r="A2" t="s"><v>4</v></c><c r="C2"><v>90</v></c><c r="D2"><v>80</v></c></row>'
            # B3 a styled blank, C3 a formula with no saved value
            '<row r="3"><c r="A3" t="s"><v>5</v></c><c r="B3" s="0"/><c r="C3"><f>B3*2</f></c><c r="D3"><v>70</v></c></row>')
    assert sheet_text(workbook(rows, SCORES)) == "이름 | 중간 | 기말 | 과제\n학생A |  | 90 | 80\n학생B |  |  | 70"


def test_xlsx_leading_blanks_keep_their_columns_and_a_shared_left_margin_is_dropped():
    rows = ('<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c></row>'
            '<row r="2"><c r="A2" s="0"/><c r="B2"><v>85</v></c><c r="C2"><v>90</v></c></row>'  # no name
            '<row r="3"><c r="C3"><v>77</v></c></row>')  # only the final
    assert sheet_text(workbook(rows, SCORES)) == "이름 | 중간 | 기말\n | 85 | 90\n |  | 77"
    # The same table starting at column C, as when the first columns are left as a margin.
    shifted = rows.replace('r="A', 'r="X').replace('r="C', 'r="E').replace('r="B', 'r="D').replace('r="X', 'r="C')
    assert sheet_text(workbook(shifted, SCORES)) == "이름 | 중간 | 기말\n | 85 | 90\n |  | 77"


def test_xlsx_cells_without_a_usable_reference_follow_the_one_before():
    rows = ('<row><c t="s"><v>0</v></c><c s="1"/><c><v>3</v></c></row>'  # no r= at all
            '<row r="2"><c r="B2"><v>1</v></c><c><v>2</v></c><c r="A2"><v>3</v></c><c r="XFE2"><v>4</v></c></row>')
    assert sheet_text(workbook(rows, SCORES)) == "이름 |  | 3\n | 1 | 2 | 3 | 4"


def test_xlsx_shared_strings_and_far_right_cells_cannot_blow_up_the_text(monkeypatch):
    monkeypatch.setattr(attachments, "MAX_TEXT_CHARS", 50_000)
    strings = f"<sst><si><t>{'x' * 10_000}</t></si></sst>"  # 10 KB, named by 2,000 cells: 20 MB of text
    rows = "".join(f'<row r="{r}">' + '<c t="s"><v>0</v></c>' * 20 + "</row>" for r in range(1, 101))
    tracemalloc.start()
    try:
        text = extract_text("a.xlsx", workbook(rows, strings))[1]
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 5 * 1024 * 1024 and "50,000자까지만" in text
    # Every other row has its value in the last column: 16,383 empty fields before it, as column A is used.
    rows = "".join(f'<row r="{r}"><c r="XFD{r}"><v>1</v></c></row><row><c><v>2</v></c></row>' for r in range(1, 2001))
    out = attachments._sheet_rows(f"<sheetData>{rows}</sheetData>", [], [], False, 50_000)
    assert len(out) == 3 and out[0] == " | " * 16_383 + "1" and out[1] == "2"  # stopped right past the budget
    assert "50,000자까지만" in extract_text("a.xlsx", workbook(rows))[1]
    # Only far-right values: the shared margin is dropped, so it costs nothing.
    rows = "".join(f'<row r="{r}"><c r="XFC{r}"><v>{r}</v></c><c r="XFD{r}"><v>1</v></c></row>' for r in range(1, 2001))
    assert sheet_text(workbook(rows)).splitlines()[-1] == "2000 | 1"


def test_xlsx_cells_past_the_last_column_are_dropped_and_cost_nothing(monkeypatch):
    # A million bare <c/> (each takes the next column) and then a value, which would land far past XFD. The
    # blanks once came out as a million empty fields before it, held in several copies.
    for lead in ("", '<c r="XFD1"/>'):
        xml = f'<sheetData><row r="1"><c r="A1"><v>1</v></c>{lead}{"<c/>" * 1_000_000}<c><v>2</v></c></row></sheetData>'
        tracemalloc.start()
        try:
            out = attachments._sheet_rows(xml, [], [], False, attachments.MAX_TEXT_CHARS)
            peak = tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()
        assert out == ["1"] and peak < 1024 * 1024
    # A value that reaches XFD keeps its column; the next one has no column left.
    row = '<row r="1"><c r="A1"><v>1</v></c>' + "<c/>" * 16_382 + "<c><v>2</v></c><c><v>3</v></c></row>"
    assert sheet_text(workbook(row)) == "1" + " | " * 16_383 + "2"
    # The cells after a full row are not even read.
    read = []
    cell_text = attachments._cell_text
    monkeypatch.setattr(attachments, "_cell_text", lambda *a: read.append(1) or cell_text(*a))
    rows = "<row>" + "<c><v>1</v></c>" * (attachments.MAX_COLUMNS + 1_000) + "</row><row><c><v>2</v></c></row>"
    assert sheet_text(workbook(rows)).splitlines()[-1] == "2" and len(read) == attachments.MAX_COLUMNS + 1


def capped(full: str, cap: int) -> str:
    return full if len(full) <= cap else full[:cap] + f"\n\n(너무 길어 앞의 {cap:,}자까지만 읽었습니다.)"


def test_xlsx_rows_are_never_left_out_without_the_note(monkeypatch):
    rows = "".join(f'<row r="{r}"><c r="A{r}" t="s"><v>{r % 6}</v></c><c r="C{r}"><v>{r * 37}</v></c>'
                   + (f'<c r="F{r}" t="s"><v>4</v></c>' if r % 3 else "") + "</row>" for r in range(1, 25))
    sheet = f"<worksheet><sheetData>{rows}</sheetData></worksheet>"
    data = zipped({"xl/sharedStrings.xml": SCORES, "xl/worksheets/sheet1.xml": sheet, "xl/worksheets/sheet2.xml": sheet})
    full = extract_text("a.xlsx", data)[1]
    assert full.count("\n") == 2 * 24 + 2  # two sheets of a header and 24 rows, a blank line between
    for cap in range(1, len(full) + 3):
        monkeypatch.setattr(attachments, "MAX_TEXT_CHARS", cap)
        assert extract_text("a.xlsx", data)[1] == capped(full, cap), cap


STYLES = """<styleSheet><numFmts count="7">
<numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd"/><numFmt numFmtId="165" formatCode="[$-412]AM/PM\\ h:mm"/>
<numFmt numFmtId="166" formatCode="[h]:mm"/><numFmt numFmtId="167" formatCode="#,##0&quot;점&quot;"/>
<numFmt numFmtId="168" formatCode="0 &quot;days&quot;"/><numFmt numFmtId="169" formatCode="0.00E+00"/>
<numFmt numFmtId="170" formatCode="yyyy&quot;년&quot; m&quot;월&quot; d&quot;일&quot;;@"/></numFmts>
<cellStyleXfs count="1"><xf numFmtId="14"/></cellStyleXfs>
<cellXfs count="13"><xf numFmtId="0"/><xf numFmtId="14" applyNumberFormat="1"/><xf numFmtId="22"/><xf numFmtId="20"/>
<xf numFmtId="164"><alignment horizontal="center"/></xf><xf numFmtId="165"/><xf numFmtId="166"/><xf numFmtId="167"/>
<xf numFmtId="168"/><xf numFmtId="169"/><xf numFmtId="170"/><xf numFmtId="58"/><xf numFmtId="49"/></cellXfs>
<dxfs count="1"><dxf><numFmt numFmtId="164" formatCode="0.00"/></dxf></dxfs></styleSheet>"""


def cells(*values: tuple[int, str] | tuple[int, str, str]) -> str:
    """One row: (style, value) or (style, value, type) per cell."""
    row = ""
    for style, value, *kind in values:
        row += f'<c s="{style}"' + "".join(f' t="{k}"' for k in kind) + f"><v>{value}</v></c>"
    return f"<row>{row}</row>"


def test_xlsx_dates_and_times_come_out_as_iso_text():
    rows = (cells((1, "46335"), (2, "46335.375"), (3, "0.375"), (3, "0.3750115740740741"), (4, "46335"))
            + cells((5, "0.5625"), (6, "1.5"), (10, "46335"), (11, "46335"), (11, "0.75"), (11, "46335.75"))
            + cells((1, "1"), (1, "59"), (1, "61"), (1, "-1"), (1, "3000000"), (4, "46334.99999999999")))
    assert sheet_text(workbook(rows, styles=STYLES)).splitlines() == [
        "2026-11-09 | 2026-11-09 09:00 | 09:00 | 09:00:01 | 2026-11-09",
        "13:30 | 36:00 | 2026-11-09 | 2026-11-09 | 18:00 | 2026-11-09 18:00",
        "1900-01-01 | 1900-02-28 | 1900-03-01 | -1 | 3000000 | 2026-11-09",  # a formula's rounding error
    ]


def test_xlsx_numbers_text_and_other_formats_stay_as_written():
    strings = "<sst><si><t>46335</t></si></sst>"
    rows = cells((0, "46335"), (7, "95"), (8, "3"), (9, "12000"), (12, "46335"), (99, "46335"), (1, "0", "s"),
                 (1, "TRUE", "str"), (1, "#N/A", "e"))
    assert sheet_text(workbook(rows, strings, STYLES)) == "46335 | 95 | 3 | 12000 | 46335 | 46335 | 46335 | TRUE | #N/A"


def test_xlsx_1904_workbooks_count_from_1904():
    rows = cells((1, "0"), (1, "44873"), (2, "44873.5"))
    for flag in ('date1904="1"', "date1904='true'"):
        book = f"<workbook><workbookPr {flag} defaultThemeVersion=\"166925\"/></workbook>"
        assert sheet_text(workbook(rows, styles=STYLES, book=book)) == "1904-01-01 | 2026-11-09 | 2026-11-09 12:00"
    book = '<workbook><workbookPr date1904="0"/></workbook>'
    assert sheet_text(workbook(rows, styles=STYLES, book=book)) == "1899-12-31 | 2022-11-08 | 2022-11-08 12:00"


def test_xlsx_with_prefixed_spreadsheetml_is_read():
    ns = 'xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    strings = f"<x:sst {ns}><x:si><x:t>과제</x:t></x:si><x:si><x:r><x:t>제출</x:t></x:r><x:r><x:t>일</x:t></x:r></x:si></x:sst>"
    styles = f"<x:styleSheet {ns}><x:cellXfs><x:xf numFmtId=\"0\"/><x:xf numFmtId=\"14\"/></x:cellXfs></x:styleSheet>"
    rows = ('<x:row r="1"><x:c r="A1" t="s"><x:v>0</x:v></x:c><x:c r="B1" t="s"><x:v>1</x:v></x:c></x:row>'
            '<x:row r="2"><x:c r="A2" t="inlineStr"><x:is><x:t>HW3</x:t></x:is></x:c><x:c r="B2" s="1"><x:v>46335</x:v></x:c></x:row>')
    data = workbook(rows, strings, styles, sheet=f"<x:worksheet {ns}><x:sheetData>{{}}</x:sheetData></x:worksheet>")
    assert sheet_text(data) == "과제 | 제출일\nHW3 | 2026-11-09"


def test_number_format_kinds():
    kind = attachments._format_kind
    assert [kind(c) for c in ("yyyy-mm-dd", "d-mmm", "mmm", "h:mm", "mm:ss", "[mm]:ss", "h:mm AM/PM",
                              'yyyy"년" m"월" d"일" dddd', "m/d/yyyy h:mm", "General", "@", "0.0%",
                              '"주"0', "0.00E+00", '[Red]#,##0;[Blue]-#,##0', '_-* #,##0_-;-* #,##0_-;_-* "-"_-;_-@_-',
                              "[$₩-412]#,##0")] == [
        "date", "date", "date", "time", "time", "elapsed", "time", "date", "datetime",
        None, None, None, None, None, None, None, None]


# --- HWP (OLE compound files) ---------------------------------------------------------------------

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ENDOFCHAIN, FATSECT, FREESECT, NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF, 0xFFFFFFFF
SECTOR, MINI = 512, 64


def at(sector: int) -> int:
    """The file offset of a sector (sector 0 follows the 512-byte header)."""
    return SECTOR * (sector + 1)


def cfb(streams: dict[str, bytes]) -> tuple[bytearray, dict[str, int]]:
    """A version 3 compound file (the OLE container HWP 5 uses) holding `streams` ("BodyText/Section0": data),
    written by hand since olefile only reads. Also returns where its parts are: "dir" (the directory
    sector), "minifat" and "ministream" (first sectors), "sid:<path>" (directory entry numbers) and
    "<path>" (a stream's first sector, or first mini sector under 4 KB)."""
    entries: list[dict] = [{"name": "Root Entry", "type": 5, "kids": [], "path": ""}]
    sid = {"": 0}
    for path in streams:
        parts = path.split("/")
        for depth in range(len(parts)):
            key, parent = "/".join(parts[:depth + 1]), "/".join(parts[:depth])
            if key not in sid:
                sid[key] = len(entries)
                entries.append({"name": parts[depth], "type": 2 if depth == len(parts) - 1 else 1, "kids": [], "path": key})
                entries[sid[parent]]["kids"].append(sid[key])
    fat, minifat = [FREESECT] * (SECTOR // 4), [FREESECT] * (SECTOR // 4)

    def chain(table: list[int], start: int, count: int) -> int:
        for i in range(start, start + count):
            table[i] = i + 1 if i < start + count - 1 else ENDOFCHAIN
        return start

    fat[0] = FATSECT  # sector 0 is the FAT, then the directory (4 entries a sector), the MiniFAT, the mini stream
    dir_sectors = -(-len(entries) // 4)
    layout = {"dir": chain(fat, 1, dir_sectors), "minifat": chain(fat, 1 + dir_sectors, 1)}
    mini, big = bytearray(), bytearray()
    for path, data in streams.items():
        if len(data) < 4096:
            layout[path] = chain(minifat, len(mini) // MINI, -(-len(data) // MINI))
            mini += data.ljust(-(-len(data) // MINI) * MINI, b"\0")
    layout["ministream"] = chain(fat, layout["minifat"] + 1, -(-len(mini) // SECTOR))
    next_sector = layout["ministream"] + -(-len(mini) // SECTOR)
    for path, data in streams.items():
        if len(data) >= 4096:
            layout[path] = chain(fat, next_sector, -(-len(data) // SECTOR))
            next_sector += -(-len(data) // SECTOR)
            big += data.ljust(-(-len(data) // SECTOR) * SECTOR, b"\0")
    assert next_sector <= len(fat)

    directory = bytearray()
    for i, e in enumerate(entries):
        name = e["name"].encode("utf-16-le") + b"\0\0"
        parent = next((p for p in entries if i in p["kids"]), None)
        siblings = parent["kids"] if parent else []
        right = siblings[siblings.index(i) + 1] if i in siblings[:-1] else NOSTREAM
        child = e["kids"][0] if e["kids"] else NOSTREAM
        if e["type"] == 5:
            start, size = (layout["ministream"], len(mini)) if mini else (ENDOFCHAIN, 0)
        elif e["type"] == 2:
            start, size = layout[e["path"]], len(streams[e["path"]])
        else:
            start, size = 0, 0
        directory += struct.pack("<64sHBBIII16sIQQIII", name, len(name), e["type"], 1, NOSTREAM, right, child,
                                 bytes(16), 0, 0, 0, start, size, 0)
        layout[f"sid:{e['path']}"] = i
    # version 3, 512-byte sectors, 64-byte mini sectors, 1 FAT sector, mini streams under 4096 bytes, 1 MiniFAT sector
    header = struct.pack("<8s16s6H10I", OLE_MAGIC, bytes(16), 0x3E, 3, 0xFFFE, 9, 6, 0, 0, 0, 1, layout["dir"], 0,
                         4096, layout["minifat"], 1, ENDOFCHAIN, 0) + struct.pack("<109I", 0, *[FREESECT] * 108)
    sectors = [struct.pack(f"<{len(fat)}I", *fat), bytes(directory.ljust(dir_sectors * SECTOR, b"\0")),
               struct.pack(f"<{len(minifat)}I", *minifat), bytes(mini.ljust(-(-len(mini) // SECTOR) * SECTOR, b"\0")),
               bytes(big)]
    return bytearray(header + b"".join(sectors)), layout


def hwp_header(compressed: bool) -> bytes:
    return b"HWP Document File".ljust(32, b"\0") + struct.pack("<II", 0x05000300, int(compressed)) + bytes(216)


def put(data: bytearray, offset: int, value: int) -> None:
    struct.pack_into("<I", data, offset, value)


def entry_size(layout: dict[str, int], path: str) -> int:
    """The file offset of a directory entry's size field."""
    return at(layout["dir"]) + 128 * layout[f"sid:{path}"] + 120


def long_record(tag: int, body: bytes) -> bytes:
    """An HWP record over 4,094 bytes: the size field says 0xFFF and the size follows."""
    return struct.pack("<II", tag | (0xFFF << 20), len(body)) + body


def deflate(data: bytes) -> bytes:
    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    return packer.compress(data) + packer.flush()


def read_bounded(name: str, data: bytes) -> tuple[pytest.ExceptionInfo, int]:
    """extract_text's refusal of `data`, and the peak memory it used getting there."""
    tracemalloc.start()
    try:
        with pytest.raises(UnreadableAttachment) as info:
            extract_text(name, bytes(data))
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    return info, peak


def test_real_ole_hwp_files_are_read():
    small = {"FileHeader": hwp_header(True), "BodyText/Section0": deflate(hwp_record(67, utf16("중간고사 범위", [13]))),
             "BodyText/Section1": deflate(hwp_record(67, utf16("3장까지")))}
    data, _ = cfb(small)
    assert extract_text("시험.hwp", bytes(data)) == ("한글(HWP)", "중간고사 범위\n3장까지")
    long = long_record(67, utf16("가" * 3000))  # 6 KB uncompressed: stored in the FAT, not the mini stream
    data, _ = cfb({"FileHeader": hwp_header(False), "BodyText/Section0": long})
    assert extract_text("과제.hwp", bytes(data))[1] == "가" * 3000


def test_hwp_mini_stream_declared_past_the_file_is_not_followed():
    data, layout = cfb({"FileHeader": hwp_header(True), "BodyText/Section0": deflate(hwp_record(67, utf16("본문")))})
    put(data, at(0) + 4 * layout["ministream"], layout["ministream"])  # its FAT entry points to itself
    put(data, entry_size(layout, ""), 32 << 20)  # and the root entry says it holds 32 MB
    info, peak = read_bounded("a.hwp", data)
    assert "파일을 읽지 못했습니다" in str(info.value) and peak < 4 * 1024 * 1024  # olefile would read 32 MB


def test_hwp_body_stream_declared_past_the_file_is_not_followed():
    long = long_record(67, utf16("가" * 3000))
    data, layout = cfb({"FileHeader": hwp_header(False), "BodyText/Section0": long})
    last = layout["BodyText/Section0"] + -(-len(long) // SECTOR) - 1
    put(data, at(0) + 4 * last, last)
    put(data, entry_size(layout, "BodyText/Section0"), 32 << 20)
    info, peak = read_bounded("a.hwp", data)
    assert "파일을 읽지 못했습니다" in str(info.value) and peak < 4 * 1024 * 1024


@pytest.mark.parametrize("change", ["minifat", "fat", "sector"])
def test_hwp_headers_with_impossible_counts_never_reach_olefile(monkeypatch, change):
    data, layout = cfb({"FileHeader": hwp_header(True), "BodyText/Section0": deflate(hwp_record(67, utf16("본문")))})
    if change == "minifat":  # 32 MB of MiniFAT, through a FAT entry that points to itself
        put(data, 64, 65_536)
        put(data, at(0) + 4 * layout["minifat"], layout["minifat"])
    elif change == "fat":  # 5,189 FAT sectors through a DIFAT sector that names itself as the next one
        difat = len(data) // SECTOR - 1
        data += struct.pack("<128I", *[0] * 127, difat)
        put(data, 44, 109 + 127 * 40)
        put(data, 68, difat)
        put(data, 72, 40)
        for i in range(1, 109):
            put(data, 76 + 4 * i, 0)
    else:
        struct.pack_into("<H", data, 30, 2)  # 4-byte sectors
    opened = []
    real = olefile.OleFileIO
    monkeypatch.setattr(olefile, "OleFileIO", lambda f: opened.append(f) or real(f))
    info, peak = read_bounded("a.hwp", data)
    assert "파일을 읽지 못했습니다" in str(info.value) and not opened and peak < 1024 * 1024


def many_streams(count: int) -> bytes:
    """A compound file holding a FileHeader and `count` one-byte streams, each said to start at its own mini
    sector (none of them is ever read), in a balanced directory tree as real writers keep it."""
    entries = count + 2  # the root, FileHeader, the streams
    dir_sectors = -(-entries // 4)
    fat_sectors = -(-(dir_sectors + 2) // (SECTOR // 4 - 1))
    fat = [FATSECT] * fat_sectors + [fat_sectors + i + 1 for i in range(dir_sectors - 1)] + [ENDOFCHAIN]
    minifat_at = len(fat)  # then the mini stream, one sector
    fat += [ENDOFCHAIN, ENDOFCHAIN] + [FREESECT] * (fat_sectors * SECTOR // 4 - len(fat) - 2)
    kids = [[NOSTREAM, NOSTREAM] for _ in range(entries)]

    def tree(lo: int, hi: int) -> int:
        if lo > hi:
            return NOSTREAM
        mid = (lo + hi) // 2
        kids[mid] = [tree(lo, mid - 1), tree(mid + 1, hi)]
        return mid

    top = tree(1, entries - 1)
    entry = struct.Struct("<64sHBBIII16sIQQIII")
    names = ["Root Entry", "FileHeader"] + [f"s{sid}" for sid in range(2, entries)]
    directory = bytearray()
    for sid, name in enumerate(names):
        if sid == 0:  # the root: the mini stream, which holds FileHeader
            kind, child, start, size = 5, top, minifat_at + 1, 256
        elif sid == 1:
            kind, child, start, size = 2, NOSTREAM, 0, 256
        else:
            kind, child, start, size = 2, NOSTREAM, sid + 2, 1
        raw = name.encode("utf-16-le") + b"\0\0"
        directory += entry.pack(raw, len(raw), kind, 1, *kids[sid], child, bytes(16), 0, 0, 0, start, size, 0)
    header = struct.pack("<8s16s6H10I", OLE_MAGIC, bytes(16), 0x3E, 3, 0xFFFE, 9, 6, 0, 0, 0, fat_sectors, fat_sectors,
                         0, 4096, minifat_at, 1, ENDOFCHAIN, 0)
    header += struct.pack("<109I", *range(fat_sectors), *[FREESECT] * (109 - fat_sectors))
    minifat = struct.pack("<128I", 1, 2, 3, ENDOFCHAIN, *[FREESECT] * 124)  # FileHeader's 4 mini sectors
    return (header + struct.pack(f"<{len(fat)}I", *fat) + directory.ljust(dir_sectors * SECTOR, b"\0") + minifat
            + hwp_header(True).ljust(SECTOR, b"\0"))


def test_hwp_with_many_streams_is_turned_down_quickly():
    data = many_streams(40_000)  # 5 MB. olefile's own check for streams named twice is quadratic: about 3 s
    started = time.monotonic()
    with pytest.raises(UnreadableAttachment, match="항목이 너무 많아"):
        extract_text("a.hwp", data)
    assert time.monotonic() - started < 1.0
    with pytest.raises(UnreadableAttachment, match="글자가 없는 문서"):  # a few: opened and read, no body text
        extract_text("a.hwp", many_streams(3))


def test_hwp_streams_named_twice_are_noted_as_olefile_notes_them():
    text = deflate(hwp_record(67, utf16("본문")))
    data, layout = cfb({"FileHeader": hwp_header(True), "BodyText/Section0": text, "BodyText/Section1": text})
    put(data, at(layout["dir"]) + 128 * layout["sid:BodyText/Section1"] + 116, layout["BodyText/Section0"])
    with attachments._ole_class(olefile.OleFileIO)(io.BytesIO(bytes(data))) as ours, \
            olefile.OleFileIO(io.BytesIO(bytes(data))) as theirs:
        assert ours.parsing_issues == theirs.parsing_issues
        assert [message for _, message in theirs.parsing_issues] == ["Stream referenced twice"]
        assert ours._used_streams_fat == ours._used_streams_minifat == []  # olefile's list search never ran
    assert extract_text("a.hwp", bytes(data))[1] == "본문\n본문"  # both sections read the same sectors


# --- PDF ------------------------------------------------------------------------------------------

def pdf_pages(count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(count):
        writer.add_page(PdfReader(io.BytesIO(MINI_PDF)).pages[0])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_pdf_extraction_stops_at_the_text_cap(monkeypatch):
    calls = []
    extract = PageObject.extract_text
    monkeypatch.setattr(PageObject, "extract_text", lambda self, *a, **k: calls.append(1) or extract(self, *a, **k))
    monkeypatch.setattr(attachments, "MAX_TEXT_CHARS", 100)
    text = extract_text("강의.pdf", pdf_pages(20))[1]
    assert len(calls) == 4 and "100자까지만" in text  # a page is about 30 characters with its header
    monkeypatch.undo()
    data = pdf_pages(4)
    full = extract_text("강의.pdf", data)[1]
    for cap in range(1, len(full) + 3):
        monkeypatch.setattr(attachments, "MAX_TEXT_CHARS", cap)
        assert extract_text("강의.pdf", data)[1] == capped(full, cap), cap


def test_pdf_extraction_gives_up_after_its_deadline(monkeypatch):
    monkeypatch.setattr(attachments, "PDF_SECONDS", -1)
    with pytest.raises(UnreadableAttachment, match="시간이 너무 오래 걸려"):
        extract_text("강의.pdf", pdf_pages(3))
    assert "Naive Bayes" in extract_text("강의.pdf", MINI_PDF)[1]  # the first page is always read


def test_a_late_narrow_row_cannot_repad_the_whole_sheet_past_the_budget():
    """2,000 rows with a value only in XFD, then one at column A: the margin drops at the end, and
    the earlier rows must not all be re-padded to 16k columns (98M characters from 138 KB before)."""
    import tracemalloc

    from kw_mcp import attachments

    rows = "".join(f'<row r="{i}"><c r="XFD{i}" t="inlineStr"><is><t>x</t></is></c></row>' for i in range(1, 2001))
    rows += '<row r="2001"><c r="A2001" t="inlineStr"><is><t>a</t></is></c></row>'
    xml = f"<worksheet><sheetData>{rows}</sheetData></worksheet>"
    tracemalloc.start()
    lines = attachments._sheet_rows(xml, [], [], False, attachments.MAX_TEXT_CHARS)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert sum(len(line) + 1 for line in lines) <= attachments.MAX_TEXT_CHARS + 200_000
    assert peak < 200 * 1024 * 1024
