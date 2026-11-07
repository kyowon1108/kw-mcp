"""One school notice in full (title, date, body text, attachments, images) for the extension's
read_school_notice and the kw-campus connector's read_notice.

Only pages on the hosts the kw-campus collectors read are fetched (PAGE_HOSTS): www.kw.ac.kr, the
department and college boards (kwcampus.deptboards, aicon), the two Wix sites (wixfeeds) and 총동문회's
gnuboard (kwcampus.smallboards; 총학생회 and 현장실습 are collected but never read as pages). A
page's images and files may come from another allowed host (department pages show images kept on
www.kw.ac.kr) or, for the Wix sites, from Wix's file host. Redirects are followed by hand and every
hop is checked the same way, so nothing off the list is ever requested.

Requests carry the extension's honest User-Agent, go over HTTP/1.1 (some department hosts answer
HTTP/2 with an empty 200), keep no cookies and are capped in size and time. In one process a host
gets at most one request every MIN_INTERVAL_S (Pacer); the connector passes its own gate (robots
records, the same interval across Lambda instances, a daily cap). A parsed page is kept CACHE_S.

Templates: www's boards (jwxe, div.board-view-box), the BoardMode department boards (div.view_top,
view_file, view_con), the admin_mode=read boards of aicon, chemng and sports (table.board-view), gnuboard
posts (article#bo_v), and everything else (the agency and ingenium boards, Wix posts) by a generic
main-content search. The
body and attachment text are someone else's writing and come wrapped by text.untrusted.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import re
import struct
import time
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit

import httpx
from mcp.types import ImageContent, TextContent

from .attachments import (
    MAX_DOWNLOAD_BYTES,
    UnreadableAttachment,
    extract_text,
    split_parts,
)
from .klas import USER_AGENT
from .text import clean, html_to_text, scrub, untrusted

MIB = 1024 * 1024
MIN_INTERVAL_S = 2.0
CACHE_S = 600.0
CACHE_PAGES = 32
CACHE_FILES = 4
TIMEOUT = httpx.Timeout(15.0, connect=10.0)
REQUEST_DEADLINE_S = 30.0  # one request, body included: a trickling server can't hold the call
MAX_REDIRECTS = 3
BODY_CHARS = 20_000
TITLE_CHARS = 300
ALT_CHARS = 200
MAX_ATTACHMENTS = 30
MAX_LISTED_IMAGES = 20
MAX_IMAGE_TRIES = 8  # image requests one call may make while looking for images to show
MAX_NODES = 200_000
MAX_DEPTH = 1_000

WWW = "www.kw.ac.kr"
AICON = "aicon.kw.ac.kr"
WIX_FILES = "static.wixstatic.com"
# The kw-campus collectors' boards (kwcampus.deptboards.BOARDS): key -> (name, host, list page, group).
# Group A posts are ?BoardMode=view&UID=<n>, group B ?admin_mode=read&no=<n>. A kw-campus test keeps
# this table equal to the collectors' own.
DEPT_BOARDS: dict[str, tuple[str, str, str, str]] = {
    "ei": ("전자정보공과대학", "ei.kw.ac.kr", "/community/notice.php", "A"),
    "ee": ("전자공학과", "ee.kw.ac.kr", "/HTML/department/undergrad_info.php", "A"),
    "elcomm": ("전자통신공학과", "elcomm.kw.ac.kr", "/department/office_notice.php", "A"),
    "radiowave": ("전자융합공학과", "radiowave.kw.ac.kr", "/community/s_notice.php", "A"),
    "electric": ("전기공학과", "electric.kw.ac.kr", "/community/s_notice.php", "A"),
    "snme": ("전자재료공학과", "snme.kw.ac.kr", "/college/college_notice.php", "A"),
    "semicon": ("반도체시스템공학부", "semicon.kw.ac.kr", "/HTML/community/notice.php", "A"),
    "law": ("법학부", "law.kw.ac.kr", "/bulletin/notice.php", "A"),
    "archi": ("건축공학과", "archi.kw.ac.kr", "/community/notice.php", "A"),
    "chss": ("인문사회과학대학", "chss.kw.ac.kr", "/notice/news.php", "A"),
    "korean": ("국어국문학과", "korean.kw.ac.kr", "/community/notice.php", "A"),
    "english": ("영어산업학과", "english.kw.ac.kr", "/new/bulletin/notice.php", "A"),
    "psy": ("산업심리학과", "psy.kw.ac.kr", "/community/notice.php", "A"),
    "dnaci": ("동북아문화산업학부", "dnaci.kw.ac.kr", "/notice/news.php", "A"),
    "kwpa": ("행정학과", "kwpa.kw.ac.kr", "/notice/faculty.php", "A"),
    "biz": ("경영대학", "biz.kw.ac.kr", "/community/notice.php", "A"),
    "kwlife": ("참빛인재대학", "kwlife.kw.ac.kr", "/notice/notice.php", "A"),
    "kwlaw": ("금융부동산법무학과", "kwlaw.kw.ac.kr", "/notice/notice.php", "A"),
    "kwgame": ("게임콘텐츠학과", "kwgame.kw.ac.kr", "/notice/notice.php", "A"),
    "kwsports": ("스포츠상담재활학과", "kwsports.kw.ac.kr", "/notice/notice.php", "A"),
    "ingenium": ("인제니움학부대학", "ingenium.kw.ac.kr", "/inform/notice.php", "A"),
    "chemng": ("화학공학과", "chemng.kw.ac.kr", "/community/notice.php", "B"),
    "sports": ("스포츠융합과학과", "sports.kw.ac.kr", "/community/notice.php", "B"),
    "electricjob": ("전기공학과", "electric.kw.ac.kr", "/autonomy_active/employment_field.php", "A"),
    "career": ("경력개발팀", "job.kw.ac.kr", "/community/notice.php", "A"),
    "startup": ("창업지원단", "startup.kw.ac.kr", "/communication/notice.php", "A"),
    "kwiie": ("한국어교육센터", "kwiie.kw.ac.kr", "/community/notice.php", "A"),
    "humanrights": ("인권센터", "humanrights.kw.ac.kr", "/community/notice.php", "A"),
    "oia": ("국제처 유학생", "oia.kw.ac.kr", "/campus/notice.php", "A"),
    "grad": ("일반대학원", "grad.kw.ac.kr", "/notice/news.php", "A"),
    "liberal": ("자율전공학부", "liberal.kw.ac.kr", "/bulletin/notice.php", "A"),
    "semi": ("반도체특성화대학사업단", "semi.kw.ac.kr", "/communication/notice.php", "A"),
    "huss": ("HUSS 사업단", "huss.kw.ac.kr", "/bulletin/notice.php", "A"),
    "inno": ("대학혁신사업단", "inno.kw.ac.kr", "/bulletin/notice.php", "A"),
}
# kwcampus.wixfeeds.FEEDS: key -> (name, host). Their post ids are Wix ids, not part of a URL.
WIX_SITES: dict[str, tuple[str, str]] = {
    "architecture": ("건축학과", "www.kwuarchitecture.com"),
    "media": ("미디어커뮤니케이션학부", "www.kwmedia.info"),
}
# www's boards (kw-notice is the main notice board; kwcampus.wwwboards has the other two).
WWW_BOARDS = {"kw-notice": "/ko/life/notice.jsp", "kw-job": "/ko/life/job.jsp", "kw-faq": "/ko/life/faq.jsp"}
# kwcampus.smallboards' gnuboard boards: key -> (name, host, bo_table). Post ids "<key>-<wr_id>". On such a
# host only /bbs/board.php?bo_table=<a listed table>&wr_id=<n> is read as a page, and only images under
# /data/editor/ and /data/file/ as assets: gnuboard's download.php serves a file only inside the session that
# viewed the post (we keep no cookies), so attachments there are named in a note, never requested.
GNU_BOARDS: dict[str, tuple[str, str, str]] = {
    "alumni": ("총동문회", "www.kwuaa.com", "notice"),
}
GNU_TABLES: dict[str, frozenset[str]] = {
    host: frozenset(t for _, h, t in GNU_BOARDS.values() if h == host) for _, host, _ in GNU_BOARDS.values()}
_GNU_IMAGE = re.compile(r"/data/(?:editor|file)/[\w./-]+\.(?:jpe?g|png|gif|webp)", re.IGNORECASE)

DEPARTMENT_OF_HOST = {
    AICON: "인공지능융합대학",
    **{host: name for name, host, _, _ in DEPT_BOARDS.values()},
    **{host: name for name, host in WIX_SITES.values()},
    **{host: name for name, host, _ in GNU_BOARDS.values()},
}
PAGE_HOSTS = frozenset({WWW, *DEPARTMENT_OF_HOST})
ASSET_HOSTS = PAGE_HOSTS | {WIX_FILES}
# Hosts whose robots.txt asks for more than the rest. job.kw.ac.kr (경력개발팀, robots.txt checked
# 2026-11-07): Crawl-delay 10, Disallow /recommend/ and /job/. Its pages are read only from the notice
# board; files and images the page links to may be on other paths of the host, but not the disallowed ones.
HOST_INTERVAL_S = {"job.kw.ac.kr": 10.0}
HOST_PAGE_PATHS = {"job.kw.ac.kr": ("/community/notice.php",)}
HOST_DISALLOWED = {"job.kw.ac.kr": ("/recommend/", "/job/")}

_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
                   "source", "track", "wbr"})
_DATE = re.compile(r"(20\d{2})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")
_FILE_EXT = re.compile(r"\.(pdf|hwp|hwpx|docx?|xlsx?|pptx?|zip|txt|csv|ipynb|jpe?g|png|gif)\s*$", re.IGNORECASE)
_FILE_HREF = re.compile(r"download|filedown|file_down|fileDown|attach|/files?/|\.(pdf|hwpx?|docx?|xlsx?|pptx?|zip)(\?|$)",
                        re.IGNORECASE)
# Images that are page furniture, not content: board icons, buttons, spacers, counters.
_DECORATIVE = re.compile(r"/board/img/|/images?/(common|icon|btn)|icon|/ico_|ico-|btn_|bullet|blank\.gif|spacer|"
                         r"pixel|counter|loading|emoticon", re.IGNORECASE)
_MIN_SIDE_PX = 16  # a side below this is a line or a tracking pixel
_ICON_PX = 80  # both sides below this: an icon
_BODY_CLASSES = ("view_con", "view_content", "view-content", "view_cont", "board_view_con", "board-view-con",
                 "bbs_view_con", "view_txt", "viewContent", "board_content", "bbs_content", "post-content", "fr-view",
                 "board_view", "board-view", "bbs_view", "bbs-view", "view_box", "viewBox")
_TITLE_CLASSES = ("view_title", "view-title", "board_title", "bbs_title", "subject", "title", "tit", "post-title")


class NoticeError(Exception):
    """Why the notice can't be read; str() is a Korean sentence for the model."""


