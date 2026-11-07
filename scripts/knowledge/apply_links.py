"""Puts the official URLs into the link-style entries (reading-room seats, library, dormitory, shuttle), and
fixes a few question variants that pulled generic questions onto narrow entries.

Claude saw these pages as text without their addresses, so some entries said "주소는 자료에 없음". The address
of every page is known (sources.json); this step writes it into how_to and adds the page as a source. kupis is
robots-disallowed and was never fetched: it is cited as a link only. Idempotent; run before --assemble.

    python apply_links.py
"""

from __future__ import annotations

import json

from build_faq import CATEGORIES, entry_files
from kbcommon import dump_json

SEATS = "http://mobileid.kw.ac.kr/seatweb/domian5.asp"
KUPIS = "https://kupis.kw.ac.kr/"
DORM = "https://kw.happydorm.or.kr/"
DORM_NOTICE = "https://kw.happydorm.or.kr/60/6010.do"
DORM_ADMISSION = "https://kw.happydorm.or.kr/30/3010.do"
DORM_APPLY = "https://kw.happydorm.or.kr/30/3030.do"
DIRECTIONS = "https://www.kw.ac.kr/ko/tour/directions.jsp"
CALENDAR = "https://www.kw.ac.kr/ko/life/bachelor_calendar.jsp"
HAKSA_NOTICES = "https://www.kw.ac.kr/ko/life/notice.jsp?srCategoryId=1"
CLUBS = "https://www.kw.ac.kr/ko/life/activity03.jsp"

# entry id -> (sentence for how_to, source ids to add, answer phrases to drop)
LINKS = {
    "library-seat-status-live": (
        f"열람실 실시간 좌석 현황: {SEATS} (1분마다 자동 갱신). 도서관 홈페이지: {KUPIS}",
        ["seat-status", "kupis-home"], ["페이지 주소와 ", "자료에 페이지 주소나 메뉴 경로가 없으므로, 위치를 모르면 "]),
    "library-reading-room-seat-count": (f"실시간 좌석 현황: {SEATS}", ["seat-status"], []),
    "library-hours": (f"도서관 홈페이지: {KUPIS}", ["kupis-home"], []),
    "library-contact": (f"도서관 홈페이지: {KUPIS}", ["kupis-home"], []),
    "dorm-apply-how": (f"행복기숙사 공지사항: {DORM_NOTICE}, 입사신청: {DORM_APPLY}",
                       ["dorm-apply", "dorm-main"], []),
    "dorm-checkin-procedure": (f"입사/퇴사 안내: {DORM_ADMISSION}, 입사신청: {DORM_APPLY}",
                               ["dorm-admission", "dorm-apply"], []),
    "dorm-checkin-documents": (f"입사 안내: {DORM_ADMISSION}", ["dorm-admission"], []),
    "dorm-rules-life": (f"행복기숙사 홈페이지: {DORM}", ["dorm-main"], []),
    "dorm-contact": (f"행복기숙사 홈페이지: {DORM}", ["dorm-contact"], []),
    "shuttle-route-schedule": (f"위치 및 교통안내: {DIRECTIONS}", ["web-directions"], []),
    "shuttle-info-currency": (f"위치 및 교통안내: {DIRECTIONS}", ["web-directions"], []),
    "shuttle-stop-location": (f"위치 및 교통안내: {DIRECTIONS}", ["web-directions"], []),
    # round 4
    "campus-student-counseling": ("학생상담실 홈페이지: https://sangdam.kw.ac.kr/", ["web-counsel"], []),
    "support-humanrights-gender-counseling": ("인권·성평등상담실 홈페이지: https://humanrights.kw.ac.kr/",
                                              ["web-humanrights"], []),
    "career-job-postings-instagram": ("경력개발팀 인스타그램: https://www.instagram.com/kwu_career", ["job-51947"], []),
    "career-internship-apply-contact": ("현장실습온라인시스템: https://internship.kw.ac.kr/index.do", ["internship-home"], []),
    "career-internship-credit-rules": ("현장실습온라인시스템: https://internship.kw.ac.kr/index.do", ["internship-home"], []),
    # round 5
    "support-counseling-booking-hours": ("학생상담실 홈페이지: https://sangdam.kw.ac.kr/", ["sangdam-notice"], []),
    "enroll-notice-search": (f"학사일정: {CALENDAR}, 학사 공지: {HAKSA_NOTICES}", ["web-calendar", "notices-haksa-1"], []),
    "enroll-schedule-where": (f"학사일정: {CALENDAR}, 학사 공지: {HAKSA_NOTICES}", ["web-calendar", "notices-haksa-1"], []),
    # security review: no shorteners or pages of unknown owners. vvd.bz/bhjy answered a HEAD with 200 and no
    # Location, so it has no resolved official address; the KW-MOOC address and menu path stay.
    "support-violence-prevention-education": ("", [], [" 바로가기 링크: https://vvd.bz/bhjy"]),
    # the 중앙동아리 page links a Notion page whose owner is not known; point at the school's page instead
    "club-join-how": (f"중앙동아리 안내: {CLUBS}", ["web-activity03"],
                      ["(https://aback-shirt-867.notion.site/f400deafa1434fe6bc03f2d62a61e51b)",
                       "에 연결된 노션 안내 페이지"]),
}

