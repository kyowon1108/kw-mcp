"""read_school_notice / kw_mcp.notices: one school notice in full.

The pages are synthetic, shaped like the real templates (www's jwxe board, a BoardMode department
board, aicon's board-view table, and generic agency/ingenium/Wix pages); titles and text are made
up and name nobody. No network: respx answers every request."""

import asyncio
import json
import struct
import zlib

import httpx
import pytest
import respx

from kw_mcp import klas, notices, server

WWW_URL = "https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=60001"
WWW_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>광운대학교</title></head><body>
<div id="header"><img src="/_res/ko/img/common/logo.png" alt="광운대학교"></div>
<div class="board-view-box"><ul>
 <li class="title"><p class="title"><strong class="category">[등록/장학]</strong> 2026학년도 테스트 장학생 선발 공고
   <span class="ico-new">New</span></p>
  <p class="info">조회수 12 | 작성일 2026.11.02 | 수정일 2026.11.03 | 학생복지팀</p></li>
 <li class="attachment">
  <p><a href="/include/Download.jsp?fuid=1&amp;ano=60001"><span class="ico-file">Attachment</span>선발 공고.pdf</a></p>
  <p><a href="/include/Download.jsp?fuid=2&amp;ano=60001"><span class="ico-file">Attachment</span>신청서.txt</a></p>
 </li>
 <li class="contents">
  <p><img src="/KWData/webeditor/2026/poster.png" alt="장학생 선발 포스터"></p>
  <p><img src="/KWData/webeditor/2026/pixel.gif" width="1" height="1"></p>
  <p><img src="https://tracker.example.net/t.gif" alt=""></p>
  <p>* 자세한 내용은 첨부 파일을 참조하시기 바랍니다.</p>
 </li>
</ul></div></body></html>"""

SNME_URL = "https://snme.kw.ac.kr/college/college_notice.php?BoardMode=view&UID=4800"
BOARDMODE_PAGE = """<html><head><meta charset="UTF-8"><title>광운대학교 전자재료공학과</title></head><body>
<div id="contentArea" class="list_view"><div class="btn_list top"><a class="listBtn">목록</a></div>
<!-- view_top --><div class="view_top"><h3><span>[공지]</span> 2027년도 테스트 연구실 배정 신청</h3>
<ul><li><span>관리자</span></li><li><span>2026-10-28</span></li><li class="hit"><span>63</span></li></ul></div>
<!-- file --><div class="view_file"><span><a href='/LIB/PHP_FUNC/Download.php?param=abc123'><img src='/Board/img/icon_download.png'> 신청서_양식.xlsx</a></span><br></div>
<div class="view_con"><p><span>안녕하세요. 학과 사무실입니다.</span></p>
<div class="view_con"><p>신청 기간: 2026.10.28 ~ 2026.11.04</p></div>
<p><img src="https://www.kw.ac.kr/KWData/webeditor/2026/table.jpg" alt="일정표"></p></div>
<div class="btn_relation"><p><span class="icon"><img src="/Board/img/list_prev.png" alt="이전" width="50"></span>
<a href="/college/college_notice.php?BoardMode=view&UID=4799">이전 글</a></p></div></div></body></html>"""

AICON_URL = "https://aicon.kw.ac.kr/administration/notice.php?admin_mode=read&no=3600"
AICON_PAGE = """<html><head><meta charset="UTF-8"><title>광운대학교 인공지능융합대학</title></head><body>
<div class="table_styleW mt30"><table class="board-view"><caption>상세</caption>
<thead><tr><th class="subject">[공지] 2026학년도 테스트 졸업작품 전시회 안내</th></tr></thead>
<tbody><tr><td><ul class="table_view_list">
<li class="ico01">작 성 자 : <span class="tt">관리자</span></li>
<li class="ico02">작 성 일 : <span class="tt">2026.11.06</span></li>
<li class="ico03">첨부파일 : <span class="tt"><a href='../lib/download.php?file_name=%EB%B0%B0%EC%B9%98%EB%8F%84.pdf&save_file=a_1.pdf&meta=free'>배치도.pdf</a></span></li>
</ul></td></tr>
<tr><td class="view_td"><p><b>졸업작품 전시회 안내</b></p><p>1. 일시 : 2026년 11월 12일(목) 9:00~17:00</p>
<table class="__se_tbl"><tr><td>09:00~10:00</td><td>작품설치</td></tr></table>
<p><img src="https://aicon.kw.ac.kr/webedit_naver/upload/261106/booth.png"></p></td></tr></tbody></table></div>
<div class="btn-tc tr"><a class="btnNormal" href="/administration/notice.php?page=">글 목록</a></div></body></html>"""

CHSS_URL = "https://chss.kw.ac.kr/notice/news.php?BoardMode=view&UID=210"
AGENCY_PAGE = """<html><head><meta charset="utf-8"><title>인문사회과학대학</title></head><body>
<div id="gnb"><a href="/">홈</a><a href="/notice/news.php">공지사항</a></div>
<div id="contents"><h3 class="page_title">공지사항</h3>
<div class="board_view"><div class="view_title"><h4>2026학년도 테스트 학생 설명회 안내</h4>
<p class="date">작성일 2026-11-02</p></div>
<div class="file"><a href="/Board/download.php?no=210&amp;file=1">신청서.hwp</a></div>
<div class="view_content"><p>설명회를 다음과 같이 엽니다.</p><img src="/upload/editor/notice.jpg" alt="안내"></div>
<a href="/notice/news.php?BoardMode=list">목록</a></div></div></body></html>"""

INGENIUM_URL = "https://ingenium.kw.ac.kr/inform/notice.php?BoardMode=view&UID=55"
INGENIUM_PAGE = """<html><head><meta charset="utf-8"><title>인제니움학부대학</title></head><body>
<div class="sub_content"><table class="bbs_view"><tr><th class="subject">테스트 교과목 수강 안내</th></tr>
<tr><td class="date">2026.06.15</td></tr>
<tr><td class="file"><a href="/bbs/download.php?idx=3">안내문.pdf</a> <a href="/inform/notice.php">목록</a></td></tr>
<tr><td class="bbs_content"><p>교과목 수강 방법을 안내합니다.</p></td></tr></table></div></body></html>"""

WIX_URL = "https://www.kwuarchitecture.com/post/test-exhibition"
WIX_PAGE = """<html><head><meta property="og:title" content="테스트 전시 안내">
<meta property="article:published_time" content="2026-09-16T03:00:00.000Z"></head><body>
<header id="SITE_HEADER"><img src="https://static.wixstatic.com/media/logo~mv2.png/v1/fill/w_60,h_60/logo.png"
 width="60" height="60"></header>
