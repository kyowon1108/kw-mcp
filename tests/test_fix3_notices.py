"""1.0 review fixes in the combined tools: my_notices' department section, campus alerts, holidays.

Made-up titles and departments only; the public API is an httpx MockTransport, KLAS a small fake."""

from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from kw_mcp import combined
from kw_mcp.klas import KlasError, KlasRequestLimit
from kw_mcp.public_api import PublicApi
from kw_mcp.service import KST


class Svc:
    """What the combined tools ask of a KlasService."""

    def __init__(self, now, department="전자공학과", schedule="월 3교시/새빛101"):
        self.now, self._department, self.schedule = now, department, schedule

    def _now(self):
        return self.now

    async def current_semester(self):
        return f"{self.now.year},1"

    async def courses(self):
        return [{"course": "데이터마이닝", "professor": "김교수", "schedule": self.schedule}]

    async def deadlines(self, days):
        return {"items": []}

    async def notices(self):
        return []

    async def department(self):
        if isinstance(self._department, BaseException):
            raise self._department
        return self._department


class Public:
    """The kw-campus JSON API: department-board rows for category=학과, nothing else. max_limit: the
    cap a kw-campus 1.0 server applies and says; None is a server before 1.0 (no cap in the answer)."""

    def __init__(self, department_rows=(), notices=(), max_limit=None):
        self.department_rows, self.notices, self.requests = list(department_rows), list(notices), []
        self.max_limit = max_limit

    def api(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(str(request.url))
            q = parse_qs(urlparse(str(request.url)).query)
            if request.url.path.endswith("/api/menu"):
                return httpx.Response(200, json={"meals": []})
            if request.url.path.endswith("/api/calendar"):
                return httpx.Response(200, json={"events": []})
            if q.get("category") == ["학과"]:
                cap = int(q["limit"][0]) if self.max_limit is None else min(int(q["limit"][0]), self.max_limit)
                body = {"notices": self.department_rows[:cap]}
                return httpx.Response(200, json=body if self.max_limit is None else {**body, "max_limit": self.max_limit})
            if q.get("source") == ["kw-notice"]:
                return httpx.Response(200, json={"notices": self.notices})
            return httpx.Response(200, json={"notices": []})
        return PublicApi("https://api.example/c/token", transport=httpx.MockTransport(handler))


def row(post_id, title, category, department=None, posted="2026-11-05", **extra):
    return {"post_id": post_id, "title": title, "category": category, "category_id": "dept-x",
            "department": category if department is None else department, "posted_date": posted,
            "url": f"https://example.kw.ac.kr/{post_id}", **extra}


NOW = datetime(2026, 11, 6, 9, 0, tzinfo=KST)


# --- B5: a copy on my board ------------------------------------------------------------------------

def test_department_notices_keep_my_copy_of_a_folded_notice():
    folded = row("dept-ee-646", "2026 취업박람회 개최 안내", "전자공학과", also=["dept-law-519"],
                 also_boards=[{"post_id": "dept-law-519", "category": "법학부", "department": "법학부",
                               "posted_date": "2026-11-03", "url": "https://example.kw.ac.kr/law/519"}])
    law = combined.department_notices([folded], "법학부", "정책법학대학")
    assert law == [{"post_id": "dept-law-519", "title": "2026 취업박람회 개최 안내", "category": "법학부",
                    "category_id": "dept-x", "department": "법학부", "posted_date": "2026-11-03",
                    "url": "https://example.kw.ac.kr/law/519"}]
    assert combined.department_notices([folded], "전자공학과", "전자정보공과대학") == [folded]
    assert combined.department_notices([folded], "행정학과", "정책법학대학") == []
    old_server = {k: v for k, v in folded.items() if k != "also_boards"}  # a server before 1.0: no boards
    assert combined.department_notices([old_server], "법학부", "정책법학대학") == []


# --- S09: what my_notices asks and says ----------------------------------------------------------------

async def test_my_notices_asks_every_board_with_the_larger_cap_and_keeps_the_department_here():
    public = Public([row("dept-ee-1", "전자공학과 수강 안내", "전자공학과"), row("dept-law-2", "법학부 안내", "법학부")])
    out = await combined.my_notices(Svc(NOW), public.api(), days=7)
    assert [n["post_id"] for n in out["department"]] == ["dept-ee-1"]
    scope = out["department_scope"]
    assert scope["boards"] == ["전자공학과", "전자정보공과대학"] and "truncated" not in scope
    assert "학과 이름은 이 PC에서만 씁니다." in scope["note"]
    asked = [parse_qs(urlparse(u).query) for u in public.requests if "category=%ED%95%99%EA%B3%BC" in u]
    assert asked and asked[0]["limit"] == [str(combined.DEPARTMENT_LIMIT)]
    assert not any("전자공학과" in u or "%EC%A0%84%EC%9E%90%EA%B3%B5%ED%95%99%EA%B3%BC" in u for u in public.requests)


@pytest.mark.parametrize("count, max_limit, truncated", [
    (combined.DEPARTMENT_LIMIT, None, True), (combined.LEGACY_LIMIT, None, True), (30, None, False),  # before 1.0
    # kw-campus 1.0 says its cap: 50 posts under a cap of 200 are all there were, 200 may be cut
    (combined.LEGACY_LIMIT, combined.DEPARTMENT_LIMIT, False), (combined.DEPARTMENT_LIMIT + 7, combined.DEPARTMENT_LIMIT, True),
    (120, 120, True), (119, 120, False),  # a server with a smaller cap than asked for
])
async def test_a_full_answer_says_how_far_back_it_reached(count, max_limit, truncated):
    start = date(2026, 10, 1)
    rows = [row(f"dept-ee-{n}", f"공지 {n}", "전자공학과", posted=(start + timedelta(days=n % 30)).isoformat())
            for n in range(count)]
    out = await combined.my_notices(Svc(NOW), Public(rows, max_limit=max_limit).api(), days=60)
    scope = out["department_scope"]
    assert scope.get("truncated", False) is truncated
    assert len(out["department"]) == min(count, max_limit or combined.DEPARTMENT_LIMIT)
    if truncated:
        assert scope["covered_from"] == "2026-10-01" and "2026-10-01 이후 글만 확인했습니다" in scope["note"]
    else:
        assert "covered_from" not in scope and "최근" not in scope["note"]


@pytest.mark.parametrize("answer", [{"max_limit": "200"}, {"max_limit": True}, {"max_limit": 0}, {}])
async def test_a_cap_the_server_doesnt_give_as_a_number_is_a_server_before_1_0(answer):
    rows = [row(f"dept-ee-{n}", f"공지 {n}", "전자공학과") for n in range(combined.LEGACY_LIMIT)]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"notices": rows, **answer})

    api = PublicApi("https://api.example/c/token", transport=httpx.MockTransport(handler))
    assert await combined.department_rows(api, "2026-10-01") == (rows, None)
    assert combined.department_section(rows, "전자공학과")["department_scope"]["truncated"] is True
    assert await combined.department_rows(PublicApi(""), "2026-10-01") == ([], None)  # not set up: nothing asked


