"""Per-host rules of the notice reader: job.kw.ac.kr's robots.txt (Crawl-delay 10, Disallow /recommend/
and /job/) is kept on the client side, the other hosts keep the 2 s interval and any path."""

import httpx
import pytest

from kw_mcp import notices
from kw_mcp.notices import (
    DEPT_BOARDS,
    NoticeError,
    Pacer,
    _Fetcher,
    check_url,
    url_for_post_id,
)

JOB = "job.kw.ac.kr"


class Clock:
    """A fake monotonic clock whose sleep moves time forward and records each wait."""

    def __init__(self) -> None:
        self.now, self.waits = 0.0, []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


async def test_job_kw_waits_ten_seconds_and_the_rest_two():
    clock = Clock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)
    for _ in range(3):
        await pacer.before(f"https://{JOB}/community/notice.php?BoardMode=view&UID=1")
    assert clock.waits == [10.0, 10.0]
    clock.waits.clear()
    for _ in range(2):
        await pacer.before("https://ee.kw.ac.kr/HTML/department/undergrad_info.php")
    assert clock.waits == [notices.MIN_INTERVAL_S] == [2.0]


async def test_hosts_are_paced_apart_and_case_does_not_split_them():
    clock = Clock()
    pacer = Pacer(clock=clock, sleep=clock.sleep)
    await pacer.before(f"https://{JOB}/community/notice.php")
    await pacer.before("https://www.kw.ac.kr/ko/life/notice.jsp")  # another host: no wait
    await pacer.before("https://JOB.KW.AC.KR/community/notice.php")
    assert clock.waits == [10.0]


def test_only_the_notice_board_is_read_as_a_page_on_job_kw():
    url = url_for_post_id("dept-career-123")
    assert check_url(url) == f"https://{JOB}/community/notice.php?BoardMode=view&UID=123"
    for path in ("/index.php", "/job/list.php", "/recommend/view.php?no=1", "/community/other.php"):
        with pytest.raises(NoticeError):
            check_url(f"https://{JOB}{path}")
    # Other hosts: any page path, as before.
    assert check_url("https://ee.kw.ac.kr/HTML/anything.php?x=1") == "https://ee.kw.ac.kr/HTML/anything.php?x=1"


@pytest.mark.parametrize(("path", "allowed"), [
    ("/upload/board/notice.pdf", True),
    ("/images/poster.png", True),
    ("/job/file.pdf", False),
    ("/recommend/poster.png", False),
    ("/JOB/file.pdf", False),  # case
    ("/%6Aob/file.pdf", False),  # escaped
    ("/upload/../job/file.pdf", False),
])
def test_files_a_job_kw_page_links_to_stay_off_the_disallowed_paths(path, allowed):
    if allowed:
        assert check_url(f"https://{JOB}{path}", asset=True) == f"https://{JOB}{path}"
    else:
        with pytest.raises(NoticeError):
            check_url(f"https://{JOB}{path}", asset=True)


def test_a_redirect_into_a_disallowed_path_is_not_followed():
    with pytest.raises(NoticeError):
        _Fetcher._next_hop(f"https://{JOB}/community/notice.php?BoardMode=view&UID=1", "/job/list.php", False)
    with pytest.raises(NoticeError):
        _Fetcher._next_hop(f"https://{JOB}/community/notice.php", "/recommend/x.pdf", True)
    assert _Fetcher._next_hop(f"https://{JOB}/community/notice.php", "/files/a.pdf", True) == f"https://{JOB}/files/a.pdf"


def test_the_board_table_is_unchanged():
    assert DEPT_BOARDS["career"] == ("경력개발팀", JOB, "/community/notice.php", "A")