<article><h1 data-hook="post-title">테스트 전시 안내</h1><div data-hook="post-description"><p>졸업 전시를 엽니다.</p>
<img src="https://static.wixstatic.com/media/abc~mv2.jpg/v1/fill/w_147,h_83,al_c,q_80,blur_2,enc_auto/abc~mv2.jpg">
</div></article></body></html>"""

ENGLISH_URL = "https://english.kw.ac.kr/new/bulletin/notice.php?BoardMode=view&UID=77"
ENGLISH_PAGE = ("""<html><head><meta http-equiv="Content-Type" content="text/html; charset=euc-kr"></head><body>
<div class="view_title"><h4>테스트 특강 안내</h4></div><div class="view_content"><p>영어 특강을 엽니다.</p></div>
</body></html>""").encode("cp949")


def png(width: int, height: int, pad: int = 0) -> bytes:
    """A real PNG of that size (gray), `pad` bytes of an ancillary chunk added."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    extra = chunk(b"tEXt", b"pad\x00" + b"x" * pad) if pad else b""
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + extra + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def html(text: str | bytes, content_type: str = "text/html; charset=utf-8", headers: dict | None = None) -> httpx.Response:
    return httpx.Response(200, content=text.encode() if isinstance(text, str) else text,
                          headers={"Content-Type": content_type, **(headers or {})})


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """No pacing waits and an empty cache in every test (pacing has its own test)."""
    monkeypatch.setattr(notices, "PACER", notices.Pacer(interval=0))
    notices.clear_cache()
    yield
    notices.clear_cache()


def payload(answer: notices.Answer) -> dict:
    blocks = answer.content()
    return json.loads(blocks[0].text)


# --- addresses ---------------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    WWW_URL, SNME_URL, AICON_URL, CHSS_URL, INGENIUM_URL, WIX_URL, "https://www.kwmedia.info/post/x",
    "https://kwlife.kw.ac.kr/notice/notice.php?BoardMode=view&UID=1", "https://chemng.kw.ac.kr/community/notice.php?admin_mode=read&no=78",
])
def test_collector_hosts_are_allowed(url):
    assert notices.check_url(url) == url