async def test_departments_without_a_collected_board_are_named():
    out = await combined.my_notices(Svc(NOW, department="로봇학부"), Public().api())
    assert out["department_scope"]["boards"] == ["인공지능융합대학"]
    assert "내 학과 게시판은 따로 모으지 않아 인공지능융합대학 게시판의 글만 넣었습니다." in out["department_scope"]["note"]
    out = await combined.my_notices(Svc(NOW, department="행정학과"), Public().api())
    assert "단과대(정책법학대학) 게시판은 아직 모으지 않아" in out["department_scope"]["note"]
    out = await combined.my_notices(Svc(NOW, department="새학과"), Public().api())
    note = out["department_scope"]["note"]
    assert "단과대를 몰라" in note and "'없음'이 아닙니다" in note and out["department"] == []


async def test_the_request_cap_is_not_folded_into_a_department_note():
    with pytest.raises(KlasRequestLimit):
        await combined.my_notices(Svc(NOW, department=KlasRequestLimit("요청이 많아 4분 뒤 다시")), Public().api())
    out = await combined.my_notices(Svc(NOW, department=KlasError("학적 응답 없음")), Public().api())
    assert "department" not in out and "학적에서 학과를 읽지 못했습니다(KlasError)" in out["department_note"]


# --- S17: campus alerts ------------------------------------------------------------------------------

def test_alert_words_need_their_context():
    for title in ("(주)한국전력 품질점검 인턴 채용", "기상청 기상기후 청년인턴 모집", "2026 국가기상위성센터 대학생 서포터즈 모집",
                  "생산통제 담당 신입 채용", "이전 공지 참고: 2학기 장학 일정", "국민재난안전 아이디어 공모전",
                  "정전협정 기념 특강", "단수전공 신청 안내", "폐쇄회로(CCTV) 운영 안내",
                  # 이전 meaning "earlier" after a word that ends like an office (결과, 교과, 학과, 출처, 사실)
                  "수강신청 결과 이전 학기 대비 안내", "교과 이전 이수 과목 인정 안내", "학과 이전 공지 참고",
                  "출처 이전 글 참고", "사실 이전에는 없던 장학", "품질관리팀 인턴 채용", "내부통제 점검 결과 공개"):
        assert not combined.CAMPUS_ALERT_WORDS.search(title), title
    for title in ("KLAS 시스템 점검 안내 (11/7 02:00~06:00)", "새빛관 정전 안내", "한울관 출입 통제 안내",
                  "교내 차량 통제 안내", "학생지원팀 사무실 이전 안내", "기상 특보에 따른 휴강 안내", "61.111.8.4 서버 점검",
                  "재난 상황 발생 시 행동 요령", "KLAS 정기점검 안내", "도서관 임시 휴관",
                  # facility notices: a 시설/설비 before 점검, 구역·통로 통제, an office (팀·처·실·과·단) moving
                  "비마관 소방시설 정기점검 안내", "소방시설 점검에 따른 화재경보 오작동 안내", "한울관 일부 구역 통제 안내",
                  "학생지원팀 이전 안내", "승강기 설비 점검", "전기설비 안전점검 안내", "새빛관 주출입구 통제 안내",
                  "국제교류처 이전 및 업무 안내", "취업지원실 이전 안내", "산학협력단 이전 안내",
                  "학생지원팀 이전에 따른 업무 중단 안내"):
        assert combined.CAMPUS_ALERT_WORDS.search(title), title


