"""A fake KLAS client over evals/fixtures/student.json, so KlasService's real shaping code runs.

Only `post`, `page` and `download` are used by KlasService (see kw_mcp.klas.KlasClient). Paths are mapped
back to the service module's constant names, so a renamed path still routes. Never logs in, never
touches the keychain or the network.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from kw_mcp import service as svc_module
from kw_mcp.klas import KlasError
from kw_mcp.service import KlasService

FIXTURE = Path(__file__).parent / "fixtures" / "student.json"
PER_COURSE = ("TASKS", "ONLINE", "PROJECTS", "QUIZZES", "ONLINE_TESTS", "SURVEYS", "DISCUSSIONS", "COURSE_HOME")
FIXED = ("GRADES", "GRADE_TOTALS", "STUDENT_RECORD", "GEN_ED", "GRADUATION_CHECK", "STANDING", "GRADE_TERM",
         "EVAL_TERM", "EVAL_COURSES", "SCHOLARSHIP_TERM", "SCHOLARSHIP_HISTORY", "DROP_CREDITS_TERM")
_BOARD = re.compile(r"^/std/lis/sport/([0-9a-f]+)/Board(Std(?:List|View))\.do$")
_TAGS = re.compile(r"<[^>]+>")
# 학적·어학 answers for the same made-up student, shaped like the page templates (2026-11-07). The name,
# student id and advisor fields are placeholders the service must never pass on.
_FAKE_ME = {"kname": "가상학생", "hakbun": "2024000123", "jidoName": "가상교수", "jidoEmail": "advisor@example.invalid"}
ACADEMIC: dict[str, Any] = {
    "LEAVE_WINDOWS": {
        "commitStr01": "<b>일반휴학</b><br>(신청불가)",
        "commentStr01": "신청기간이 아닙니다! <br>기간 : 2027.01.04부터 2027.02.19까지시간 : 09:00부터 17:00까지",
        "commitStr02": "<b>일반휴학연기</b><br>(신청불가)",
        "commentStr02": "신청기간이 아닙니다! <br>기간 : 2027.01.04부터 2027.02.19까지시간 : 09:00부터 17:00까지",
        "commitStr03": "<b>군입휴학</b><br>(신청가능)",
        "commentStr03": "기간 : 2026.09.01부터 2026.12.31까지시간 : 09:00부터 17:00까지",
        "commitStr04": "<b>군입휴학연기</b><br>(신청불가)",
        "commentStr04": "입영 일자가 바뀐 경우에만 신청합니다. (평가용 가상 안내문)",
        "commitStr05": "<b>일반복학</b><br>(신청불가)",
        "commentStr05": "신청기간이 아닙니다! <br>기간 : 2027.01.04부터 2027.02.19까지시간 : 09:00부터 17:00까지",
        "commitStr06": "", "commentStr06": "",
    },
    "LEAVE_STATUS": {
        "stats": True, "returnMsg": "", "applyCnt": 1, "hakjukName": "재학", "hakjukDate": "20260302",
        "combackDate": None,
        "statu": [{"gubun": "일반휴학", "applyDate": "20250105", "processName": "승인", "processDate": "20250110",
                   "bigo": "", "processOpt": "Y", "gubunCode": "1"}],
    },
    "MAJOR_APPLIED": {
        "stats": True, "returnMsg": "", "hakjukMap": _FAKE_ME,
        "resultList": [{"submajor": "복수전공", "applyDate": "2026.05.20", "organName": "경영대학", "className": "경영학부",
                        "majorName": "경영학전공", "dayName": "주간", "finishOpt": "N", "submajorOpt": "2",
                        "organCode": "00", "classCode": "00", "majorCode": "00"}],
    },
    "MICRO_APPLIED": {"stats": True, "returnMsg": "", "hakjukMap": _FAKE_ME, "resultList": []},
    "LINKED_APPLIED": {"stats": True, "returnMsg": "", "hakjukMap": _FAKE_ME, "resultList": []},
    "LANGUAGE_REQUIREMENT": [{"daesangOpt": "Y", "passOpt": "N", "langName": None, "langScore": None, "langDate": None,
                              "codeName1": "졸업인증", "dayOpt": "주간", "graduateDate": None, "kname": "가상학생",
                              "hakbun": "2024000123"}],
}
COURSE_DROP_HTML = "<html><body><div class='tablelistbox'>수강포기 기간이 아닙니다.</div></body></html>"


def load(path: Path = FIXTURE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def docx_bytes(lines: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{escape(line)}</w:t></w:r></w:p>" for line in lines)
    return _zip({"[Content_Types].xml": "<Types/>",
                 "word/document.xml": f'<w:document xmlns:w="w"><w:body>{body}</w:body></w:document>'})


def pptx_bytes(lines: list[str]) -> bytes:
    slides = {f"ppt/slides/slide{i}.xml": f"<p:sld><a:p><a:r><a:t>{escape(line)}</a:t></a:r></a:p></p:sld>"
              for i, line in enumerate(lines, 1)}
    return _zip({"[Content_Types].xml": "<Types/>", **slides})


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


def file_bytes(entry: dict[str, Any]) -> bytes:
    lines = entry["text"]
    if entry["kind"] == "docx":
        return docx_bytes(lines)
    if entry["kind"] == "pptx":
        return pptx_bytes(lines)
    return "\n".join(lines).encode("utf-8")


class FakeKlasClient:
    """Answers KlasService's requests from the fixture. Unknown paths raise KlasError, like a KLAS
    page that changed, so a missing fixture section shows up as a tool error rather than as 'none'."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self._names = {getattr(svc_module, n): n for n in (*PER_COURSE, *FIXED, *ACADEMIC, "SEMESTERS", "HOME",
                                                            "TASK_VIEW", "FILE_LIST", "SYLLABUS", "ATTENDANCE")}
        self._boards = {master: "notice" if no == "1" else "library" for _, master, no in svc_module.BOARDS}

    async def post(self, path: str, body: dict[str, Any] | None = None, *, allow_empty: bool = False) -> Any:
        self.calls.append((path, body))
        body = body or {}
        name = self._names.get(path)
        if name == "SEMESTERS":
            return self.data["semesters"]
        if name == "HOME":
            sem = body.get("searchYearhakgi")
            if sem not in self.data["home"]:
                raise KlasError(f"fixture has no home page for {sem}")
            return self.data["home"][sem]
        if name in PER_COURSE:
            subj = body.get("selectSubj")
            default: Any = {} if name == "COURSE_HOME" else []
            return self.data["per_course"].get(name, {}).get(subj, default)
        if name == "SYLLABUS":
            return self.data["per_course"]["SYLLABUS"].get(body.get("selectSubj"), [])
        if name == "ATTENDANCE":
            return self.data["per_course"]["ATTENDANCE"].get(body.get("subj"), [])
        if name == "TASK_VIEW":
            view = self.data["task_view"].get(body.get("selectSubj"), {}).get(str(body.get("ordseq")))
            if view is None:
                raise KlasError("fixture has no task view")
            return view
        if name == "FILE_LIST":
            files = self.data["files"].get(body.get("attachId"), [])
            return [{"fileName": f["fileName"], "fileSize": len(file_bytes(f)),
                     "download": f"/common/file/DownloadFile/{body.get('attachId')}/{i}"} for i, f in enumerate(files, 1)]
        if name in FIXED:
            value = self.data["fixed"][name]
            if value is None and not allow_empty:
                raise KlasError(f"empty answer for {name}")
            return value
        if name in ACADEMIC:
            return ACADEMIC[name]
        if m := _BOARD.match(path):
            return self._board(self._boards.get(m.group(1)), m.group(2), body)
        raise KlasError(f"fixture has no answer for {path}")

    def _board(self, kind: str | None, page: str, body: dict[str, Any]) -> Any:
        posts = self.data["boards"].get(body.get("selectSubj"), {}).get(kind or "", [])
        if page == "StdView":
            for p in posts:
                if str(p["boardNo"]) == str(body.get("boardNo")):
                    return {"board": {k: p.get(k) for k in ("title", "content", "registDt", "updtDt", "atchFileId")}}
            return {"board": None}
        keyword = (body.get("searchKeyword") or "").strip()
        in_body = body.get("searchCondition") != "TLE"
        hits = [p for p in posts if not keyword or keyword in p["title"]
                or (in_body and keyword in _TAGS.sub(" ", p.get("content") or ""))]
        hits.sort(key=lambda p: (p.get("topAt") == "Y", p["registDt"]), reverse=True)
        rows = [{k: p.get(k) for k in ("boardNo", "title", "registDt", "topAt", "fileCnt", "atchFileId")} for p in hits[:10]]
        return {"list": rows, "page": {"totalElements": len(hits)}}

    async def page(self, path: str) -> str:
        self.calls.append((path, None))
        if path == svc_module.COURSE_DROP_PAGE:
            return COURSE_DROP_HTML
        raise KlasError(f"fixture has no page {path}")

    async def download(self, path: str, max_bytes: int) -> bytes:
        m = re.fullmatch(r"/common/file/DownloadFile/([^/]+)/(\d+)", path)
        if not m:
            raise KlasError(f"fixture can't download {path}")
        files = self.data["files"].get(m.group(1), [])
        index = int(m.group(2)) - 1
        if not 0 <= index < len(files):
            raise KlasError("no such fixture file")
        return file_bytes(files[index])


def build_service(path: Path = FIXTURE) -> tuple[KlasService, FakeKlasClient]:
    data = load(path)
    now = datetime.fromisoformat(data["now"])
    client = FakeKlasClient(data)
    return KlasService(client, now=lambda: now), client
