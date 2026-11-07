"""학과 사무실·단과대학 교학팀 연락처 entries, built without Claude from the www department and college pages.

Each department page shows "학과문의 : 02-940-xxxx" and the college office's room; each college page shows the
교학팀 number. Office numbers only: the staff tables on the same pages (names, e-mail) are never read here.

    python build_contacts.py        # -> out/faq-etc-extra-contacts.json (build_faq.py --assemble picks it up)
"""

from __future__ import annotations

import re

from kbcommon import OUT, TEXT, dump_json, load_sources

COLLEGES = [  # (slug, name, short names students use, college page id, department page ids)
    ("ei", "전자정보공과대학", ["전정대"], "college-001",
     ["college_001_01", "college_001_04", "college_001_05", "college_001_02", "college_001_03", "college_001_08"]),
    ("ai", "인공지능융합대학", ["인융대"], "college-011",
     ["college_011_01", "college_011_02", "college_011_03", "college_011_04", "college_011_05", "ai06_1"]),
    ("eng", "공과대학", ["공대"], "college-003", ["college_003_01", "college_003_02", "college_003_03", "college_003_04"]),
    ("sci", "자연과학대학", ["자연대"], "college-004", ["college_004_01", "college_004_02", "college_004_04", "college_004_05"]),
    ("hss", "인문사회과학대학", ["인사대"], "college-005",
     ["college_005_01", "college_005_02", "college_005_03", "college_005_06", "college_005_07"]),
    ("law", "정책법학대학", ["정법대"], "college-006", ["college_006_01", "college_006_02", "college_006_05"]),
    ("biz", "경영대학", ["경영대"], "college-007", ["college_007_01", "college_007_02"]),
    ("chambit", "참빛인재대학", ["참빛"], "college-010",
     ["college_010_01", "college_010_02", "college_010_03", "college_010_04"]),
    ("ingenium", "인제니움대학(자율전공학부)", ["자율전공"], "college-008", []),
]
CHECKED_AT = "2026-11-07"
PHONE = r"0?2?-?\d{3,4}-\d{4}(?:\s*,\s*\d{4})?"


def _text(sid: str) -> str:
    p = TEXT / f"{sid}.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def dept_info(sid: str) -> tuple[str | None, str | None]:
    t = _text(sid)
    phone = re.search(rf"학과문의\s*:\s*({PHONE})", t)
    room = re.search(r"위치\s*:\s*([^\n]+)", t)
    return (phone.group(1).strip() if phone else None), (room.group(1).strip() if room else None)


def college_phone(sid: str) -> str | None:
    t = _text(sid)
    head = t[: t.find("교육목표")] if "교육목표" in t else t[:1500]
    m = re.search(r"\n(02-\d{3,4}-\d{4})\n", head)
    return m.group(1) if m else None


def main() -> None:
    names = {s["id"]: s.get("department") for s in load_sources()}
    entries, general = [], []
    for slug, college, short, college_sid, depts in COLLEGES:
        office = college_phone(college_sid)
        rows, sources, room = [], [], None
        for hp in depts:
            sid = f"dept-{hp}"
            phone, where = dept_info(sid)
            if phone:
                rows.append(f"{names.get(sid) or hp} {phone}")
                sources.append({"source_id": sid, "article": "학과 소개 - 학과문의", "quote": ""})
                room = room or where
        if office:
            sources.append({"source_id": college_sid, "article": "단과대학 소개 - 교학팀 연락처", "quote": ""})
        if not rows and not office:
            continue
        if office:
            general.append(f"{college} 교학팀 {office}")
        dept_names = [r.rsplit(" ", 1)[0] for r in rows]
        answer = (f"{college} 학과 사무실 대표번호입니다. " + ", ".join(rows) + "." if rows else
                  f"{college} 학생은 학과별 번호 대신 교학팀으로 문의합니다.")
        if office:
            answer += f" 단과대학 교학팀은 {office}" + (f"(위치 {room})" if room else "") + "입니다."
        elif rows and len({r.rsplit(" ", 2)[-2] if ", " in r else r.rsplit(" ", 1)[-1] for r in rows}) == 1:
            answer += " 네 학과가 같은 번호를 씁니다."
        first = dept_names[0] if dept_names else college
        entries.append({
            "id": f"etc-office-phone-{slug}",
            "questions": [f"{first} 과사 전화번호 뭐야?", f"{short[0]} 학과사무실 연락처", f"{college} 교학팀 번호",
                          f"{dept_names[-1] if dept_names else college} 사무실 어디로 전화해?"],
            "answer": answer,
            "conditions_exceptions": ["번호는 학교 홈페이지 학과 소개 페이지의 '학과문의' 기준이며, 담당자 개인 번호는 싣지 않았습니다.",
                                      "업무 시간과 담당 업무는 학과 사무실에 확인하세요."],
            "how_to": "학교 홈페이지 > 교육 > 단과대학 > 학과 소개 페이지에서 '학과문의' 번호를 확인할 수 있습니다.",
            "contact_office": {"name": f"{college} 교학팀", "phone": office or ""},
            "sources": sources,
            "applies_to": f"{college} 학생",
            "confidence": "high",
            "disagreement": "",
        })
    entries.append({
        "id": "etc-office-phone-where",
        "questions": ["과사 전화번호 어디서 찾아?", "학과 사무실 번호 알려줘", "교학팀 연락처 모음", "우리 과 사무실 어디야?"],
        "answer": ("학과 사무실 번호는 학교 홈페이지의 학과 소개 페이지('학과문의')에 있습니다. 단과대학 교학팀 대표번호는 "
                   + ", ".join(general) + "입니다. 학과별 번호는 단과대학별 항목을 보세요."),
        "conditions_exceptions": ["개인 담당자 번호는 싣지 않았습니다."],
        "how_to": "학교 홈페이지 > 교육 > 단과대학 > 학과 소개에서 확인합니다.",
        "contact_office": {"name": "소속 단과대학 교학팀", "phone": ""},
        "sources": [{"source_id": c[3], "article": "단과대학 소개 - 교학팀 연락처", "quote": ""} for c in COLLEGES
                    if college_phone(c[3])],
        "applies_to": "전체 학부생",
        "confidence": "high",
        "disagreement": "",
    })
    out = {"category": "기타", "entries": entries, "gaps": [], "dropped": [],
           "changes": [f"built by build_contacts.py from department and college pages ({CHECKED_AT})"]}
    dump_json(OUT / "faq-etc-extra-contacts.json", out)
    print(len(entries), "contact entries")


if __name__ == "__main__":
    main()
