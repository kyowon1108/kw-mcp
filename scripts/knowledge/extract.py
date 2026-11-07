"""Text out of everything in raw/: HTML pages (main content only), PDF, HWP/HWPX/DOCX/XLSX, old .xls.

Files are read with this repo's own parsers (kw_mcp.text.html_to_text, kw_mcp.attachments.extract_text).
The school's 필수과목표 are old-format Excel (.xls), which kw_mcp.attachments does not read; those go through
xlrd (run with `uv run --with xlrd`). HTML tables are flattened to "a | b | c" rows (rowspan/colspan
expanded) so a model can read them.

    python extract.py            # every raw file without a text/ twin
    python extract.py --force    # redo all
"""

from __future__ import annotations

import argparse
import re
from html import unescape
from html.parser import HTMLParser

from kbcommon import RAW, TEXT

from kw_mcp.attachments import UnreadableAttachment, extract_text
from kw_mcp.text import html_to_text

# Where the readable part of a page starts, per site family. The first marker found wins.
CONTENT_MARKERS = (
    'id="jwxe_main_content"',   # www.kw.ac.kr
    'class="contents-box"',
    'id="sub_content"', 'id="content"', 'id="contents"', 'class="content"', 'class="sub_content"',
    "<body",
)
CUT_MARKERS = ('class="contents-damdang"', 'id="footer"', 'class="footer"', "<footer")


class _Tables(HTMLParser):
    """Rewrites <table> blocks as pipe-separated lines, expanding rowspan/colspan."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.stack: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.stack.append({"rows": [], "row": None, "cell": None, "spans": {}})
            return
        if not self.stack:
            self.out.append(self.get_starttag_text() or "")
            return
        t = self.stack[-1]
        if tag == "tr":
            t["row"] = []
        elif tag in ("td", "th"):
            t["cell"] = {"text": [], "rs": _num(a.get("rowspan")), "cs": _num(a.get("colspan"))}
        elif tag in ("br", "p", "div", "li") and t["cell"] is not None:
            t["cell"]["text"].append(" ")

    def handle_endtag(self, tag):
        if not self.stack:
            self.out.append(f"</{tag}>")
            return
        t = self.stack[-1]
        if tag in ("td", "th") and t["cell"] is not None:
            if t["row"] is None:
                t["row"] = []
            t["row"].append(t["cell"])
            t["cell"] = None
        elif tag == "tr" and t["row"] is not None:
            t["rows"].append(t["row"])
            t["row"] = None
        elif tag == "table":
            if t["row"]:
                t["rows"].append(t["row"])
            self.stack.pop()
            lines = _grid(t["rows"])
            block = "\n<p>[표]</p>\n" + "".join(f"<p>{_esc(line)}</p>\n" for line in lines) + "<p>[표 끝]</p>\n"
            if self.stack and self.stack[-1]["cell"] is not None:
                self.stack[-1]["cell"]["text"].append(" / ".join(lines))
            else:
                self.out.append(block)

    def handle_data(self, data):
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"]["text"].append(data)
        elif not self.stack:
            self.out.append(_esc(data))


def _num(v) -> int:
    try:
        return max(1, min(int(v or 1), 50))
    except ValueError:
        return 1


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _grid(rows: list[list[dict]]) -> list[str]:
    pending: dict[int, tuple[str, int]] = {}  # column -> (text, rows left)
    lines = []
    for row in rows:
        cells, col, it = [], 0, iter(row)
        cur = next(it, None)
        while cur is not None or any(c >= col for c in pending):
            if col in pending:
                text, left = pending[col]
                cells.append(text)
                if left <= 1:
                    del pending[col]
                else:
                    pending[col] = (text, left - 1)
                col += 1
                continue
            if cur is None:
                break
            text = re.sub(r"\s+", " ", "".join(cur["text"])).strip()
            for k in range(cur["cs"]):
                cells.append(text)
                if cur["rs"] > 1:
                    pending[col + k] = (text, cur["rs"] - 1)
            col += cur["cs"]
            cur = next(it, None)
        if any(cells):
            lines.append(" | ".join(cells))
    return lines


def html_main_text(html: str) -> str:
    start = 0
    for m in CONTENT_MARKERS:
        i = html.find(m)
        if i >= 0:
            start = i
            break
    end = len(html)
    for m in CUT_MARKERS:
        j = html.find(m, start + 1)
        if j > 0:
            end = min(end, j)
    part = html[start:end]
    part = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", part)
    p = _Tables()
    p.feed(part)
    p.close()
    return html_to_text("".join(p.out), limit=10**9)


def links(html: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r'(?is)<a\s[^>]*href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>', html):
        text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        out.append((unescape(m.group(1)), text))
    return out


def decode_html(data: bytes) -> str:
    head = data[:2000].decode("ascii", "replace").lower()
    enc = "utf-8"
    m = re.search(r'charset=["\']?([a-z0-9_-]+)', head)
    if m and m.group(1) in ("euc-kr", "ks_c_5601-1987", "cp949"):
        enc = "cp949"
    text = data.decode(enc, "replace")
    if enc == "utf-8" and text.count("\ufffd") > 20:  # old ASP pages send EUC-KR without saying so
        text = data.decode("cp949", "replace")
    return text


XLS_FROM_YEAR = 2015  # 필수과목표 rows before this calendar year are left out (they go back to 1991)


def _cell(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return re.sub(r"\s+", " ", str(v)).strip()


def xls_text(data: bytes) -> str:
    """Old-format Excel (BIFF, .xls) via xlrd - kw_mcp.attachments reads only .xlsx. Rows as "a | b | c"."""
    import xlrd  # run with: uv run --with xlrd

    book = xlrd.open_workbook(file_contents=data)
    out = []
    for sheet in book.sheets():
        out.append(f"--- 시트 {sheet.name.strip()} ---")
        year = None
        for r in range(sheet.nrows):
            cells = [_cell(c.value) for c in sheet.row(r)]
            if re.fullmatch(r"(19|20)\d\d", cells[0] if cells else ""):
                year = int(cells[0])
            if year is not None and year < XLS_FROM_YEAR:
                continue
            while cells and not cells[-1]:
                cells.pop()
            if any(cells):
                out.append(" | ".join(cells))
    return "\n".join(out)


def extract_one(path, force: bool = False) -> str | None:
    out = TEXT / (path.stem + ".txt")
    if out.exists() and not force:
        return out.read_text(encoding="utf-8")
    data = path.read_bytes()
    ext = path.suffix.lower()
    try:
        if ext == ".html":
            text = html_main_text(decode_html(data))
        elif ext == ".xls":
            text = xls_text(data)
        elif ext in (".pdf", ".hwp", ".hwpx", ".docx", ".xlsx", ".pptx"):
            text = extract_text(path.name, data)[1]
        else:
            return None
    except UnreadableAttachment as e:
        text = f"(읽지 못함: {e})"
    out.write_text(text, encoding="utf-8")
    return text


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("names", nargs="*", help="raw file stems (default: all)")
    args = ap.parse_args()
    for path in sorted(RAW.iterdir()):
        if path.name.endswith(".meta.json") or (args.names and path.stem not in args.names):
            continue
        text = extract_one(path, args.force)
        if text is not None:
            print(f"{path.stem}\t{len(text)}")


if __name__ == "__main__":
    main()