class Refused(NoticeError):
    """A gate refused the request (robots record, daily cap). `reason` is a short code the caller may set
    ("budget", "time", "off_host", "resting"); "refused" when it gave none."""

    def __init__(self, message: str = "", reason: str = "refused") -> None:
        super().__init__(message)
        self.reason = reason


class TooLarge(NoticeError):
    pass


class Gate(Protocol):
    async def before(self, url: str) -> None:
        """Wait until `url` may be requested, or raise Refused."""


class Pacer:
    """At most one request per host every `interval` seconds in this process (longer for a host in
    `host_intervals`, the robots.txt Crawl-delay). Each caller books the next free slot before it
    waits, so requests to one host go out in turn, that interval apart."""

    def __init__(self, interval: float = MIN_INTERVAL_S, clock=time.monotonic, sleep=asyncio.sleep,
                 host_intervals: dict[str, float] | None = None) -> None:
        self.interval, self._clock, self._sleep = interval, clock, sleep
        self.host_intervals = HOST_INTERVAL_S if host_intervals is None else host_intervals
        self._next: dict[str, float] = {}

    async def before(self, url: str) -> None:
        host = (urlsplit(url).hostname or "").lower()
        now = self._clock()
        slot = max(now, self._next.get(host, 0.0))
        self._next[host] = slot + max(self.interval, self.host_intervals.get(host, 0.0))
        if slot > now:
            await self._sleep(slot - now)


PACER = Pacer()


@dataclass(frozen=True)
class Limits:
    page_bytes: int = 4 * MIB  # a Wix post page is about 1.3 MB
    file_bytes: int = MAX_DOWNLOAD_BYTES  # the same cap as KLAS attachments
    image_bytes: int = 1536 * 1024
    images_total: int = 4 * MIB
    max_images: int = 4
    deadline_s: float | None = None  # the whole call; None on the PC


PC_LIMITS = Limits()