GNU_POST = """<html><head><title>장학생 선발 안내 &gt; 공지/행사안내 | 광운대학교 총동문회</title></head><body>
<article id="bo_v"><header><h2 class="kn">2026년도 장학생 선발 안내</h2></header>
<section id="bo_v_info"><h2>페이지 정보</h2><span class="sound_only">작성자</span> <strong>사무국</strong>
<strong class="if_date"><span class="sound_only">작성일</span> 26-08-28 14:06</strong></section>
<section id="bo_v_atc"><h2 id="bo_v_atc_title">본문</h2>
<div id="bo_v_img"><a href="https://www.kwuaa.com/bbs/view_image.php?bo_table=notice&amp;fn=a.png" class="view_image">
<img src="https://www.kwuaa.com/data/file/notice/thumb-a_800x1131.png" alt=""></a></div>
<div id="bo_v_con"><p>신청 기간: 9월 30일까지</p>
<a href="https://www.kwuaa.com/bbs/view_image.php?fn=x.jpg" class="view_image">
<img src="https://www.kwuaa.com/data/editor/2608/thumb-x_835x1181.jpg" alt="x.jpg"></a>
<img src="https://tracker.example/pixel.gif"></div></section>
<section id="bo_v_file"><h2>첨부파일</h2><ul><li><a href="https://www.kwuaa.com/bbs/download.php?bo_table=notice&amp;wr_id=86&amp;no=0&amp;nonce=n"
class="view_file_download"><strong>신청서식.hwp</strong></a> (61.0K) <span class="bo_v_file_cnt">21회 다운로드 | DATE : 2026-09-22 14:14:04</span></li></ul></section>
<ul class="bo_v_nb"><li><a href="https://www.kwuaa.com/bbs/board.php?bo_table=notice&amp;wr_id=87">이전글</a></li></ul>
</article></body></html>"""
ALUMNI_POST = "https://www.kwuaa.com/bbs/board.php?bo_table=notice&wr_id=86"


def test_the_alumni_gnuboard_is_read_like_a_department_board_but_its_files_are_not():
    """총동문회 (kwcampus.smallboards): gnuboard posts with their attached and inline images. Its download.php
    hands a file only to the session that opened the post (we keep no cookies), so files are a note, never a
    request; pages there are the listed board's posts only, assets its editor and board images only."""
    url = url_for_post_id("alumni-86")
    assert url == ALUMNI_POST and check_url(url) == url
    assert notices.GNU_BOARDS["alumni"] == ("총동문회", "www.kwuaa.com", "notice")
    page = notices.parse_page(GNU_POST, url)
    assert (page.title, page.date, page.department) == ("2026년도 장학생 선발 안내", "2026-08-28", "총동문회")
    assert "신청 기간" in page.body and "21회 다운로드" not in page.body and "이전글" not in page.body
    assert page.attachments == [] and page.site_files == 1
    assert page.images == [("https://www.kwuaa.com/data/file/notice/thumb-a_800x1131.png", None),  # #bo_v_img first
                           ("https://www.kwuaa.com/data/editor/2608/thumb-x_835x1181.jpg", "x.jpg")]  # no tracker
    notes = notices._notes({}, page, images=False)
    assert any("첨부 파일 1개" in n and "source_url" in n for n in notes)
    for bad in ("/bbs/login.php", "/index.php", "/bbs/write.php?bo_table=notice", "/bbs/board.php?bo_table=notice",
                "/bbs/board.php?bo_table=qa&wr_id=1", "/bbs/board.php?bo_table=notice&wr_id=86&page=2",
                "/bbs/board.php?bo_table=notice&wr_id=x"):
        with pytest.raises(NoticeError):
            check_url(f"https://www.kwuaa.com{bad}")
    for bad in ("/bbs/download.php?bo_table=notice&wr_id=86&no=0", "/data/file/notice/form.hwp",
                "/bbs/view_image.php?fn=x.jpg", "/data/editor/../../bbs/x.jpg", "/data/editor/2608/x.jpg?v=1",
                "/data/editor/x.php/y.jpg", "/data/file/notice/a.php.png", "/data/editor/a.jpg/b"):
        with pytest.raises(NoticeError):
            check_url(f"https://www.kwuaa.com{bad}", asset=True)
    assert check_url("https://www.kwuaa.com/data/file/notice/a.PNG", asset=True)
    # 총학생회 and 현장실습 notices are collected as links only
    for link in ("https://www.kwu-studentcouncil.co.kr/notices/cl1", "https://internship.kw.ac.kr/home/notice/view.do?bbsSeq=1"):
        with pytest.raises(NoticeError):
            check_url(link)