# Entries removed outright (id -> reason). The event's sign-up link was m.site.naver.com/2iMoN, which a HEAD
# resolved to a Google Form (not a school address), and the event itself ends on 2026-11-10.
DROP = {"support-humanrights-lecture-2026": "2026-11-10 특강, 신청 링크가 단축 주소(구글 폼)"}


# Question variants that pulled a generic question onto a narrower entry (entry id -> {old: new}).
QUESTION_FIXES = {
    "tuition-withdrawal-refund-procedure": {"자퇴 서류 뭐 필요함?": "자퇴하면 등록금 얼마 돌려받아?",
                                            "자퇴원서 양식 어디 있음?": "자퇴 환불은 어느 계좌로 받아?",
                                            "자퇴 환불 계좌는 어떻게 알려줘?": "자퇴 환불은 어느 계좌로 받아?"},
    "status-withdrawal-procedure": {"+": "자퇴하려면 어디 가서 뭐 내야 돼?"},
    # round 5: '제대' (not only '전역') should reach the return-after-service entry
    "status-return-after-military": {"+": "군대 제대하고 복학할 때 뭐 내?"},
}


def main() -> None:
    done = []
    for _, prefix in CATEGORIES:
        for path in entry_files(prefix):
            d = json.loads(path.read_text(encoding="utf-8"))
            changed = False
            gone = [e["id"] for e in d["entries"] if e["id"] in DROP]
            if gone:
                d["entries"] = [e for e in d["entries"] if e["id"] not in DROP]
                d.setdefault("dropped", []).extend({"id": i, "reason": DROP[i]} for i in gone)
                changed = True
            for e in d["entries"]:
                fixes = QUESTION_FIXES.get(e["id"], {})
                if any(q in fixes for q in e["questions"]):
                    e["questions"] = [fixes.get(q, q) for q in e["questions"]]
                    changed = True
                extra = fixes.get("+")
                if extra and extra not in e["questions"] and len(e["questions"]) < 6:
                    e["questions"].append(extra)
                    changed = True
                if e["id"] not in LINKS:
                    continue
                sentence, sids, drop = LINKS[e["id"]]
                for phrase in drop:
                    e["answer"] = e["answer"].replace(phrase, "")
                    e["how_to"] = e["how_to"].replace(phrase, "")
                if sentence and sentence not in e["how_to"]:
                    e["how_to"] = (e["how_to"].rstrip() + " " + sentence).strip()
                have = {s["source_id"] for s in e["sources"]}
                e["sources"] += [{"source_id": s, "article": "링크", "quote": ""} for s in sids if s not in have]
                changed = True
                done.append(e["id"])
            if changed:
                dump_json(path, d)
    missing = sorted(set(LINKS) - set(done))
    print("links added to", len(done), "entries; not found:", missing)


if __name__ == "__main__":
    main()