@dataclass
class Picture:
    index: int
    url: str
    mime: str
    data: bytes


@dataclass
class Answer:
    data: dict
    pictures: list[Picture] = field(default_factory=list)

    def content(self) -> list[TextContent | ImageContent]:
        """The answer as MCP content: the JSON text first, then each image after a line naming it."""
        blocks: list[TextContent | ImageContent] = [
            TextContent(type="text", text=json.dumps(scrub(self.data), ensure_ascii=False, indent=2))]
        for p in self.pictures:
            blocks.append(TextContent(type="text", text=f"이미지 {p.index}: {p.url}"))
            blocks.append(ImageContent(type="image", data=base64.b64encode(p.data).decode("ascii"), mime_type=p.mime))
        return blocks


# --- addresses ---------------------------------------------------------------------------------

def _off_list(host: str) -> NoticeError:
    return NoticeError(f"광운대 공지 사이트(www.kw.ac.kr, 학과·단과대 게시판, 건축학과·미디어커뮤니케이션학부·총동문회 사이트) 주소만 "
                       f"읽습니다({host or '주소 없음'}). school_notices·my_notices 결과의 url을 주세요.")


def check_url(url: str, *, asset: bool = False) -> str:
    """The https URL to request (fragment dropped) when its host is allowed; NoticeError otherwise.
    asset=True also allows Wix's file host, for images and files a page links to."""
    raw = (url or "").strip()
    if not raw:
        raise NoticeError("읽을 공지의 url(또는 post_id)을 주세요.")
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError:
        raise NoticeError("주소 형식이 잘못됐습니다.") from None
    host = (parts.hostname or "").lower().rstrip(".")
    if (parts.scheme.lower() not in ("http", "https") or parts.username is not None or parts.password is not None
            or port not in (None, 80, 443) or host not in (ASSET_HOSTS if asset else PAGE_HOSTS)):
        raise _off_list(host)
    path = parts.path or "/"
    # Compare the path as the server will read it: %-escapes decoded, case folded, '..' not allowed.
    plain = unquote(path).lower()
    if host in HOST_DISALLOWED and (".." in plain or any(plain.startswith(p) for p in HOST_DISALLOWED[host])):
        raise NoticeError(f"{host}의 이 경로는 사이트가 읽지 말라고 해서 읽지 않아요.")
    if not asset and host in HOST_PAGE_PATHS and plain not in HOST_PAGE_PATHS[host]:
        raise NoticeError(f"{host}에서는 공지 게시판({', '.join(HOST_PAGE_PATHS[host])}) 글만 읽어요.")
    if host in GNU_TABLES and not _gnu_allowed(host, plain, parts.query, asset):
        raise NoticeError(f"{host}에서는 공지 글과 글 속 이미지만 읽어요. 첨부 파일은 사이트에서 직접 받아 주세요.")
    return urlunsplit(("https", host, path, parts.query, ""))


def _gnu_allowed(host: str, plain: str, query: str, asset: bool) -> bool:
    """A gnuboard host: a post of a listed board as a page; an editor or board image as an asset."""
    if asset:  # an image file: no script anywhere on the way, nothing after its extension
        return (not query and ".." not in plain and ".php" not in plain and "/" not in plain[plain.rfind(".") + 1:]
                and _GNU_IMAGE.fullmatch(plain) is not None)
    fields = parse_qs(query, keep_blank_values=True)
    return (plain == "/bbs/board.php" and sorted(fields) == ["bo_table", "wr_id"]
            and all(len(v) == 1 for v in fields.values()) and fields["bo_table"][0] in GNU_TABLES[host]
            and re.fullmatch(r"\d{1,12}", fields["wr_id"][0]) is not None)


def url_for_post_id(post_id: str) -> str:
    """A notice's URL from its post_id in the school notice results: "12345" (main board), "kw-job-…",
    "kw-faq-…", "aicon-…", "dept-<board>-…", "alumni-…". Wix posts have no URL in their id."""
    pid = (post_id or "").strip()
    if re.fullmatch(r"\d{1,12}", pid):
        return f"https://{WWW}{WWW_BOARDS['kw-notice']}?BoardMode=view&DUID={pid}"
    if m := re.fullmatch(r"(kw-job|kw-faq)-(\d{1,12})", pid):
        return f"https://{WWW}{WWW_BOARDS[m.group(1)]}?BoardMode=view&DUID={m.group(2)}"
    if m := re.fullmatch(r"aicon-(\d{1,12})", pid):
        return f"https://{AICON}/administration/notice.php?admin_mode=read&no={m.group(1)}"
    if (m := re.fullmatch(r"dept-([a-z]+)-(\d{1,12})", pid)) and m.group(1) in DEPT_BOARDS:
        _, host, path, group = DEPT_BOARDS[m.group(1)]
        query = f"BoardMode=view&UID={m.group(2)}" if group == "A" else f"admin_mode=read&no={m.group(2)}"
        return f"https://{host}{path}?{query}"
    if (m := re.fullmatch(r"([a-z]+)-(\d{1,12})", pid)) and m.group(1) in GNU_BOARDS:
        _, host, table = GNU_BOARDS[m.group(1)]
        return f"https://{host}/bbs/board.php?bo_table={table}&wr_id={m.group(2)}"
    if (m := re.fullmatch(r"dept-([a-z]+)-[0-9a-f]{24}", pid)) and m.group(1) in WIX_SITES:
        raise NoticeError("이 글은 post_id로 주소를 알 수 없습니다. 공지 결과의 url을 주세요.")
    raise NoticeError(f"알 수 없는 post_id입니다({pid[:40]}). 공지 결과의 url을 주세요.")


# --- fetching ----------------------------------------------------------------------------------

@dataclass
class _Response:
    url: str
    content_type: str
    charset: str | None
    disposition: str
    body: bytes


def _status_message(status: int) -> str:
    if status in (404, 410):
        return f"글을 찾지 못했습니다(HTTP {status}). 지워졌거나 주소가 바뀌었을 수 있습니다."
    if status in (401, 403):
        return f"학교 사이트가 이 글을 보여 주지 않았습니다(HTTP {status}). 로그인이 필요하거나 막힌 글일 수 있습니다."
    if status == 429:
        return "학교 사이트가 요청이 많다며 잠시 거절했습니다(HTTP 429). 조금 뒤 다시 시도하세요."
    if status >= 500:
        return f"학교 사이트에 오류가 났습니다(HTTP {status}). 조금 뒤 다시 시도하세요."
    return f"학교 사이트가 요청을 거절했습니다(HTTP {status})."


