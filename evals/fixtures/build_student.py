"""Builds evals/fixtures/student.json: one synthetic student as raw KLAS answers.

Nothing here is a real person. Course codes, professors ("김교수"), the student number and every
grade are made up. The shapes follow what kw_mcp.service reads (see tests/test_*service*.py), so the
real shaping code runs on it. "Today" is Saturday 2026-11-07 13:00 KST, week 10 of 2026-2.

    uv run --frozen python evals/fixtures/build_student.py
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).with_name("student.json")
NOW = "2026-11-07T13:00:00+09:00"
SEM = "2026,2"
WEEK1_MONDAY = date(2026, 8, 31)  # 2026-2 starts Tue 2026-09-01
LAST_HELD = date(2026, 11, 6)     # classes held up to Friday of week 10
NO_CLASS = {date(2026, 9, 24), date(2026, 9, 25), date(2026, 10, 9)}  # 추석 연휴, 한글날
DAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4}

# subj, name, professor, schedule, category, credits, meeting days
COURSES = [
    ("U26DB0101", "데이터베이스", "김교수", "월 3교시/새빛관 203, 수 3교시/새빛관 203", "전필", 3, ["월", "수"]),
    ("U26OS0101", "운영체제", "이교수", "화 4교시/새빛관 301, 목 4교시/새빛관 301", "전필", 3, ["화", "목"]),
    ("U26ML0101", "머신러닝", "박교수", "수 5,6교시/한울관 B101", "전선", 3, ["수"]),
    ("U26PS0101", "확률과통계", "최교수", "화 2교시/비마관 405, 목 2교시/비마관 405", "전선", 3, ["화", "목"]),
    ("U26ET0101", "현대사회와윤리", "정교수", "금 2,3교시/화도관 301", "교선", 3, ["금"]),
    ("U26AI0101", "AI와 데이터 리터러시", "한교수", "미지정", "교선", 3, []),
]
LABEL = {subj: f"{name} (H0{i}0-{i}-{1000 + i}-01)" for i, (subj, name, *_) in enumerate(COURSES, 1)}

# Absences/lates/early/excused: (subj, week, session) -> code. Everything else held is AT.
MARKS = {
    ("U26OS0101", 3, 1): "AB", ("U26OS0101", 7, 2): "LT", ("U26OS0101", 9, 1): "AB",
    ("U26PS0101", 2, 2): "AB", ("U26PS0101", 5, 2): "AB", ("U26PS0101", 8, 2): "AB",
    ("U26PS0101", 4, 1): "LT", ("U26PS0101", 10, 1): "LT",
    ("U26DB0101", 6, 1): "OA",
    ("U26ML0101", 4, 1): "LE", ("U26ML0101", 4, 2): "LE",
    ("U26ET0101", 5, 1): "AB", ("U26ET0101", 5, 2): "AB",
}


def attendance(subj: str, days: list[str], two_periods_one_day: bool) -> list:
    weeks: list = []
    for week in range(1, 17):
        monday = WEEK1_MONDAY + timedelta(days=7 * (week - 1))
        if monday > LAST_HELD:
            weeks.append(None)
            continue
        row: dict = {"weeklyseq": week}
        if two_periods_one_day:
            dates = [monday + timedelta(days=DAYS[days[0]])] * 2
        else:
            dates = [monday + timedelta(days=DAYS[d]) for d in days]
        for i, day in enumerate(dates, 1):
            held = date(2026, 9, 1) <= day <= LAST_HELD and day not in NO_CLASS
            row[f"attendancediv{i}"] = MARKS.get((subj, week, i), "AT") if held else None
            row[f"attendancedate{i}"] = day.strftime("%Y%m%d") if held else None
        for i in range(len(dates) + 1, 5):
            row[f"attendancediv{i}"] = None
        weeks.append(row)
    return weeks


TASKS = {
    "U26DB0101": [
        {"ordseq": 1, "title": "과제 1: SQL 기초 질의", "startdate": "2026-09-21 00:00:00", "expiredate": "2026-10-04 23:59:59",
         "reexpiredate": None, "submityn": "Y", "score": "9"},
        {"ordseq": 2, "title": "과제 2: 도서관 대출 시스템 ERD 설계", "startdate": "2026-10-28 00:00:00",
         "expiredate": "2026-11-07 23:59:59", "reexpiredate": "2026-11-09 23:59:59", "submityn": "N", "score": None},
    ],
    "U26OS0101": [
        {"ordseq": 2, "title": "과제 2: 프로세스 동기화(세마포어)", "startdate": "2026-10-15 00:00:00",
         "expiredate": "2026-11-01 23:59:59", "reexpiredate": "2026-11-08 23:59:59", "submityn": "N", "score": None},
        {"ordseq": 3, "title": "과제 3: CPU 스케줄링 시뮬레이터", "startdate": "2026-11-02 00:00:00",
         "expiredate": "2026-11-13 23:59:59", "reexpiredate": None, "submityn": "N", "score": None},
    ],
    "U26ML0101": [
        {"ordseq": 4, "title": "실습 4: 결정트리 구현", "startdate": "2026-11-04 00:00:00", "expiredate": "2026-11-10 23:59:59",
         "reexpiredate": None, "submityn": "N", "score": None},
        {"ordseq": 3, "title": "실습 3: 로지스틱 회귀", "startdate": "2026-10-21 00:00:00", "expiredate": "2026-10-27 23:59:59",
         "reexpiredate": None, "submityn": "Y", "score": "8"},
    ],
    "U26PS0101": [
        {"ordseq": 3, "title": "과제 3: 조건부확률과 베이즈 정리", "startdate": "2026-11-03 00:00:00",
         "expiredate": "2026-11-12 18:00:59", "reexpiredate": None, "submityn": "N", "score": None},
    ],
    "U26ET0101": [
        {"ordseq": 1, "title": "에세이 1: 기술과 책임", "startdate": "2026-09-14 00:00:00", "expiredate": "2026-10-02 23:59:59",
         "reexpiredate": None, "submityn": "Y", "score": "18"},
        {"ordseq": 2, "title": "에세이 2: 데이터 프라이버시", "startdate": "2026-11-06 00:00:00",
         "expiredate": "2026-11-27 23:59:59", "reexpiredate": None, "submityn": "N", "score": None},
    ],
    "U26AI0101": [],
}

TASK_VIEW = {
    "U26DB0101": {
        "2": {"rpt": {"title": "과제 2: 도서관 대출 시스템 ERD 설계",
                      "contents": "<p>도서관 대출 시스템의 요구사항(첨부 가이드)을 읽고 ERD를 설계하세요.</p>"
                                  "<p>- 엔터티 6개 이상, 관계의 카디널리티 표기</p><p>- 제출: PDF 1개, 파일명 학번_이름.pdf</p>"
                                  "<p>- 지각 제출은 11/9(월) 23:59까지 받으며 하루에 10% 감점합니다.</p>",
                      "submitfiletype": "PDF", "filelimit": "20", "reptype": "P", "submityn": "N", "indate": "Y",
                      "adddate": "N", "isopenscore": "N", "attachopen": "Y", "atchFileId": "F-DB-T2", "ordseq": 2},
              "smt": None},
        "1": {"rpt": {"title": "과제 1: SQL 기초 질의", "contents": "<p>첨부한 스키마로 SELECT 질의 10개를 작성하세요.</p>",
                      "submitfiletype": "SQL", "filelimit": "5", "reptype": "P", "submityn": "Y", "indate": "N",
                      "adddate": "N", "isopenscore": "Y", "attachopen": "Y", "atchFileId": None, "ordseq": 1},
              "smt": {"registDt": "2026-10-04T13:20:00.000+00:00", "finalscore": 9, "tutordate": "2026-10-12",
                      "tutorcontents": "<p>JOIN 조건 하나 누락(-1)</p>"}},
    },
    "U26OS0101": {
        "2": {"rpt": {"title": "과제 2: 프로세스 동기화(세마포어)",
                      "contents": "<p>생산자-소비자 문제를 세마포어로 구현하세요(C, pthread). 보고서 2쪽 이내.</p>"
                                  "<p>마감 후 1주일(11/8)까지 지각 제출 가능, 감점 20%.</p>",
                      "submitfiletype": "ZIP", "filelimit": "30", "reptype": "P", "submityn": "N", "indate": "N",
                      "adddate": "Y", "isopenscore": "N", "attachopen": "Y", "atchFileId": None, "ordseq": 2},
              "smt": None},
        "3": {"rpt": {"title": "과제 3: CPU 스케줄링 시뮬레이터",
                      "contents": "<p>FCFS, SJF, RR(q=4) 스케줄러를 구현하고 평균 대기시간을 비교하세요.</p>",
                      "submitfiletype": "ZIP", "filelimit": "30", "reptype": "P", "submityn": "N", "indate": "Y",
                      "adddate": "N", "isopenscore": "N", "attachopen": "Y", "atchFileId": None, "ordseq": 3},
              "smt": None},
    },
    "U26PS0101": {
        "3": {"rpt": {"title": "과제 3: 조건부확률과 베이즈 정리",
                      "contents": "<p>교재 5장 연습문제 3, 7, 12번. 손글씨 스캔 PDF 가능.</p><p>11/12(목) 18:00 마감, 지각 제출 없음.</p>",
                      "submitfiletype": "PDF", "filelimit": "20", "reptype": "P", "submityn": "N", "indate": "Y",
                      "adddate": "N", "isopenscore": "N", "attachopen": "Y", "atchFileId": None, "ordseq": 3},
              "smt": None},
    },
    "U26ML0101": {
        "4": {"rpt": {"title": "실습 4: 결정트리 구현",
                      "contents": "<p>scikit-learn 없이 ID3 결정트리를 구현하고 ipynb로 제출하세요.</p>",
                      "submitfiletype": "IPYNB", "filelimit": "10", "reptype": "P", "submityn": "N", "indate": "Y",
                      "adddate": "N", "isopenscore": "N", "attachopen": "Y", "atchFileId": None, "ordseq": 4},
              "smt": None},
    },
}

ONLINE = {
    "U26AI0101": [
        {"weekNo": 9, "moduletitle": "9주차", "sbjt": "데이터 편향과 공정성", "startDate": "2026-10-26 00:00",
         "endDate": "2026-11-01 23:59", "prog": 100, "rcognTime": "50", "achivTime": "50"},
        {"weekNo": 10, "moduletitle": "10주차", "sbjt": "생성형 AI의 원리", "startDate": "2026-11-02 00:00",
         "endDate": "2026-11-08 23:59", "prog": 35, "rcognTime": "50", "achivTime": "18"},
        {"weekNo": 11, "moduletitle": "11주차", "sbjt": "AI와 저작권", "startDate": "2026-11-09 00:00",
         "endDate": "2026-11-15 23:59", "prog": 0, "rcognTime": "50", "achivTime": "0"},
        {"evltnSe": "quiz", "sbjt": "10주차 확인 퀴즈", "startDate": "2026-11-02 00:00", "endDate": "2026-11-08 23:59", "prog": None},
    ],
    "U26ML0101": [
        {"weekNo": 10, "moduletitle": "10주차", "sbjt": "결정트리 보충 영상", "startDate": "2026-11-04 00:00",
         "endDate": "2026-11-11 23:59", "prog": 60, "rcognTime": "30", "achivTime": "18"},
    ],
}

QUIZZES = {
    "U26PS0101": [
        {"papernm": "8주차 퀴즈: 이산확률분포", "examtypenm": "온라인", "sdt": "2026-11-06 09:00:00",
         "edt": "2026-11-09 18:00:00", "issubmit": "N", "examtime": "20", "examcnt": 5, "totalscore": 10},
        {"papernm": "5주차 퀴즈: 확률의 공리", "examtypenm": "온라인", "sdt": "2026-10-05 09:00:00",
         "edt": "2026-10-08 18:00:00", "issubmit": "Y", "examtime": "20", "examcnt": 5, "totalscore": 10},
    ],
    "U26AI0101": [
        {"papernm": "10주차 확인 퀴즈", "examtypenm": "온라인", "sdt": "2026-11-02 00:00:00", "edt": "2026-11-08 23:59:00",
         "issubmit": "N", "examtime": "10", "examcnt": 3, "totalscore": 3},
    ],
}

ONLINE_TESTS = {
    "U26AI0101": [
        {"papernm": "중간고사(온라인)", "examtypenm": "온라인시험", "sdt": "2026-10-20 10:00:00", "edt": "2026-10-20 11:00:00",
         "issubmit": "Y", "isretry": "N", "weeklyseq": 8},
        {"papernm": "기말고사(온라인)", "examtypenm": "온라인시험", "sdt": "2026-12-15 10:00:00", "edt": "2026-12-15 11:00:00",
         "issubmit": "N", "isretry": "N", "weeklyseq": 15},
    ],
}

PROJECTS = {
    "U26ML0101": [
        {"title": "기말 팀 프로젝트 제안서", "purpose": "주제·데이터셋·역할 분담 1쪽", "startdate": "2026-11-02 00:00:00",
         "expiredate": "2026-11-14 23:59:59", "reexpiredate": None, "submityn": "N", "score": None, "teamno": 4},
    ],
}

SURVEYS = {"U26OS0101": [{"sulpapernm": "중간 강의 설문", "sulstart": "2026-11-02", "sulend": "2026-11-08", "appcnt": 0}]}

DISCUSSIONS = {
    "U26ET0101": [{"title": "AI 윤리 토론: 자율주행차의 딜레마", "started": "2026-11-02 00:00:00",
                   "ended": "2026-11-09 23:59:59", "toroncnt": 12}],
}


def course_home(subj: str) -> dict:
    tasks = TASKS.get(subj, [])
    quizzes = QUIZZES.get(subj, [])
    return {"taskCnt": len(tasks), "taskPrsntCnt": sum(t["submityn"] == "Y" for t in tasks), "taskNewCnt": 0,
            "quizCnt": len(quizzes), "quizPrsntCnt": sum(q["issubmit"] == "Y" for q in quizzes), "quizNewCnt": 0,
            "examCnt": len(ONLINE_TESTS.get(subj, [])), "examPrsntCnt": sum(t["issubmit"] == "Y" for t in ONLINE_TESTS.get(subj, [])),
            "examNewCnt": 0, "prjctCnt": len(PROJECTS.get(subj, [])), "prjctPrsntCnt": 0, "prjctNewCnt": 0,
            "surveyCnt": len(SURVEYS.get(subj, [])), "surveyPrsntCnt": 0, "surveyNewCnt": 0,
            "dscsnCnt": len(DISCUSSIONS.get(subj, [])), "dscsnJoinCnt": 0, "dscsnNewCnt": 0,
            "pdsCnt": len(BOARDS.get(subj, {}).get("library", [])), "pdsNewCnt": 0,
            "cntntCmpltCnt": sum(1 for o in ONLINE.get(subj, []) if (o.get("prog") or 0) >= 100),
            "cntntList": [{} for o in ONLINE.get(subj, []) if not o.get("evltnSe")]}


def post(no: int, title: str, when: str, content: str, atch: str | None = None, top: bool = False) -> dict:
    return {"boardNo": no, "title": title, "registDt": f"{when}:00.000+09:00", "topAt": "Y" if top else "N",
            "fileCnt": 1 if atch else 0, "atchFileId": atch, "content": content, "updtDt": None}


BOARDS = {
    "U26DB0101": {
        "notice": [
            post(210, "기말고사 범위 및 일정 공지", "2026-11-04T15:00",
                 "<p>기말고사: 12월 14일(월) 3교시(12:00~13:15), 새빛관 203.</p><p>범위: 9주차~14주차 (정규화, 트랜잭션, "
                 "동시성 제어, 회복, 인덱스). 오픈북 아님, 계산기 불필요. 학생증 지참.</p>"),
            post(205, "과제 2 제출 형식 안내", "2026-10-28T11:00",
                 "<p>과제 2는 PDF 한 파일로 KLAS 과제 메뉴에 제출합니다. 자세한 형식은 첨부 파일을 보세요.</p>", "F-DB-P205"),
            post(198, "중간고사 성적 공개 및 열람 안내", "2026-10-27T17:00",
                 "<p>중간고사 점수는 KLAS 성적 메뉴가 아니라 이 글의 댓글 기간(10/29~10/30)에 연구실(새빛관 512)에서 열람합니다. "
                 "평균 61점.</p>"),
        ],
        "library": [
            post(211, "11주차 강의자료: 트랜잭션", "2026-11-06T09:00", "<p>11주차 슬라이드입니다.</p>"),
        ],
    },
    "U26OS0101": {
        "notice": [
            post(101, "[휴강] 11/10(화) 휴강 및 보강 안내", "2026-11-05T10:00",
                 "<p>11월 10일(화) 4교시 수업은 교수 학회 참석으로 휴강합니다.</p><p>보강: 11월 24일(화) 18:00~19:15, "
                 "새빛관 301. 출석은 보강 때 부릅니다.</p>"),
            post(95, "중간고사 점수 공개 및 이의신청", "2026-10-30T14:00",
                 "<p>중간고사 점수를 KLAS 공지 첨부로 올렸습니다. 이의신청은 11/3(화)까지 메일로 받습니다.</p>"),
            post(90, "결석 처리 기준 안내", "2026-09-03T09:00",
                 "<p>이 과목은 학칙에 따라 수업시간의 1/4 이상 결석하면 성적을 F로 처리합니다. 지각 3회는 결석 1회로 봅니다.</p>",
                 top=True),
        ],
        "library": [],
    },
    "U26ML0101": {
        "notice": [
            post(330, "강의실 변경 안내 (11/11부터)", "2026-11-06T09:30",
                 "<p>11월 11일(수) 수업부터 강의실이 한울관 B101에서 새빛관 B105로 바뀝니다. 학기 끝까지 적용됩니다.</p>"),
            post(325, "중간 대체 과제 및 기말 프로젝트 안내", "2026-10-20T13:00",
                 "<p>이 과목은 기말고사를 보지 않고 기말 팀 프로젝트로 대체합니다. 제안서 마감 11/14, 최종 발표 12/9(수) 수업 시간.</p>"),
        ],
        "library": [
            post(331, "10주차 강의자료 (결정트리)", "2026-11-03T20:00", "<p>10주차 슬라이드와 실습 코드 안내입니다.</p>", "F-ML-P331"),
        ],
    },
    "U26PS0101": {
        "notice": [
            post(412, "11/12(목) 비대면 수업 전환 안내", "2026-11-06T18:00",
                 "<p>11/12(목) 2교시 수업은 Zoom 실시간 비대면으로 진행합니다. 접속 링크는 수업 30분 전에 이 게시판에 올립니다. "
                 "출석은 Zoom 접속 기록으로 확인합니다.</p>"),
            post(405, "중간고사 결과 및 기말고사 범위", "2026-11-02T10:00",
                 "<p>기말고사: 12월 17일(목) 2교시(10:30~11:45), 비마관 405. 범위: 7장~11장. 공학용 계산기 허용.</p>"),
        ],
        "library": [],
    },
    "U26ET0101": {
        "notice": [
            post(515, "11/13(금) 수업 장소 변경 (하루만)", "2026-11-06T16:00",
                 "<p>11/13(금) 수업은 화도관 301 대신 화도관 104에서 합니다. 그 다음 주부터는 다시 301입니다.</p>"),
            post(510, "공결(출석 인정) 신청 방법", "2026-10-15T09:00",
                 "<p>질병·예비군 등 공결은 증빙서류를 사유 발생 후 1주일 안에 학과 사무실에 제출하세요. "
                 "KLAS에 반영되기까지 1~2주 걸립니다.</p>"),
        ],
        "library": [],
    },
    "U26AI0101": {
        "notice": [
            post(610, "11주차 온라인 강의 업로드 지연 안내", "2026-11-06T11:00",
                 "<p>11주차 강의는 11/10(화)에 올라갑니다. 수강 기간은 11/16(월) 23:59까지로 하루 늘렸습니다(KLAS 표시는 곧 수정).</p>"),
        ],
        "library": [],
    },
}

FILES = {
    "F-DB-T2": [{"fileName": "과제2_ERD_가이드.docx", "kind": "docx",
                 "text": ["도서관 대출 시스템 요구사항", "회원은 최대 5권까지 14일간 대출할 수 있다.",
                          "연체 시 연체일수만큼 대출이 정지된다.", "도서는 ISBN, 제목, 저자, 출판사, 소장 위치를 가진다.",
                          "평가: 엔터티 식별 40%, 관계·카디널리티 40%, 표기법 20%"]}],
    "F-DB-P205": [{"fileName": "과제2_제출형식.docx", "kind": "docx",
                   "text": ["과제 2 제출 형식", "PDF 1개, 20MB 이하, 파일명 학번_이름.pdf",
                            "ERD 도구는 자유(draw.io, ERDCloud 등). 손그림 스캔은 받지 않음.",
                            "표지 없이 1쪽부터 ERD, 2쪽에 가정(assumption) 목록."]}],
    "F-ML-P331": [{"fileName": "10주차_결정트리.pptx", "kind": "pptx",
                   "text": ["결정트리 (Decision Tree)", "엔트로피와 정보 이득", "ID3 / C4.5 / CART 비교",
                            "가지치기(pruning)로 과적합 줄이기", "실습 4: ID3 직접 구현 (11/10 마감)"]}],
}

SYLLABUS = {
    "U26DB0101": {"gwamokKname": "데이터베이스", "codeName1": "전필", "hakjumNum": 3, "memberName": "김교수", "jikgeubName": "교수",
                  "email": "prof-db@example.invalid", "telNo": "02-000-0001", "summary": "관계형 데이터베이스 설계와 SQL",
                  "purpose": "ER 모델링, 정규화, 트랜잭션 이해", "week1Lecture": "소개", "week2Lecture": "관계 모델",
                  "week3Lecture": "SQL 1", "week4Lecture": "SQL 2", "week5Lecture": "ER 모델", "week6Lecture": "ERD 실습",
                  "week7Lecture": "정규화 1", "week8Lecture": "중간고사", "week9Lecture": "정규화 2", "week10Lecture": "트랜잭션",
                  "week11Lecture": "동시성 제어", "week12Lecture": "회복", "week13Lecture": "인덱스", "week14Lecture": "질의 최적화",
                  "week15Lecture": "기말고사", "week16Lecture": "보강 주간", "attendBiyul": 10, "middleBiyul": 30,
                  "lastBiyul": 35, "reportBiyul": 25, "quizBiyul": None, "bookName": "Database System Concepts",
                  "writeName": "Silberschatz", "companyName": "McGraw-Hill", "printYear": "2019"},
    "U26OS0101": {"gwamokKname": "운영체제", "codeName1": "전필", "hakjumNum": 3, "memberName": "이교수", "jikgeubName": "교수",
                  "email": "prof-os@example.invalid", "telNo": "02-000-0002", "summary": "프로세스, 스케줄링, 메모리, 파일 시스템",
                  "week8Lecture": "중간고사", "week15Lecture": "기말고사", "week10Lecture": "CPU 스케줄링",
                  "attendBiyul": 10, "middleBiyul": 30, "lastBiyul": 30, "reportBiyul": 30,
                  "bigo": "결석이 수업시간의 1/4 이상이면 F", "bookName": "Operating System Concepts"},
    "U26ML0101": {"gwamokKname": "머신러닝", "codeName1": "전선", "hakjumNum": 3, "memberName": "박교수", "jikgeubName": "부교수",
                  "email": "prof-ml@example.invalid", "telNo": "02-000-0003", "summary": "지도학습과 비지도학습의 기초",
                  "week8Lecture": "중간 대체 과제", "week15Lecture": "기말 프로젝트 발표", "attendBiyul": 10, "middleBiyul": 20,
                  "lastBiyul": None, "reportBiyul": 30, "presentationBiyul": 20, "gitaBiyul": 20,
                  "gitaDetail": "기말 프로젝트 보고서", "bookName": "Hands-On Machine Learning"},
    "U26PS0101": {"gwamokKname": "확률과통계", "codeName1": "전선", "hakjumNum": 3, "memberName": "최교수", "jikgeubName": "교수",
                  "email": "prof-ps@example.invalid", "telNo": "02-000-0004", "summary": "확률 모형과 통계적 추론",
                  "week8Lecture": "중간고사", "week15Lecture": "기말고사", "attendBiyul": 10, "middleBiyul": 35,
                  "lastBiyul": 35, "reportBiyul": None, "quizBiyul": 20, "bookName": "확률과 통계"},
    "U26ET0101": {"gwamokKname": "현대사회와윤리", "codeName1": "교선", "hakjumNum": 3, "memberName": "정교수", "jikgeubName": "조교수",
                  "email": "prof-et@example.invalid", "telNo": "02-000-0005", "summary": "기술 사회의 윤리 쟁점 토론",
                  "week15Lecture": "기말 에세이 발표", "attendBiyul": 20, "middleBiyul": None, "lastBiyul": 30,
                  "reportBiyul": 30, "discussionBiyul": 20},
    "U26AI0101": {"gwamokKname": "AI와 데이터 리터러시", "codeName1": "교선", "hakjumNum": 3, "memberName": "한교수",
                  "jikgeubName": "교수", "email": "prof-ai@example.invalid", "summary": "100% 온라인 교양 강의",
                  "week8Lecture": "중간고사(온라인)", "week15Lecture": "기말고사(온라인)", "attendBiyul": 0, "middleBiyul": 40,
                  "lastBiyul": 40, "quizBiyul": 20},
}

# (year, term, course, category, credits, grade, retake)
GRADE_ROWS = [
    ("2024", "1", "대학영어", "교필", 3, "A0", "N"), ("2024", "1", "광운인되기", "교필", 1, "P", "N"),
    ("2024", "1", "미적분학1", "교선", 3, "B+", "N"), ("2024", "1", "프로그래밍기초", "전필", 3, "A+", "N"),
    ("2024", "1", "일반물리학1", "교선", 3, "C+", "N"), ("2024", "1", "정보융합개론", "전필", 3, "A0", "N"),
    ("2024", "2", "미적분학2", "교선", 3, "B0", "N"), ("2024", "2", "자료구조", "전필", 3, "B+", "N"),
    ("2024", "2", "일반물리학2", "교선", 3, "F", "N"), ("2024", "2", "이산수학", "전필", 3, "A0", "N"),
    ("2024", "2", "글쓰기와 표현", "교선", 3, "A+", "N"),
    ("2025", "1", "알고리즘", "전필", 3, "B0", "N"), ("2025", "1", "선형대수", "전선", 3, "A0", "N"),
    ("2025", "1", "컴퓨터구조", "전필", 3, "C+", "N"), ("2025", "1", "심리학의 이해", "교선", 3, "A+", "N"),
    ("2025", "1", "객체지향프로그래밍", "전필", 3, "B+", "N"),
    ("2025", "2", "데이터과학개론", "전선", 3, "A+", "N"), ("2025", "2", "시스템프로그래밍", "전선", 3, "B0", "N"),
    ("2025", "2", "경제학원론", "교선", 3, "B+", "N"), ("2025", "2", "통계학개론", "전선", 3, "D+", "N"),
    ("2025", "2", "웹프로그래밍", "전선", 3, "A0", "N"),
    ("2025", "4", "현대미술의 이해", "교선", 3, "A0", "N"),
    ("2026", "1", "컴퓨터네트워크", "전필", 3, "B+", "N"), ("2026", "1", "소프트웨어공학", "전선", 3, "A0", "N"),
    ("2026", "1", "인공지능", "전선", 3, "A+", "N"), ("2026", "1", "철학과 비판적 사고", "교선", 3, "B+", "N"),
    ("2026", "1", "컴퓨터구조", "전필", 3, "B+", "Y"),
] + [("2026", "2", name, cat, credits, "", "N") for _, name, _, _, cat, credits, _ in COURSES]

POINTS = {"A+": 4.5, "A0": 4.0, "B+": 3.5, "B0": 3.0, "C+": 2.5, "C0": 2.0, "D+": 1.5, "D0": 1.0, "F": 0.0}


def grades() -> list:
    terms: dict[tuple[str, str], list] = {}
    for year, term, course, cat, credits, grade, retake in GRADE_ROWS:
        terms.setdefault((year, term), []).append({"gwamokKname": course, "codeName1": cat, "hakjumNum": credits,
                                                   "getGrade": grade, "retakeOpt": retake})
    return [{"thisYear": y, "hakgi": t, "sungjukList": rows} for (y, t), rows in terms.items()]


def grade_totals() -> dict:
    done = [r for r in GRADE_ROWS if r[5]]
    # The 2025-1 컴퓨터구조 C+ was retaken in 2026-1: only the retake counts (KLAS drops the first attempt).
    counted = [r for r in done if not (r[2] == "컴퓨터구조" and r[0] == "2025")]
    earned = [r for r in counted if r[5] != "F"]
    graded = [r for r in counted if r[5] in POINTS]
    gpa = round(sum(POINTS[r[5]] * r[4] for r in graded) / sum(r[4] for r in graded), 2)
    major = lambda rows: sum(r[4] for r in rows if r[3].startswith("전"))
    culture = lambda rows: sum(r[4] for r in rows if r[3].startswith("교"))
    applied = counted + [r for r in GRADE_ROWS if not r[5]]
    return {"applyHakjum": sum(r[4] for r in applied), "majorApplyHakjum": major(applied), "cultureApplyHakjum": culture(applied),
            "etcApplyHakjum": 0, "chidukHakjum": sum(r[4] for r in earned), "majorChidukHakjum": major(earned),
            "cultureChidukHakjum": culture(earned), "etcChidukHakjum": 0, "delHakjum": 0, "majorDelHakjum": 0,
            "cultureDelHakjum": 0, "etcDelHakjum": 0, "hwakinScoresum": gpa, "jaechulScoresum": gpa}


def standing() -> list:
    out = []
    for (year, term), rank, of in ((("2024", "1"), 21, 88), (("2024", "2"), 47, 85), (("2025", "1"), 39, 83),
                                   (("2025", "2"), 30, 80), (("2026", "1"), 25, 82)):
        rows = [r for r in GRADE_ROWS if (r[0], r[1]) == (year, term) and r[5] in POINTS]
        point = round(sum(POINTS[r[5]] * r[4] for r in rows) / sum(r[4] for r in rows), 2)
        out.append({"thisYear": year, "hakgi": term, "applyHakjum": sum(r[4] for r in GRADE_ROWS if (r[0], r[1]) == (year, term)),
                    "applyPoint": point, "classOrder": rank, "manNum": of, "warningOpt": None, "pcnt": round(100 * rank / of, 1)})
    return out


def semesters() -> list:
    order = sorted({(r[0], r[1]) for r in GRADE_ROWS}, key=lambda k: (int(k[0]), {"1": 0, "3": 1, "2": 2, "4": 3}[k[1]]),
                   reverse=True)
    out = []
    for year, term in order:
        names = [r[2] for r in GRADE_ROWS if (r[0], r[1]) == (year, term)]
        label = f"{year}년도 {'여름' if term == '3' else '겨울' if term == '4' else term}학기"
        out.append({"value": f"{year},{term}", "label": label,
                    "subjList": [{"value": f"P{year}{term}{i:02d}", "label": n, "name": n} for i, n in enumerate(names)]})
    return out


def past_home(year: str, term: str) -> dict:
    rows = [r for r in GRADE_ROWS if (r[0], r[1]) == (year, term)]
    return {"yearhakgi": f"{year}학년도 {term}학기", "subjNotiList": [],
            "atnlcSbjectList": [{"subj": f"P{year}{term}{i:02d}", "yearhakgi": f"{year},{term}", "subjNm": r[2],
                                 "profNm": "담당교수", "lctrumSchdulInfo": "", "subjLabel": r[2]} for i, r in enumerate(rows)]}


def home() -> dict:
    noti = []
    for subj, name, *_ in COURSES:
        for board, label in (("notice", "강의 공지사항"), ("library", "강의 자료실")):
            for p in BOARDS[subj][board]:
                if p["registDt"] >= "2026-11-03":
                    noti.append({"subjNm": name, "typeNm": label, "title": p["title"], "registDt": p["registDt"]})
    noti.sort(key=lambda n: n["registDt"], reverse=True)
    return {"yearhakgi": "2026학년도 2학기", "subjNotiList": noti[:8],
            "atnlcSbjectList": [{"subj": subj, "yearhakgi": SEM, "subjNm": name, "profNm": prof, "lctrumSchdulInfo": sched,
                                 "subjLabel": LABEL[subj]} for subj, name, prof, sched, *_ in COURSES]}


def build() -> dict:
    homes = {SEM: home()}
    for year, term in {(r[0], r[1]) for r in GRADE_ROWS if f"{r[0]},{r[1]}" != SEM}:
        homes[f"{year},{term}"] = past_home(year, term)
    per_course = {
        "TASKS": TASKS, "ONLINE": ONLINE, "PROJECTS": PROJECTS, "QUIZZES": QUIZZES, "ONLINE_TESTS": ONLINE_TESTS,
        "SURVEYS": SURVEYS, "DISCUSSIONS": DISCUSSIONS, "SYLLABUS": {k: [v] for k, v in SYLLABUS.items()},
        "COURSE_HOME": {subj: course_home(subj) for subj, *_ in COURSES},
        "ATTENDANCE": {subj: attendance(subj, days, len(days) == 1) for subj, _, _, _, _, _, days in COURSES if days},
    }
    for subj, weeks in per_course["ATTENDANCE"].items():  # the course home repeats the e-attendance marks
        per_course["COURSE_HOME"][subj]["atendList"] = [
            {"attendancediv": w[f"attendancediv{i}"]} for w in weeks if w for i in range(1, 5) if w.get(f"attendancediv{i}")]
    return {
        "_about": "Synthetic KLAS answers for one made-up student (정보융합학부 2024학번, 3학년). No real person or data.",
        "now": NOW,
        "semesters": semesters(),
        "home": homes,
        "per_course": per_course,
        "task_view": TASK_VIEW,
        "boards": BOARDS,
        "files": FILES,
        "fixed": {
            "GRADES": grades(), "GRADE_TOTALS": grade_totals(), "STANDING": standing(),
            "STUDENT_RECORD": {"hakgwa": "정보융합학부", "hakbun": "2024000123", "grade": 3, "hakjukStatu": "재학",
                               "majorHakjum": 0, "cultureHakjum": 0, "generalHakjum": 0, "prevHakjumNum": 0},
            "GEN_ED": {"aa8128": 1, "aa62": 3, "aa64": 3, "aa63": 3, "aa76": 0, "aa65": 3, "aa66": 3, "aa67": 0,
                       "aa68": 3, "aa7881": 6},
            "GRADUATION_CHECK": None,
            "GRADE_TERM": {"termMap": None},
            "EVAL_TERM": None,
            "EVAL_COURSES": [],
            "SCHOLARSHIP_TERM": {"stats": False, "returnMsg": "장학금 신청 기간이 아닙니다.", "janghakApplyTerm": None},
            "DROP_CREDITS_TERM": {"stats": "N", "returnMsg": "취득학점포기 신청 기간이 아닙니다."},
            "SCHOLARSHIP_HISTORY": [
                {"yearHakgi": "2026-2", "grade": 3, "janghakName": "국가장학금(Ⅰ유형)", "janghakAmt": 1750000},
                {"yearHakgi": "2026-1", "grade": 3, "janghakName": "성적우수장학금(B)", "janghakAmt": 1000000},
                {"yearHakgi": "2026-1", "grade": 3, "janghakName": "국가장학금(Ⅰ유형)", "janghakAmt": 1750000},
                {"yearHakgi": "2025-2", "grade": 2, "janghakName": "교내근로장학금", "janghakAmt": 1200000},
                {"yearHakgi": "2025-2", "grade": 2, "janghakName": "국가장학금(Ⅰ유형)", "janghakAmt": 1750000},
            ],
        },
    }


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
