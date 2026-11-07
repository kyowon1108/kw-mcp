"""Per-host rules of the notice reader: job.kw.ac.kr's robots.txt (Crawl-delay 10, Disallow /recommend/
and /job/) is kept on the client side, the other hosts keep the 2 s interval and any path."""

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