def test_urls_are_normalized_to_https_without_fragment():
    assert notices.check_url("http://ee.kw.ac.kr/a.php?x=1#top") == "https://ee.kw.ac.kr/a.php?x=1"
    assert notices.check_url("www.kw.ac.kr/ko/life/notice.jsp") == "https://www.kw.ac.kr/ko/life/notice.jsp"
    assert notices.check_url("https://WWW.KW.AC.KR./x") == "https://www.kw.ac.kr/x"


@pytest.mark.parametrize("url", [
    "https://www.example.com/notice", "https://kw.ac.kr.evil.example/x", "https://share.kw.ac.kr/notice/news.php",
    "https://klas.kw.ac.kr/", "https://user:pw@www.kw.ac.kr/", "https://www.kw.ac.kr:8443/", "ftp://www.kw.ac.kr/",
    "file:///etc/passwd", "https://static.wixstatic.com/media/a.jpg", "https://ce.kw.ac.kr/department_office/lecture.php",
])
def test_other_hosts_are_refused(url):
    with pytest.raises(notices.NoticeError, match="광운대 공지 사이트"):
        notices.check_url(url)


def test_wix_file_host_only_for_images_and_files():
    assert notices.check_url("https://static.wixstatic.com/media/a.jpg", asset=True)


@pytest.mark.parametrize("post_id,url", [
    ("60001", "https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=60001"),
    ("kw-job-70001", "https://www.kw.ac.kr/ko/life/job.jsp?BoardMode=view&DUID=70001"),
    ("kw-faq-12", "https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=12"),
    ("aicon-3525", "https://aicon.kw.ac.kr/administration/notice.php?admin_mode=read&no=3525"),
    ("dept-electric-900", "https://electric.kw.ac.kr/community/s_notice.php?BoardMode=view&UID=900"),
    ("dept-chemng-78", "https://chemng.kw.ac.kr/community/notice.php?admin_mode=read&no=78"),
])
def test_post_ids_become_urls(post_id, url):
    assert notices.url_for_post_id(post_id) == url


@pytest.mark.parametrize("post_id", ["dept-architecture-0123456789abcdef01234567", "dept-nope-1", "x' or 1=1", ""])
def test_post_ids_without_a_url_are_refused(post_id):
    with pytest.raises(notices.NoticeError, match="url"):
        notices.url_for_post_id(post_id)


# --- the templates -----------------------------------------------------------------------------

@respx.mock
async def test_www_notice():
    page = respx.get(WWW_URL).mock(return_value=html(WWW_PAGE, headers={"Set-Cookie": "JSESSIONID=x; Path=/"}))
    tracker = respx.get(host="tracker.example.net")
    data = payload(await notices.read_notice(WWW_URL))
    assert data["title"] == "2026학년도 테스트 장학생 선발 공고"
    assert (data["date"], data["updated"], data["department"], data["category"]) == ("2026-11-02", "2026-11-03",
                                                                                   "학생복지팀", "등록/장학")
    assert data["body"] == "<<<KLAS_CONTENT\n* 자세한 내용은 첨부 파일을 참조하시기 바랍니다.\nKLAS_CONTENT>>>"
    assert data["attachments"] == [
        {"index": 1, "name": "선발 공고.pdf", "url": "https://www.kw.ac.kr/include/Download.jsp?fuid=1&ano=60001"},
        {"index": 2, "name": "신청서.txt", "url": "https://www.kw.ac.kr/include/Download.jsp?fuid=2&ano=60001"}]
    # the 1x1 pixel (by its size) and the tracker (another host) aren't listed; the logo is outside the body
    assert data["images"] == [{"index": 1, "url": "https://www.kw.ac.kr/KWData/webeditor/2026/poster.png",
                               "alt": "장학생 선발 포스터"}]
    assert data["source_url"] == WWW_URL and "images=true" in data["note"] and "attachment=번호" in data["note"]
    request = page.calls.last.request
    assert request.headers["User-Agent"] == klas.USER_AGENT and "cookie" not in request.headers
    assert not tracker.called