async def test_campus_alerts_ask_fifty_main_board_rows_and_skip_outside_notices():
    notices = [{"title": "새빛관 정전 안내", "category_id": "facilities"},
               {"title": "[외부] 교통 통제 구간 홍보 공모전", "category_id": "external"}]
    public = Public(notices=notices)
    out = await combined.campus_alerts(public.api(), NOW)
    assert [n["title"] for n in out["notices"]] == ["새빛관 정전 안내"]
    asked = [parse_qs(urlparse(u).query) for u in public.requests if "source=kw-notice" in u]
    assert asked[0]["limit"] == [str(combined.ALERT_LIMIT)] and combined.ALERT_LIMIT == 50


# --- S38: 2027 holidays ---------------------------------------------------------------------------------

# 우주항공청 2027년 월력요항 (한국천문연구원 astro.kasi.re.kr), 노동절·제헌절 included since 2026.
HOLIDAYS_2027 = {
    "2027-01-01": "신정", "2027-02-06": "설날 연휴", "2027-02-07": "설날", "2027-02-08": "설날 연휴",
    "2027-02-09": "대체공휴일(설날)", "2027-03-01": "삼일절", "2027-05-01": "노동절", "2027-05-03": "대체공휴일(노동절)",
    "2027-05-05": "어린이날", "2027-05-13": "부처님오신날", "2027-06-06": "현충일", "2027-07-17": "제헌절",
    "2027-07-19": "대체공휴일(제헌절)", "2027-08-15": "광복절", "2027-08-16": "대체공휴일(광복절)", "2027-09-14": "추석 연휴",
    "2027-09-15": "추석", "2027-09-16": "추석 연휴", "2027-10-03": "개천절", "2027-10-04": "대체공휴일(개천절)",
    "2027-10-09": "한글날", "2027-10-11": "대체공휴일(한글날)", "2027-12-25": "성탄절", "2027-12-27": "대체공휴일(성탄절)",
}


def test_2027_holidays_are_in_the_table():
    assert {d: n for d, n in combined.KR_HOLIDAYS.items() if d.startswith("2027")} == HOLIDAYS_2027
    assert "2027" in combined.HOLIDAY_YEARS
    for day, name in combined.KR_HOLIDAYS.items():
        if name.startswith("대체공휴일"):  # a substitute day is a weekday that isn't a holiday itself
            assert date.fromisoformat(day).weekday() < 5, day
    assert combined.holiday(datetime(2027, 3, 1, tzinfo=KST)) == "삼일절"
    assert combined.holiday_check(datetime(2027, 6, 1, tzinfo=KST)) == {}
    assert combined.holiday_check(datetime(2028, 1, 3, tzinfo=KST)) == {"holiday_check": "2028년 공휴일 정보 없음"}


async def test_briefing_on_a_2027_holiday(monkeypatch):
    monkeypatch.setattr(combined, "term_in_session", lambda semester, now: True)
    day = datetime(2027, 3, 1, 9, 0, tzinfo=KST)  # 삼일절, a Monday
    out = await combined.today_briefing(Svc(day), Public().api())
    assert out["classes"][0]["holiday"] == "삼일절" and "공휴일(삼일절)" in out["classes_note"]
    assert out["campus_alerts"]["today"] == [{"start": "2027-03-01", "end": "2027-03-01", "title": "삼일절",
                                              "source": "법정 공휴일"}]
    assert "holiday_check" not in out
    plain = await combined.today_briefing(Svc(datetime(2027, 3, 8, 9, 0, tzinfo=KST)), Public().api())
    assert "holiday" not in plain["classes"][0] and "classes_note" not in plain and "campus_alerts" not in plain


def test_classes_note_cases():
    assert "2027,1 학기 수업 기간이 아니라" in combined.classes_note("2027,1", False, "삼일절")["classes_note"]
    assert "공휴일(삼일절)" in combined.classes_note(None, None, "삼일절")["classes_note"]  # the term unknown
    assert combined.classes_note("2027,1", True, None) == {}
    alerts = {"notices": [], "today": [{"title": "개교기념일"}]}
    assert combined.with_holiday(alerts, None, "2027-03-01") is alerts
    assert [e["title"] for e in combined.with_holiday(alerts, "삼일절", "2027-03-01")["today"]] == ["삼일절", "개교기념일"]