class _Fetcher:
    def __init__(self, client: httpx.AsyncClient, gate: Gate, deadline: float | None) -> None:
        self.client, self.gate, self.deadline = client, gate, deadline

    def left(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - time.monotonic()

    async def get(self, url: str, *, asset: bool, cap: int, referer: str | None = None) -> _Response:
        for _ in range(MAX_REDIRECTS + 1):
            if self.left() <= 1:
                raise NoticeError("시간이 부족해 학교 사이트에 요청하지 않았습니다. 다시 시도하세요.")
            await self.gate.before(url)
            headers = {"Referer": referer} if referer else {}
            try:
                async with asyncio.timeout(min(REQUEST_DEADLINE_S, self.left())):
                    async with self.client.stream("GET", url, headers=headers) as r:
                        self.client.cookies.clear()  # no cookies, as with the collectors
                        if r.status_code in (301, 302, 303, 307, 308):
                            url = self._next_hop(url, r.headers.get("location"), asset)
                            continue
                        if r.status_code != 200:
                            raise NoticeError(_status_message(r.status_code))
                        length = r.headers.get("content-length", "")
                        if length.isdigit() and int(length) > cap:
                            raise TooLarge(str(int(length)))
                        chunks, total = [], 0
                        async for chunk in r.aiter_bytes():
                            total += len(chunk)
                            if total > cap:
                                raise TooLarge(str(total))
                            chunks.append(chunk)
                        mime = r.headers.get("content-type", "")
                        charset = re.search(r"charset=[\"']?([\w.:-]+)", mime, re.IGNORECASE)
                        return _Response(url, mime.split(";")[0].strip().lower(), charset and charset.group(1),
                                         r.headers.get("content-disposition", ""), b"".join(chunks))
            except TimeoutError:
                raise NoticeError("학교 사이트가 제때 답하지 않았습니다. 조금 뒤 다시 시도하세요.") from None
            except httpx.HTTPError as e:
                raise NoticeError(f"학교 사이트에 연결하지 못했습니다({e.__class__.__name__}).") from None
        raise NoticeError("다른 주소로 너무 여러 번 넘겨져 읽지 않았습니다.")

    @staticmethod
    def _next_hop(url: str, location: str | None, asset: bool) -> str:
        if not location:
            raise NoticeError("학교 사이트가 빈 주소로 넘기려 해 읽지 않았습니다.")
        target = urljoin(url, location.strip())
        try:
            return check_url(target, asset=asset)
        except NoticeError:
            host = urlsplit(target).hostname or target[:60]
            raise NoticeError(f"학교 사이트가 허용 목록 밖의 주소({host})로 넘기려 해 따라가지 않았습니다.") from None


# --- a small DOM ---------------------------------------------------------------------------------

class _Node:
    __slots__ = ("attrs", "children", "end", "outer_end", "outer_start", "parent", "start", "tag")

    def __init__(self, tag: str, attrs: dict[str, str], parent: _Node | None, outer_start: int, start: int) -> None:
        self.tag, self.attrs, self.parent, self.children = tag, attrs, parent, []
        self.outer_start, self.start = outer_start, start  # the "<" of the start tag, just after it
        self.end = self.outer_end = start  # the end tag's "<", just after it (empty until closed)

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def inside(self, other: _Node) -> bool:
        return other.outer_start <= self.outer_start and self.outer_end <= other.outer_end


class _Tree(HTMLParser):
    """Nodes with their offsets in the page, so a node's text is html_to_text of its own slice."""

    def __init__(self, raw: str) -> None:
        super().__init__(convert_charrefs=True)
        self.raw = raw
        self._lines = [0, *(m.end() for m in re.finditer("\n", raw))]
        self.root = _Node("#root", {}, None, 0, 0)
        self.root.end = self.root.outer_end = len(raw)
        self._stack = [self.root]
        self._count = 0

    def _at(self) -> int:
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def _add(self, tag: str, attrs: list[tuple[str, str | None]], push: bool) -> None:
        if self._count >= MAX_NODES:
            return
        self._count += 1
        at = self._at()
        node = _Node(tag, {k: v or "" for k, v in attrs}, self._stack[-1], at, at + len(self.get_starttag_text() or ""))
        node.end = node.outer_end = node.start
        self._stack[-1].children.append(node)
        if push and tag not in _VOID and len(self._stack) < MAX_DEPTH:
            self._stack.append(node)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._add(tag, attrs, push=True)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._add(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                at = self._at()
                close = self.raw.find(">", at)
                close = len(self.raw) if close < 0 else close + 1
                for node in self._stack[i + 1:]:  # left open inside it: closed here too
                    node.end = node.outer_end = at
                self._stack[i].end, self._stack[i].outer_end = at, close
                del self._stack[i:]
                return

    def close(self) -> None:
        super().close()
        for node in self._stack[1:]:
            node.end = node.outer_end = len(self.raw)
        del self._stack[1:]


def _walk(node: _Node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        stack.extend(reversed(n.children))


def _find(node: _Node | None, tag: str | None = None, cls: str | None = None, pred=None) -> _Node | None:
    return next(iter(_find_all(node, tag, cls, pred)), None)


def _find_all(node: _Node | None, tag: str | None = None, cls: str | None = None, pred=None) -> list[_Node]:
    if node is None:
        return []
    return [n for n in _walk(node) if n is not node and (tag is None or n.tag == tag)
            and (cls is None or n.has_class(cls)) and (pred is None or pred(n))]


def _text(raw: str, node: _Node | None, skip: tuple[_Node | None, ...] = (), limit: int = BODY_CHARS) -> str:
    if node is None:
        return ""
    pieces, pos = [], node.start
    for s in sorted((s for s in skip if s is not None and s.inside(node) and s is not node), key=lambda s: s.outer_start):
        if s.outer_start >= pos:
            pieces.append(raw[pos:s.outer_start])
            pos = s.outer_end
    pieces.append(raw[pos:node.end])
    return html_to_text("".join(pieces), limit=limit)


def _line(raw: str, node: _Node | None, skip: tuple[_Node | None, ...] = (), limit: int = TITLE_CHARS) -> str:
    return " ".join(_text(raw, node, skip, limit=4 * limit).split())[:limit]


def _date(text: str) -> str | None:
    m = _DATE.search(text or "")
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return f"{year:04d}-{month:02d}-{day:02d}" if 1 <= month <= 12 and 1 <= day <= 31 else None


# --- page templates ------------------------------------------------------------------------------

@dataclass
class _Parsed:
    title: str
    body: _Node | None
    files: _Node | None  # where the attachment links are
    date: str | None = None
    updated: str | None = None
    department: str | None = None
    category: str | None = None
    generic: bool = False  # found by the generic search: only links that look like files are attachments
    skip: tuple[_Node, ...] = ()  # left out of the body text (a whole page's header, menus, footer)
    pictures: _Node | None = None  # images shown apart from the body (gnuboard's attached images), listed first
    site_files: int = 0  # files the site serves only to a browser session that opened the post: not listed


def _jwxe(raw: str, root: _Node) -> _Parsed | None:
    """www.kw.ac.kr: li.title (strong.category, the title, span.ico-new), p.info "조회수 | 작성일 | 수정일 | 부서",
    li.attachment, li.contents."""
    box = _find(root, "div", "board-view-box")
    if box is None:
        return None
    head = _find(box, "p", "title") or _find(box, cls="title")
    category = _find(head, "strong", "category")
    marks = tuple(_find_all(head, "span", pred=lambda n: any(c.startswith("ico") for c in n.attrs.get("class", "").split())))
    parsed = _Parsed(_line(raw, head, (category, *marks)), _find(box, "li", "contents") or _find(box, cls="contents"),
                     _find(box, "li", "attachment") or _find(box, cls="attachment"),
                     category=_line(raw, category).strip("[] ") or None)
    for part in _line(raw, _find(box, "p", "info"), limit=500).split("|"):
        part = part.strip()
        if part.startswith("작성일"):
            parsed.date = _date(part)
        elif part.startswith("수정일"):
            parsed.updated = _date(part)
        elif part and not part.startswith("조회"):
            parsed.department = part[:100]
    return parsed


def _boardmode(raw: str, root: _Node) -> _Parsed | None:
    """The BoardMode department boards: div.view_top (h3 title; writer, date, hits), div.view_file, div.view_con.
    The writer is left out: it is a person's name on some boards."""
    top, body = _find(root, "div", "view_top"), _find(root, "div", "view_con")
    if top is None or body is None:
        return None
    heading = _find(top, pred=lambda n: n.tag in ("h2", "h3", "h4"))
    dates = [d for li in _find_all(top, "li") if (d := _date(_line(raw, li)))]
    return _Parsed(_line(raw, heading or top), body, _find(root, "div", "view_file"), date=dates[0] if dates else None)


def _board_view_table(raw: str, root: _Node) -> _Parsed | None:
    """aicon and the other admin_mode=read boards: table.board-view with th.subject, ul.table_view_list
    ("작 성 일 :", "첨부파일 :") and td.view_td."""
    table = _find(root, "table", "board-view")
    head, body = _find(table, "th", "subject"), _find(table, "td", "view_td")
    if head is None or body is None:
        return None
    facts = _find(table, "ul", "table_view_list")
    rows = [(li, _line(raw, li, limit=500)) for li in _find_all(facts, "li")]
    when = next((_date(t) for _, t in rows if "작" in t and "일" in t and _date(t)), None) or _date(_line(raw, facts, limit=500))
    files = next((li for li, t in rows if "첨부" in t), None) or facts
    return _Parsed(_line(raw, head), body, files, date=when)


_GNU_DATE = re.compile(r"(?<!\d)(\d{2}|\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")


def _gnuboard(raw: str, root: _Node) -> _Parsed | None:
    """gnuboard 5 posts: article#bo_v with the title in its header (span.bo_v_tit in the basic skin), the
    date in strong.if_date ("26-08-28 14:06"), images attached to the post in #bo_v_img, the body in #bo_v_con.
    The files in section#bo_v_file come from download.php, which needs the session that viewed the post: they
    are counted for a note, not listed. The writer is left out."""
    article = _find(root, "article", pred=lambda n: n.attrs.get("id") == "bo_v")
    body = _find(article, pred=lambda n: n.attrs.get("id") == "bo_v_con")
    if article is None or body is None:
        return None
    head = _find(article, cls="bo_v_tit") or _find(_find(article, "header"), pred=lambda n: n.tag in ("h1", "h2", "h3"))
    when, date = _GNU_DATE.search(_line(raw, _find(article, "strong", "if_date"))), None
    if when:
        year, month, day = int(when.group(1)), int(when.group(2)), int(when.group(3))
        date = f"{year + 2000 if year < 100 else year:04d}-{month:02d}-{day:02d}" if 1 <= month <= 12 and 1 <= day <= 31 else None
    files = _find(article, pred=lambda n: n.attrs.get("id") == "bo_v_file")
    return _Parsed(_line(raw, head), body, None, date=date,
                   pictures=_find(article, pred=lambda n: n.attrs.get("id") == "bo_v_img"),
                   site_files=len(_find_all(files, "a", pred=lambda n: "download" in n.attrs.get("href", ""))))


def _meta(root: _Node, prop: str) -> str:
    node = _find(root, "meta", pred=lambda n: n.attrs.get("property") == prop or n.attrs.get("name") == prop)
    return (node.attrs.get("content", "") if node else "").strip()


def _generic(raw: str, root: _Node) -> _Parsed:
    """Any other page: the first known body container (board engines, Wix's post content), else
    <article>, <main>, #content, the page body. Title near it, else og:title or <title>."""
    body = (_find(root, pred=lambda n: n.attrs.get("data-hook") in ("post-description", "post-content"))
            or _find(root, pred=lambda n: n.attrs.get("id") in ("bo_v_con", "post-content", "contents_view"))
            or next((b for c in _BODY_CLASSES if (b := _find(root, cls=c))), None)
            or _find(root, "article") or _find(root, "main")
            or _find(root, pred=lambda n: n.attrs.get("id") in ("content", "contents", "container"))
            or _find(root, "body") or root)
    whole = body.tag in ("body", "#root")
    area = body
    for _ in range(0 if whole else 3):  # the title, date and file list sit next to the body, a few levels up
        if area.parent is None or area.parent.tag in ("html", "#root"):
            break
        area = area.parent

    def marked(n: _Node) -> bool:
        return n.attrs.get("data-hook") == "post-title" or any(n.has_class(c) for c in _TITLE_CLASSES)

    # The title is the last heading or title box before the body: a board's own name ("공지사항") comes
    # earlier, and a heading inside a title box comes after the box.
    before = [] if area is body else _find_all(area, pred=lambda n: n.outer_start < body.outer_start
                                                and not body.inside(n)
                                                and n.tag not in ("meta", "img", "a", "script", "style", "li")
                                                and (marked(n) or n.tag in ("h1", "h2", "h3", "h4")))
    heading = next((n for n in reversed(before) if _line(raw, n)), None)
    title = _line(raw, heading) if heading else ""
    if not title:
        title = _meta(root, "og:title") or _line(raw, _find(root, "title"))
    published = _date(_meta(root, "article:published_time"))
    if published is None and area is not body:
        published = _date(_text(raw, area, (body,), limit=2000))
    chrome = tuple(_find_all(body, pred=lambda n: n.tag in ("header", "nav", "footer", "aside", "form"))) if whole else ()
    return _Parsed(clean(title)[:TITLE_CHARS], body, area, date=published, generic=True, skip=chrome)


def _decode(data: bytes, charset: str | None) -> str:
    """Header charset, else the page's meta charset (EUC-KR boards say so there), else UTF-8 or CP949."""
    if not charset:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w.:-]+)", data[:4096], re.IGNORECASE)
        charset = m.group(1).decode("ascii", "ignore") if m else None
    if charset:
        name = charset.lower().replace("_", "-")
        if name in ("euc-kr", "euckr", "ks-c-5601-1987", "ksc5601", "x-windows-949", "windows-949"):
            name = "cp949"
        try:
            return data.decode(name, "replace")  # elcomm's UTF-8 pages carry stray EUC-KR bytes
        except LookupError:
            pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp949", "replace")


@dataclass
class _Page:
    url: str
    title: str
    date: str | None
    updated: str | None
    department: str | None
    category: str | None
    body: str
    attachments: list[tuple[str, str]]  # (name, url)
    images: list[tuple[str, str | None]]  # (url, alt)
    at: float = 0.0
    site_files: int = 0  # attachments only the site itself hands out (gnuboard): named in a note


def _wix_image(url: str) -> str:
    """Wix pages first show a small blurred copy (…/v1/fill/w_147,h_83,…,blur_2,…/x.jpg); ask for the
    same image at up to 1568 px, unblurred."""
    m = re.match(r"(https://static\.wixstatic\.com/media/[^/]+/v1/\w+/)([^/]+)(/.+)$", url)
    if not m:
        return url
    params = [p for p in m.group(2).split(",") if not p.startswith("blur_")]
    sizes = {p[:2]: int(p[2:]) for p in params if re.fullmatch(r"[wh]_\d{1,5}", p)}
    if "w_" in sizes and "h_" in sizes and max(sizes.values()) > 0:
        scale = 1568 / max(sizes.values())
        params = [f"{p[:2]}{max(1, round(sizes[p[:2]] * scale))}" if p[:2] in sizes and re.fullmatch(r"[wh]_\d{1,5}", p)
                  else p for p in params]
    return m.group(1) + ",".join(params) + m.group(3)


def _decorative(img: _Node, src: str) -> bool:
    sizes = []
    for key in ("width", "height"):
        m = re.match(r"\s*(\d{1,5})(px)?\s*$", img.attrs.get(key, ""))
        if m:
            sizes.append(int(m.group(1)))
    style = img.attrs.get("style", "")
    for key in ("width", "height"):
        if m := re.search(rf"(?<![-\w]){key}\s*:\s*(\d{{1,5}})px", style):
            sizes.append(int(m.group(1)))
    return bool(sizes and min(sizes) < _MIN_SIDE_PX) or (len(sizes) >= 2 and max(sizes) < _ICON_PX) \
        or bool(_DECORATIVE.search(urlsplit(src).path))


def _links(raw: str, page_url: str, parsed: _Parsed) -> tuple[list[tuple[str, str]], list[tuple[str, str | None]]]:
    """(attachments as (name, url), body images as (url, alt)): allowed hosts only, page furniture left out."""
    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in _find_all(parsed.files, "a"):
        href = a.attrs.get("href", "").strip()
        if not href or href.lower().startswith(("javascript:", "mailto:", "#")):
            continue
        icons = tuple(_find_all(a, "span", pred=lambda n: any("ico" in c for c in n.attrs.get("class", "").split())))
        name = clean(_line(raw, a, icons, limit=200)).strip()
        if parsed.generic and not (_FILE_HREF.search(href) or _FILE_EXT.search(name)):
            continue  # a menu or a "목록" link, not a file
        try:
            target = check_url(urljoin(page_url, href), asset=True)
        except NoticeError:
            continue
        if target in seen or target == page_url:
            continue
        seen.add(target)
        files.append((name or f"첨부 {len(files) + 1}", target))
        if len(files) >= MAX_ATTACHMENTS:
            break
    images: list[tuple[str, str | None]] = []
    shown: set[str] = set()
    for img in [*_find_all(parsed.pictures, "img"), *_find_all(parsed.body, "img")]:
        src = next((img.attrs[k].strip() for k in ("src", "data-src", "data-original", "data-lazy-src")
                    if img.attrs.get(k, "").strip() and not img.attrs[k].strip().startswith("data:")), "")
        if not src:
            continue
        try:
            target = check_url(_wix_image(urljoin(page_url, src)), asset=True)
        except NoticeError:
            continue  # off the list (a tracker, another site): never requested
        if target in shown or _decorative(img, target):
            continue
        shown.add(target)
        alt = " ".join(clean(img.attrs.get("alt", "")).split())[:ALT_CHARS] or None
        images.append((target, alt))
        if len(images) >= MAX_LISTED_IMAGES:
            break
    return files, images


def parse_page(html: str, url: str) -> _Page:
    """The notice on one fetched page (url is where it came from, for links and the department)."""
    tree = _Tree(html)
    tree.feed(html)
    tree.close()
    raw, root = tree.raw, tree.root
    parsed = (_jwxe(raw, root) or _boardmode(raw, root) or _board_view_table(raw, root) or _gnuboard(raw, root)
              or _generic(raw, root))
    files, images = _links(raw, url, parsed)
    title = " ".join(clean(parsed.title).split())[:TITLE_CHARS]
    return _Page(url=url, title=title or "(제목 없음)", date=parsed.date,
                 updated=parsed.updated if parsed.updated != parsed.date else None,
                 department=parsed.department or DEPARTMENT_OF_HOST.get(urlsplit(url).hostname or "") or None,
                 category=parsed.category, body=_text(raw, parsed.body, parsed.skip, limit=BODY_CHARS),
                 attachments=files, images=images, site_files=parsed.site_files)


# --- images and files ----------------------------------------------------------------------------

def image_info(data: bytes) -> tuple[str, int, int] | None:
    """(mime, width, height) from the first bytes of a PNG, JPEG, GIF or WebP; None for anything else."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
            w, h = struct.unpack(">II", data[16:24])
            return "image/png", w, h
        if data[:6] in (b"GIF87a", b"GIF89a"):
            w, h = struct.unpack("<HH", data[6:10])
            return "image/gif", w, h
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            kind = data[12:16]
            if kind == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return "image/webp", w & 0x3FFF, h & 0x3FFF
            if kind == b"VP8L":
                bits = int.from_bytes(data[21:25], "little")
                return "image/webp", (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            if kind == b"VP8X":
                return "image/webp", int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
            return None
        if data[:3] == b"\xff\xd8\xff":
            i = 2
            while i + 9 < len(data) and i < 1_000_000:
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                    i += 1 if marker == 0xFF else 2
                    continue
                size = struct.unpack(">H", data[i + 2:i + 4])[0]
                if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return "image/jpeg", w, h
                i += 2 + size
            return "image/jpeg", 0, 0
    except struct.error:
        return None
    return None


def _tiny(width: int, height: int) -> bool:
    return (0 < width < _MIN_SIDE_PX or 0 < height < _MIN_SIDE_PX) or (0 < width < _ICON_PX and 0 < height < _ICON_PX)


def _filename(disposition: str) -> str:
    """The file name a Content-Disposition header gives (RFC 5987 or a plain, maybe UTF-8, name)."""
    if m := re.search(r"filename\*\s*=\s*[\w-]+'[^']*'([^;]+)", disposition, re.IGNORECASE):
        return unquote(m.group(1).strip().strip('"'))
    if m := re.search(r'filename\s*=\s*"?([^";]+)"?', disposition, re.IGNORECASE):
        name = unquote(m.group(1).strip())
        try:
            raw = name.encode("latin-1")
        except UnicodeEncodeError:
            return name
        for encoding in ("utf-8", "cp949"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
    return ""


def _guess_ext(data: bytes) -> str:
    """An extension from the file's first bytes, for a link whose name has none."""
    if data[:5] == b"%PDF-":
        return ".pdf"
    if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return ".hwp"
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()[:200]
        except zipfile.BadZipFile:
            return ""
        for prefix, ext in (("word/", ".docx"), ("ppt/", ".pptx"), ("xl/", ".xlsx"), ("Contents/", ".hwpx")):
            if any(n.startswith(prefix) for n in names):
                return ext
        return ".zip"
    return ""


# --- the call ------------------------------------------------------------------------------------

_PAGES: dict[str, _Page] = {}
_FILES: dict[str, tuple[float, str, str, int]] = {}  # url -> (when, kind, text, size)


def clear_cache() -> None:
    _PAGES.clear()
    _FILES.clear()


def _fresh(at: float) -> bool:
    return time.monotonic() - at < CACHE_S


async def _page(fetch: _Fetcher, url: str, limits: Limits) -> _Page:
    hit = _PAGES.get(url)
    if hit is not None and _fresh(hit.at):
        return hit
    try:
        r = await fetch.get(url, asset=False, cap=limits.page_bytes)
    except TooLarge:
        raise NoticeError(f"공지 페이지가 너무 커서({limits.page_bytes // MIB}MB 초과) 읽지 않았습니다. 링크를 직접 여세요: {url}") from None
    if r.content_type not in ("text/html", "application/xhtml+xml", ""):
        raise NoticeError(f"공지 페이지가 아니라 파일입니다({r.content_type}). 공지 주소를 주고, 첨부 파일은 attachment 번호로 읽으세요.")
    if not r.body.strip():
        raise NoticeError("학교 사이트가 빈 페이지를 보냈습니다. 조금 뒤 다시 시도하세요.")
    page = await asyncio.to_thread(parse_page, _decode(r.body, r.charset), r.url)
    page.at = time.monotonic()
    for old in [k for k, p in _PAGES.items() if not _fresh(p.at)]:
        del _PAGES[old]
    while len(_PAGES) >= CACHE_PAGES:
        del _PAGES[min(_PAGES, key=lambda k: _PAGES[k].at)]
    _PAGES[url] = page
    return page


def _summary(page: _Page) -> dict:
    data: dict = {"title": page.title, "date": page.date}
    if page.updated:
        data["updated"] = page.updated
    data["department"] = page.department
    if page.category:
        data["category"] = page.category
    data["body"] = untrusted(page.body)
    data["attachments"] = [{"index": i, "name": name, "url": url} for i, (name, url) in enumerate(page.attachments, 1)]
    data["images"] = [{"index": i, "url": url, "alt": alt} for i, (url, alt) in enumerate(page.images, 1)]
    if page.site_files:
        data["files_on_site"] = page.site_files  # attachments only a browser that opened the post can download
    data["source_url"] = page.url
    return data


def _notes(data: dict, page: _Page, images: bool) -> list[str]:
    notes = []
    if len(page.body.strip()) < 80 and page.images and not images:
        notes.append(f"본문 글자가 거의 없고 이미지가 {len(page.images)}장 있습니다. images=true로 다시 읽으면 "
                     "포스터·표 그림을 볼 수 있습니다.")
    if page.attachments:
        notes.append("첨부 파일 내용은 attachment=번호로 읽으세요.")
    if page.site_files:
        notes.append(f"첨부 파일 {page.site_files}개는 사이트에서 글을 연 브라우저로만 받을 수 있어 읽지 않았습니다. "
                     "source_url을 직접 여세요.")
    if not page.body.strip() and not page.images and not page.attachments:
        notes.append("본문을 찾지 못했습니다. 사이트 형식이 바뀌었을 수 있으니 source_url을 직접 열어 보세요.")
    return notes


async def _show_images(fetch: _Fetcher, page: _Page, data: dict, limits: Limits) -> list[Picture]:
    pictures: list[Picture] = []
    total = tries = 0
    for row in data["images"]:
        if len(pictures) >= limits.max_images:
            break
        # "skip" is a short code next to the sentence: tries, time, too_large, error, not_image, icon,
        # total_size, or the gate's own reason (budget, time, off_host, resting, refused)
        if tries >= MAX_IMAGE_TRIES:
            row["skipped"], row["skip"] = "이번에는 더 요청하지 않음", "tries"
            continue
        if fetch.left() < 5:
            row["skipped"], row["skip"] = "시간이 부족해 건너뜀", "time"
            continue
        tries += 1
        try:
            r = await fetch.get(row["url"], asset=True, cap=limits.image_bytes, referer=page.url)
        except TooLarge:
            row["skipped"], row["skip"] = f"이미지가 너무 큼({limits.image_bytes / MIB:.1f}MB 초과)", "too_large"
            continue
        except Refused as e:  # the gate: robots, daily cap, no time to wait
            row["skipped"], row["skip"] = str(e), e.reason
            if e.reason == "done":  # the caller has this one already: no request went out, no try spent
                tries -= 1
            continue
        except NoticeError as e:  # 404, no answer
            row["skipped"], row["skip"] = str(e), "error"
            continue
        info = image_info(r.body)
        if info is None:
            row["skipped"], row["skip"] = "PNG·JPEG·GIF·WebP 이미지가 아님", "not_image"
            continue
        mime, width, height = info
        if _tiny(width, height):
            row["skipped"], row["skip"] = "아이콘이나 추적용으로 보이는 작은 이미지", "icon"
            continue
        if total + len(r.body) > limits.images_total:
            row["skipped"], row["skip"] = f"이미지 합계가 {limits.images_total / MIB:.0f}MB를 넘어 건너뜀", "total_size"
            continue
        total += len(r.body)
        row["shown"] = True
        pictures.append(Picture(row["index"], row["url"], mime, r.body))
    left = [r["index"] for r in data["images"] if not r.get("shown") and "skipped" not in r]
    if left:
        data["images_note"] = f"한 번에 {limits.max_images}장까지 보여 줍니다. 보이지 않은 이미지: {left}"
    return pictures


async def _attachment(fetch: _Fetcher, page: _Page, index: int, part: int, limits: Limits) -> Answer:
    if not page.attachments:
        if page.site_files:  # gnuboard's download.php: only for the session that opened the post
            raise NoticeError(f"이 글의 첨부 파일은 사이트에서 글을 연 브라우저로만 받을 수 있어 읽지 않습니다. "
                              f"링크를 직접 여세요: {page.url}")
        raise NoticeError("이 공지에는 첨부 파일이 없습니다.")
    names = ", ".join(f"{i}. {n}" for i, (n, _) in enumerate(page.attachments, 1))
    if not 1 <= index <= len(page.attachments):
        raise NoticeError(f"attachment는 1~{len(page.attachments)} 사이여야 합니다. 첨부 파일: {names}")
    name, url = page.attachments[index - 1]
    base = {"title": page.title, "source_url": page.url, "file": name}
    hit = _FILES.get(url)
    if hit is None or not _fresh(hit[0]):
        try:
            r = await fetch.get(url, asset=True, cap=limits.file_bytes, referer=page.url)
        except TooLarge:
            raise NoticeError(f"{name}: 파일이 너무 큽니다(최대 {limits.file_bytes // MIB}MB). 링크를 직접 여세요: {url}") from None
        info = image_info(r.body)
        if info is not None and not _tiny(info[1], info[2]):
            if len(r.body) > limits.image_bytes:
                raise NoticeError(f"{name}: 이미지가 너무 커서({limits.image_bytes / MIB:.1f}MB 초과) 보여 주지 못합니다. "
                                  f"링크를 직접 여세요: {url}")
            return Answer({**base, "kind": "이미지", "size_kb": round(len(r.body) / 1024),
                           "note": "이미지 파일이라 그림으로 보여 줍니다."}, [Picture(index, url, info[0], r.body)])
        if r.content_type in ("text/html", "application/xhtml+xml") and not re.search(r"\.html?$", name, re.IGNORECASE):
            raise NoticeError(f"{name}: 파일 대신 웹 페이지가 왔습니다(학교 사이트가 바로 내려받기를 막았을 수 있음). "
                              f"링크를 직접 여세요: {url}")
        fname = name if _FILE_EXT.search(name) else (_filename(r.disposition) or name)
        if not re.search(r"\.\w{1,5}$", fname):
            fname += _guess_ext(r.body)
        try:
            job = asyncio.to_thread(extract_text, fname, r.body)
            kind, text = await (job if fetch.deadline is None else asyncio.wait_for(job, max(fetch.left() - 1, 1)))
        except UnreadableAttachment as e:
            raise NoticeError(f"{name}: {e}") from None
        except TimeoutError:
            raise NoticeError(f"{name}: 파일을 읽는 데 시간이 너무 오래 걸려 멈췄습니다. 링크를 직접 여세요: {url}") from None
        hit = (time.monotonic(), kind, clean(text), len(r.body))
        for old in [k for k, v in _FILES.items() if not _fresh(v[0])]:
            del _FILES[old]
        while len(_FILES) >= CACHE_FILES:
            del _FILES[min(_FILES, key=lambda k: _FILES[k][0])]
        _FILES[url] = hit
    _, kind, text, size = hit
    chunk, total = split_parts(text, part)
    return Answer({**base, "kind": kind, "size_kb": round(size / 1024), "part": min(max(part, 1), total),
                   "total_parts": total, "text": untrusted(chunk) or ""})


async def read_notice(url: str, attachment: int | None = None, images: bool = False, part: int = 1, *,
                      limits: Limits = PC_LIMITS, gate: Gate | None = None,
                      transport: httpx.AsyncBaseTransport | None = None) -> Answer:
    """One notice: title, date, department, body (wrapped by text.untrusted), attachments [{index, name,
    url}], images [{index, url, alt}] and source_url. attachment=<index> reads that file's text instead
    (in parts of attachments.PART_CHARS, like get_attachment_text); images=True adds up to
    limits.max_images images as pictures. NoticeError (a Korean sentence) when it can't."""
    target = check_url(url)
    deadline = None if limits.deadline_s is None else time.monotonic() + limits.deadline_s
    async with httpx.AsyncClient(http2=False, follow_redirects=False, timeout=TIMEOUT, transport=transport,
                                 headers={"User-Agent": USER_AGENT, "Accept-Language": "ko"}) as client:
        fetch = _Fetcher(client, gate or PACER, deadline)
        page = await _page(fetch, target, limits)
        if attachment is not None:
            return await _attachment(fetch, page, int(attachment), int(part or 1), limits)
        data = _summary(page)
        pictures = await _show_images(fetch, page, data, limits) if images else []
    if notes := _notes(data, page, images):
        data["note"] = " ".join(notes)
    return Answer(data, pictures)