@respx.mock
async def test_boardmode_department_notice():
    respx.get(SNME_URL).mock(return_value=html(BOARDMODE_PAGE))
    data = payload(await notices.read_notice(SNME_URL))
    assert data["title"] == "[공지] 2027년도 테스트 연구실 배정 신청"
    assert (data["date"], data["department"]) == ("2026-10-28", "전자재료공학과")
    assert "관리자" not in json.dumps(data, ensure_ascii=False)  # the writer field is left out
    assert data["attachments"] == [{"index": 1, "name": "신청서_양식.xlsx",
                                    "url": "https://snme.kw.ac.kr/LIB/PHP_FUNC/Download.php?param=abc123"}]
    assert "신청 기간: 2026.10.28 ~ 2026.11.04" in data["body"] and "이전 글" not in data["body"]
    assert [i["url"] for i in data["images"]] == ["https://www.kw.ac.kr/KWData/webeditor/2026/table.jpg"]


@respx.mock
async def test_aicon_board_view_table():
    respx.get(AICON_URL).mock(return_value=html(AICON_PAGE))
    data = payload(await notices.read_notice(AICON_URL))
    assert data["title"] == "[공지] 2026학년도 테스트 졸업작품 전시회 안내"
    assert (data["date"], data["department"]) == ("2026-11-06", "인공지능융합대학")
    assert data["attachments"][0]["url"] == ("https://aicon.kw.ac.kr/lib/download.php?file_name=%EB%B0%B0%EC%B9%98"
                                             "%EB%8F%84.pdf&save_file=a_1.pdf&meta=free")
    assert "09:00~10:00 | 작품설치" in data["body"] and "글 목록" not in data["body"]
    assert data["images"][0]["url"] == "https://aicon.kw.ac.kr/webedit_naver/upload/261106/booth.png"


@respx.mock
async def test_agency_page_by_the_generic_search():
    respx.get(CHSS_URL).mock(return_value=html(AGENCY_PAGE))
    data = payload(await notices.read_notice(CHSS_URL))
    assert (data["title"], data["date"], data["department"]) == ("2026학년도 테스트 학생 설명회 안내", "2026-11-02",
                                                                  "인문사회과학대학")
    assert [a["name"] for a in data["attachments"]] == ["신청서.hwp"]  # "목록" and the menu are not files
    assert "설명회를 다음과 같이 엽니다." in data["body"] and "공지사항" not in data["body"]
    assert data["images"] == [{"index": 1, "url": "https://chss.kw.ac.kr/upload/editor/notice.jpg", "alt": "안내"}]


@respx.mock
async def test_ingenium_page_by_the_generic_search():
    respx.get(INGENIUM_URL).mock(return_value=html(INGENIUM_PAGE))
    data = payload(await notices.read_notice(INGENIUM_URL))
    assert (data["title"], data["date"], data["department"]) == ("테스트 교과목 수강 안내", "2026-06-15", "인제니움학부대학")
    assert [a["url"] for a in data["attachments"]] == ["https://ingenium.kw.ac.kr/bbs/download.php?idx=3"]
    assert data["body"] == "<<<KLAS_CONTENT\n교과목 수강 방법을 안내합니다.\nKLAS_CONTENT>>>"


@respx.mock
async def test_wix_post():
    respx.get(WIX_URL).mock(return_value=html(WIX_PAGE))
    data = payload(await notices.read_notice(WIX_URL))
    assert (data["title"], data["date"], data["department"]) == ("테스트 전시 안내", "2026-09-16", "건축학과")
    # the blurred placeholder becomes the same picture at up to 1568 px; the header logo isn't listed
    assert [i["url"] for i in data["images"]] == [
        "https://static.wixstatic.com/media/abc~mv2.jpg/v1/fill/w_1568,h_885,al_c,q_80,enc_auto/abc~mv2.jpg"]


@respx.mock
async def test_euc_kr_page():
    respx.get(ENGLISH_URL).mock(return_value=html(ENGLISH_PAGE, content_type="text/html"))
    data = payload(await notices.read_notice(ENGLISH_URL))
    assert data["title"] == "테스트 특강 안내" and "영어 특강을 엽니다." in data["body"]


# --- images ------------------------------------------------------------------------------------

POSTERS = "".join(f'<p><img src="/KWData/webeditor/2026/p{i}.png" alt="포스터 {i}"></p>' for i in range(1, 7))