async def test_asking_for_a_gnuboard_file_makes_no_request():
    """attachment=1 on a 총동문회 post: refused from the page alone (the page itself comes from the cache here)."""
    asked = []

    def network(request):
        asked.append(str(request.url))
        return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=GNU_POST.encode())

    class Open:
        async def before(self, url):
            return None

    notices.clear_cache()
    with pytest.raises(NoticeError, match="브라우저로만"):
        await notices.read_notice(ALUMNI_POST, attachment=1, gate=Open(), transport=httpx.MockTransport(network))
    assert asked == [ALUMNI_POST]  # the page only, no download.php
    notices.clear_cache()


async def test_skipped_images_carry_a_short_code_and_a_gates_reason():
    """kwcampus records why an image wasn't read (its retries depend on it): the gate's own reason for a
    refusal, a fixed code for the rest."""
    from kw_mcp.notices import Refused

    assert Refused("x").reason == "refused" and Refused("x", "budget").reason == "budget"
    poster, icon, other = (f"https://ee.kw.ac.kr/upload/{n}.png" for n in ("poster", "small", "other"))
    page = f"""<html><body><div class="view_top"><h3>제목</h3><ul><li>2026-11-04</li></ul></div>
<div class="view_con"><p>본문</p><img src="{poster}"><img src="{icon}"><img src="{other}"></div></body></html>"""
    url = "https://ee.kw.ac.kr/HTML/department/undergrad_info.php?BoardMode=view&UID=1"

    class Gate:
        async def before(self, target):
            if target == other:
                raise Refused("오늘 다 썼습니다", "budget")

    def network(request):
        if str(request.url) == url:
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=page.encode())
        if str(request.url) == icon:
            return httpx.Response(200, content=b"GIF89a\x01\x00\x01\x00" + b"\0" * 20)
        return httpx.Response(404)

    notices.clear_cache()
    answer = await notices.read_notice(url, images=True, gate=Gate(), transport=httpx.MockTransport(network))
    codes = {row["url"]: row.get("skip") for row in answer.data["images"]}
    assert codes == {poster: "error", icon: "icon", other: "budget"}
    notices.clear_cache()


def test_files_only_the_site_hands_out_are_counted_in_the_summary():
    page = notices.parse_page(GNU_POST, ALUMNI_POST)
    assert notices._summary(page)["files_on_site"] == 1
    plain = notices.parse_page(GNU_POST.replace('<section id="bo_v_file">', '<section id="x">'), ALUMNI_POST)
    assert "files_on_site" not in notices._summary(plain)



async def test_an_image_the_caller_has_already_costs_no_request_and_no_try():
    """A gate refusing with reason "done" (kwcampus: read on an earlier try) doesn't use up MAX_IMAGE_TRIES."""
    from kw_mcp.notices import Refused

    urls = [f"https://ee.kw.ac.kr/upload/p{i}.png" for i in range(notices.MAX_IMAGE_TRIES + 1)]
    imgs = "".join(f'<img src="{u}">' for u in urls)
    page = f"""<html><body><div class="view_top"><h3>제목</h3></div><div class="view_con"><p>본문</p>{imgs}</div></body></html>"""
    url = "https://ee.kw.ac.kr/HTML/department/undergrad_info.php?BoardMode=view&UID=2"
    asked = []

    class Gate:
        async def before(self, target):
            if target in urls[:-1]:
                raise Refused("이미 읽음", "done")

    def network(request):
        asked.append(str(request.url))
        if str(request.url) == url:
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, content=page.encode())
        return httpx.Response(404)

    notices.clear_cache()
    answer = await notices.read_notice(url, images=True, gate=Gate(), transport=httpx.MockTransport(network))
    assert asked == [url, urls[-1]]  # the last image was still tried
    assert answer.data["images"][-1]["skip"] == "error" and answer.data["images"][0]["skip"] == "done"
    notices.clear_cache()