def gallery(extra: str = "") -> str:
    return WWW_PAGE.replace('<p>* 자세한', f"{extra}{POSTERS}<p>* 자세한")


@respx.mock
async def test_images_come_as_image_content_and_pixels_are_skipped():
    respx.get(WWW_URL).mock(return_value=html(gallery()))
    respx.get("https://www.kw.ac.kr/KWData/webeditor/2026/poster.png").mock(
        return_value=httpx.Response(200, content=png(1, 1), headers={"Content-Type": "image/png"}))  # a tracking pixel
    for i in range(1, 7):
        respx.get(f"https://www.kw.ac.kr/KWData/webeditor/2026/p{i}.png").mock(
            return_value=httpx.Response(200, content=png(400 + i, 300), headers={"Content-Type": "application/octet-stream"}))
    answer = await notices.read_notice(WWW_URL, images=True)
    blocks = answer.content()
    data = json.loads(blocks[0].text)
    assert data["images"][0]["skipped"].startswith("아이콘이나 추적용")
    assert [b.type for b in blocks[1:]] == ["text", "image"] * 4  # at most four
    assert blocks[1].text == "이미지 2: https://www.kw.ac.kr/KWData/webeditor/2026/p1.png"
    assert blocks[2].mime_type == "image/png" and blocks[2].data
    assert [i.get("shown") for i in data["images"]] == [None, True, True, True, True, None, None]
    assert "[6, 7]" in data["images_note"]
    assert "note" not in data or "images=true" not in data["note"]


@respx.mock
async def test_image_size_caps():
    respx.get(WWW_URL).mock(return_value=html(gallery()))
    respx.get("https://www.kw.ac.kr/KWData/webeditor/2026/poster.png").mock(
        return_value=httpx.Response(200, content=png(800, 600, pad=1600 * 1024)))  # over 1.5 MB
    for i in range(1, 7):
        respx.get(f"https://www.kw.ac.kr/KWData/webeditor/2026/p{i}.png").mock(
            return_value=httpx.Response(200, content=png(500, 500, pad=1000 * 1024)))  # about 1 MB each
    limits = notices.Limits(images_total=2 * notices.MIB + 100 * 1024)
    answer = await notices.read_notice(WWW_URL, images=True, limits=limits)
    data = json.loads(answer.content()[0].text)
    assert "너무 큼" in data["images"][0]["skipped"]
    assert len(answer.pictures) == 2 and sum(len(p.data) for p in answer.pictures) <= limits.images_total
    assert "합계" in data["images"][3]["skipped"]


@respx.mock
async def test_images_that_are_not_pictures_are_skipped():
    respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    respx.get("https://www.kw.ac.kr/KWData/webeditor/2026/poster.png").mock(return_value=html("<html>login</html>"))
    answer = await notices.read_notice(WWW_URL, images=True)
    assert not answer.pictures and "이미지가 아님" in answer.data["images"][0]["skipped"]


def test_image_sizes_are_read_from_the_header():
    assert notices.image_info(png(640, 480)) == ("image/png", 640, 480)
    assert notices.image_info(b"GIF89a" + struct.pack("<HH", 1, 1) + b"\x00" * 8) == ("image/gif", 1, 1)
    jpeg = b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9 + b"\xff\xc0" + struct.pack(
        ">HBHH", 17, 8, 300, 500) + b"\x00" * 12
    assert notices.image_info(jpeg) == ("image/jpeg", 500, 300)
    webp = b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 8 + (799).to_bytes(3, "little") + (599).to_bytes(3, "little")
    assert notices.image_info(webp) == ("image/webp", 800, 600)
    assert notices.image_info(b"<svg/>") is None


# --- attachments -------------------------------------------------------------------------------

@respx.mock
async def test_attachment_text_comes_in_parts_and_is_downloaded_once():
    respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    text = ("신청 자격: 재학생. " * 4000)[:45_000]
    file = respx.get("https://www.kw.ac.kr/include/Download.jsp?fuid=2&ano=60001").mock(
        return_value=httpx.Response(200, content=text.encode(), headers={"Content-Type": "application/octet-stream"}))
    first = payload(await notices.read_notice(WWW_URL, attachment=2))
    assert (first["file"], first["kind"], first["part"], first["total_parts"]) == ("신청서.txt", "텍스트", 1, 3)
    assert first["text"].startswith("<<<KLAS_CONTENT\n신청 자격") and first["text"].endswith("KLAS_CONTENT>>>")
    second = payload(await notices.read_notice(WWW_URL, attachment=2, part=2))
    assert second["part"] == 2 and file.call_count == 1
    assert file.calls.last.request.headers["Referer"] == WWW_URL


@respx.mock
async def test_attachment_name_from_the_file_when_the_link_has_none():
    page = WWW_PAGE.replace("신청서.txt", "신청서 내려받기")
    respx.get(WWW_URL).mock(return_value=html(page))
    respx.get("https://www.kw.ac.kr/include/Download.jsp?fuid=2&ano=60001").mock(return_value=httpx.Response(
        200, content="안내문".encode(), headers={"Content-Disposition": "attachment; filename*=UTF-8''%EC%95%88%EB%82%B4.txt"}))
    assert payload(await notices.read_notice(WWW_URL, attachment=2))["text"] == "<<<KLAS_CONTENT\n안내문\nKLAS_CONTENT>>>"


@respx.mock
async def test_attachment_that_is_an_image_is_shown():
    respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    respx.get("https://www.kw.ac.kr/include/Download.jsp?fuid=1&ano=60001").mock(
        return_value=httpx.Response(200, content=png(900, 1200)))
    answer = await notices.read_notice(WWW_URL, attachment=1)
    assert answer.data["kind"] == "이미지" and [b.type for b in answer.content()] == ["text", "text", "image"]


@respx.mock
async def test_attachment_limits_and_mistakes():
    respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    big = respx.get("https://www.kw.ac.kr/include/Download.jsp?fuid=1&ano=60001").mock(
        return_value=httpx.Response(200, content=b"%PDF-" + b"0" * 5000))
    with pytest.raises(notices.NoticeError, match="너무 큽니다"):
        await notices.read_notice(WWW_URL, attachment=1, limits=notices.Limits(file_bytes=4096))
    assert big.called
    respx.get("https://www.kw.ac.kr/include/Download.jsp?fuid=2&ano=60001").mock(
        return_value=html("<html>잘못된 접근입니다</html>"))
    with pytest.raises(notices.NoticeError, match="웹 페이지가 왔습니다"):
        await notices.read_notice(WWW_URL, attachment=2)
    with pytest.raises(notices.NoticeError, match="1~2 사이.*1. 선발 공고.pdf, 2. 신청서.txt"):
        await notices.read_notice(WWW_URL, attachment=3)


@respx.mock
async def test_unreadable_attachment_says_why():
    respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    respx.get("https://www.kw.ac.kr/include/Download.jsp?fuid=1&ano=60001").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 broken"))
    with pytest.raises(notices.NoticeError, match="선발 공고.pdf: PDF를 읽지 못했습니다|선발 공고.pdf: 파일을 읽지 못했습니다"):
        await notices.read_notice(WWW_URL, attachment=1)


# --- fetching rules ----------------------------------------------------------------------------

@respx.mock
async def test_redirect_off_the_list_is_not_followed():
    respx.get(WWW_URL).mock(return_value=httpx.Response(302, headers={"Location": "https://evil.example.com/x"}))
    evil = respx.get(host="evil.example.com")
    with pytest.raises(notices.NoticeError, match="허용 목록 밖의 주소\\(evil.example.com\\)"):
        await notices.read_notice(WWW_URL)
    assert not evil.called


@respx.mock
async def test_redirect_within_the_list_is_followed_and_checked():
    moved = "https://www.kw.ac.kr/ko/life/notice.jsp?BoardMode=view&DUID=60002"
    respx.get(WWW_URL).mock(return_value=httpx.Response(301, headers={"Location": "/ko/life/notice.jsp?BoardMode=view&DUID=60002"}))
    respx.get(moved).mock(return_value=html(WWW_PAGE))
    assert payload(await notices.read_notice(WWW_URL))["source_url"] == moved


@respx.mock
async def test_redirect_loop_stops():
    respx.get(WWW_URL).mock(return_value=httpx.Response(302, headers={"Location": WWW_URL}))
    with pytest.raises(notices.NoticeError, match="너무 여러 번"):
        await notices.read_notice(WWW_URL)


@respx.mock
async def test_oversize_page_is_not_read():
    respx.get(WWW_URL).mock(return_value=httpx.Response(200, content=b"<html>" + b"x" * 5000,
                                                         headers={"Content-Type": "text/html"}))
    with pytest.raises(notices.NoticeError, match="너무 커서"):
        await notices.read_notice(WWW_URL, limits=notices.Limits(page_bytes=4096))
    huge = httpx.Response(200, headers={"Content-Type": "text/html", "Content-Length": str(50 * notices.MIB)})
    respx.get(SNME_URL).mock(return_value=huge)
    with pytest.raises(notices.NoticeError, match="너무 커서"):
        await notices.read_notice(SNME_URL)


@respx.mock
@pytest.mark.parametrize("response,message", [
    (httpx.Response(404), "글을 찾지 못했습니다"),
    (httpx.Response(403), "보여 주지 않았습니다"),
    (httpx.Response(503), "오류가 났습니다"),
    (httpx.Response(200, content=b"", headers={"Content-Type": "text/html"}), "빈 페이지"),
    (httpx.Response(200, content=b"%PDF-1.4", headers={"Content-Type": "application/pdf"}), "파일입니다"),
])
async def test_failures_are_explained(response, message):
    respx.get(WWW_URL).mock(return_value=response)
    with pytest.raises(notices.NoticeError, match=message):
        await notices.read_notice(WWW_URL)


@respx.mock
async def test_connection_failure_is_explained():
    respx.get(WWW_URL).mock(side_effect=httpx.ConnectError("offline"))
    with pytest.raises(notices.NoticeError, match="연결하지 못했습니다\\(ConnectError\\)"):
        await notices.read_notice(WWW_URL)


@respx.mock
async def test_page_is_cached_for_ten_minutes():
    route = respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    await notices.read_notice(WWW_URL)
    await notices.read_notice(WWW_URL)
    assert route.call_count == 1
    notices._PAGES[WWW_URL].at -= notices.CACHE_S + 1
    await notices.read_notice(WWW_URL)
    assert route.call_count == 2


async def test_pacer_spaces_requests_to_one_host():
    now, waits = [100.0], []

    async def sleep(seconds):
        waits.append(round(seconds, 3))
        now[0] += seconds

    pacer = notices.Pacer(clock=lambda: now[0], sleep=sleep)
    await pacer.before("https://www.kw.ac.kr/a")
    await pacer.before("https://ee.kw.ac.kr/b")  # another host: no wait
    await pacer.before("https://www.kw.ac.kr/c")
    now[0] += 0.5
    await pacer.before("https://www.kw.ac.kr/d")
    assert waits == [2.0, 1.5]


async def test_pacer_queues_concurrent_requests():
    now, woke = [0.0], []

    async def sleep(seconds):
        woke.append(seconds)

    pacer = notices.Pacer(clock=lambda: now[0], sleep=sleep)
    await asyncio.gather(*(pacer.before("https://www.kw.ac.kr/x") for _ in range(3)))
    assert sorted(woke) == [2.0, 4.0]


# --- the extension tool ------------------------------------------------------------------------

@respx.mock
async def test_read_school_notice_tool_returns_text_and_images():
    respx.get(WWW_URL).mock(return_value=html(WWW_PAGE))
    respx.get("https://www.kw.ac.kr/KWData/webeditor/2026/poster.png").mock(
        return_value=httpx.Response(200, content=png(600, 800)))
    result = await server.mcp.call_tool("read_school_notice", {"post_id": "60001", "images": True})
    assert [b.type for b in result.content] == ["text", "text", "image"]
    assert json.loads(result.content[0].text)["title"] == "2026학년도 테스트 장학생 선발 공고"
    assert result.structured_content is None


async def test_read_school_notice_tool_refuses_other_sites():
    from mcp.server.mcpserver.exceptions import ToolError

    with pytest.raises(ToolError, match="광운대 공지 사이트"):
        await server.mcp.call_tool("read_school_notice", {"url": "https://www.other-university.ac.kr/notice/1"})
    with pytest.raises(ToolError, match="url\\(또는 post_id\\)"):
        await server.mcp.call_tool("read_school_notice", {})


def test_instructions_send_school_questions_here_before_web_search():
    line = next(x for x in server.INSTRUCTIONS.splitlines() if "read_school_notice" in x)
    assert "school_notices" in line and "학칙" in line and "장학" in line
    assert "웹 검색" in server.INSTRUCTIONS
