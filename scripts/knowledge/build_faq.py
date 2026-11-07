"""Q&A entries from the fetched sources, written and then checked by Claude, one category at a time.

Each category is two calls that share one cached prefix (system prompt, the two core regulations, the
category's own documents): a writer pass, then a reviewer pass that checks every claim against the same
documents and fixes or drops what they don't support.

    python build_faq.py --dry-run                 # prompt sizes and cost guess, no API call
    python build_faq.py --budget 45 [--only 수강신청 졸업] [--workers 4] [--skip-review]
    python build_faq.py --assemble                # out/faq-*.json -> src/kw_mcp/knowledge/faq.json
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import datetime
import json
import os
import re

from kbcommon import KNOWLEDGE, OUT, RAW, TEXT, dump_json, load_sources

CHECKED_AT = "2026-11-07"
CORE_DOCS = ["reg-hakchik", "reg-sihaeng"]
CONTACT_DOCS = ["web-team-edu", "web-team-student", "web-team-intl", "web-team-finance", "web-team-career"]
SLICES = {"web-info11": (1300, 34000), "web-info12": (0, 30000)}
MAX_DOC_CHARS = 45000

CATEGORIES = [
    ("수강신청", "enroll"), ("재수강·성적", "grade"), ("계절학기", "season"), ("수업·출석", "class"),
    ("학적변동", "status"), ("졸업", "grad"), ("다전공", "multi"), ("전과·전공배정", "transfer"),
    ("학점교류·교환학생", "exchange"), ("장학", "scholar"), ("등록·등록금", "tuition"),
    ("증명서·학생증", "cert"), ("기숙사", "dorm"), ("셔틀·교통", "shuttle"), ("도서관", "library"),
    ("학식·편의시설", "campus"), ("병무·예비군", "military"),
    # round 4 (everyday questions)
    ("IT·계정", "it"), ("상담·학생지원", "support"), ("진로·취업", "career"), ("동아리·학생자치", "club"),
    ("기타", "etc"),
]
PREFIX = dict(CATEGORIES)

TOPICS = [
    {"category": "수강신청", "n": 18,
     "docs": ["web-info13", "web-info03", "reg-221", "reg-90", "web-info01", "faq-34581", "faq-53053"],
     "questions": [
         "수강신청 최대 몇 학점까지 가능? 직전학기 성적 좋으면 더 들을 수 있나", "최소 몇 학점 신청해야 하나",
         "수강정정 기간에 뭐 할 수 있나, 정정 기간 놓치면?", "수강포기(수강철회) 언제까지, 몇 과목까지, 성적표에 남나",
         "수강신청 장바구니(희망과목) 제도 있나", "졸업학기 학생 최소 학점 예외", "타과 전공 과목 들으면 어떻게 인정되나",
         "선수과목 안 들으면 신청 못 하나", "초과 신청(학점 증가) 조건", "수강신청 프로그램 설치",
         "수강인원 제한·폐강 기준과 폐강 시 처리", "재학생이 대학원 과목 들을 수 있나(학석사 연계 제외)",
         "e러닝·원격수업 과목 학점 제한", "학년별 수강신청 일정은 어디서 보나", "4학년 9학기 등록 시 수강 학점"]},
    {"category": "재수강·성적", "n": 16,
     "docs": ["web-info05", "reg-211", "web-info01", "reg-221"],
     "questions": [
         "재수강하면 성적 최대 몇까지(A0? B+?)", "재수강 가능한 성적 기준(C+ 이하?)", "재수강하면 원래 성적은 지워지나",
         "재수강 횟수 제한", "절대평가/상대평가 비율", "P/F 과목은 평점에 들어가나", "성적 이의신청 언제 어떻게",
         "학사경고 기준과 몇 번이면 제적", "평점 계산법(4.5 만점)", "F 받으면 졸업학점에서 빠지나",
         "성적 포기 제도 있나", "백분율 환산 공식", "출석 미달이면 F인가", "학사경고 받으면 수강학점 제한"]},
    {"category": "계절학기", "n": 8,
     "docs": ["reg-188", "web-info03", "web-info13"],
     "questions": [
         "계절학기 최대 몇 학점", "계절학기 수강료 얼마/어떻게 내나", "계절학기 재수강 가능?",
         "계절학기 폐강 기준", "다른 학교 계절학기 들으면 인정되나", "계절학기 성적은 언제 반영", "휴학생도 계절학기 가능?"]},
    {"category": "수업·출석", "n": 8,
     "docs": ["reg-90", "web-info03", "faq-49939", "reg-87", "reg-218"],
     "questions": [
         "결석 몇 번이면 F", "공결(출석 인정) 받는 법: 예비군, 경조사, 질병, 취업면접", "출석부·학생증 사진 변경",
         "원격수업 출석 인정 기준", "현장실습학기제 학점 인정", "창업하면 학점 인정이나 휴학 특례 있나",
         "시험 기간 결시하면 어떻게 하나"]},
    {"category": "학적변동", "n": 16,
     "docs": ["web-info08", "faq-34897", "faq-52309", "faq-774", "web-info07", "reg-230"],
     "questions": [
         "휴학 최대 몇 학기, 한 번에 몇 학기", "신입생 첫 학기 휴학 가능?", "군휴학 절차와 기간", "휴학 신청 기간 지나면?",
         "휴학하면 등록금 반환되나(시기별)", "복학 신청 언제 어떻게", "자퇴 절차·서류", "자퇴 후 재입학 가능?",
         "제적 사유(미등록, 학사경고 등)", "질병휴학·임신출산육아 휴학", "창업휴학", "학적부 정정 신청",
         "휴학 중 계절학기·다전공 신청 가능?", "미복학하면 어떻게 되나"]},
    {"category": "졸업", "n": 18,
     "docs": ["web-info07", "web-info12", "reg-early-grad", "faq-829", "faq-782", "annex-hakchik-6"],
     "questions": [
         "졸업학점 몇 학점(학과별)", "졸업요건 뭐뭐 있나(학점, 논문, 필수과목)", "졸업논문/졸업작품 대체", "졸업유예(졸업연기) 신청 조건·비용",
         "졸업유예하면 등록금 내야 하나", "조기졸업 조건(평점, 학기)", "수료와 졸업 차이", "초과학기(9학기) 등록금",
         "편입생 졸업요건", "학위 수여 시기(2월, 8월)", "교양 몇 학점 들어야 하나(입학연도별)", "광운인되기 꼭 들어야 하나",
         "영어졸업인증 있나", "졸업 전 다전공 포기하고 졸업 가능?", "졸업사정 결과는 어디서 확인"]},
    {"category": "다전공", "n": 22,
     "docs": ["web-info11", "reg-damajor-isu", "reg-damajor-unyeong", "annex-damajor-1"],
     "questions": [
         "복수전공 신청 자격·시기", "부전공 몇 학점", "복수전공 몇 학점", "연계전공이 뭐고 몇 학점", "마이크로전공 몇 학점, 몇 개까지",
         "다전공 의무(2025학번부터) 예외 대상", "다전공 포기(취소) 방법과 시기", "다전공 상호인정 몇 학점까지",
         "다전공 하면 주전공 학점 줄어드나", "학생설계융합전공 절차", "심화전공이 뭐냐", "다전공 신청 기간(연 몇 번)",
         "마이크로전공 학점을 주전공으로도 인정?", "다전공 이수 못하면 졸업 못하나", "연계전공 학위명",
         "복수전공 필수과목도 들어야 하나", "다전공 최대 몇 개", "건축학과 복수전공", "체육특기자 복수전공"]},
    {"category": "전과·전공배정", "n": 8,
     "docs": ["reg-89", "web-info04"],
     "questions": [
         "전과 신청 자격(학년, 평점)", "전과 시기와 절차", "전과하면 이전 학점 어떻게 인정", "전과 제한 학과(정원 등)",
         "자율전공학부 전공배정 언제/어떻게", "학부 내 전공배정 기준", "전과 몇 번까지"]},
    {"category": "학점교류·교환학생", "n": 12,
     "docs": ["reg-223", "reg-79", "oia-outbound", "web-info09"],
     "questions": [
         "학점교류 가능한 학교와 최대 학점", "학점교류 신청 절차", "교환학생 지원 자격(학점, 어학)",
         "교환학생 가서 딴 학점 인정 방식", "교환학생 등록금 어디에 내나", "교환학생 다녀오면 졸업 늦어지나",
         "단기연수 학점 인정", "학점교류로 들은 과목 성적 평점 반영?", "방학 중 타대학 수강"]},
    {"category": "장학", "n": 22,
     "docs": ["web-summary", "web-scholar01", "web-scholar02", "web-scholar03", "reg-114", "web-team-student", "faq-783"],
     "questions": [
         "성적장학금 기준(평점, 이수학점)", "국가장학금 신청 시기와 소득구간", "교내·교외장학 중복 수혜 되나",
         "장학금 받으려면 최소 몇 학점 들어야", "근로장학 신청", "가계곤란 장학", "신입생 장학", "장학금 환수되는 경우",
         "외부(교외) 장학 공고 어디서 보나", "국가장학금 2유형", "다자녀 장학", "휴학하면 장학금 이월되나",
         "직전학기 학사경고면 장학 제외?", "보훈·장애 장학", "등록금 범위 초과 수혜 시 처리", "장학 문의처"]},
    {"category": "등록·등록금", "n": 10,
     "docs": ["web-team-finance", "faq-779", "faq-781", "faq-780", "faq-783", "faq-782", "web-info07", "reg-230"],
     "questions": [
         "등록금 분할납부(분납) 가능? 몇 회", "등록금 납부 기간 놓치면", "등록금 고지서 어디서 출력",
         "초과학기 등록금 학점별 금액", "휴학 시 등록금 반환 기준", "졸업유예 등록금", "등록금 카드 납부", "학자금 대출"]},
    {"category": "증명서·학생증", "n": 12,
     "docs": ["web-cert01", "web-cert02", "web-cert06", "web-cert07", "web-studentid", "web-isic", "reg-229"],
     "questions": [
         "재학증명서 인터넷 발급", "졸업증명서 영문 발급", "증명서 자동발급기 위치·시간", "증명서 발급 수수료",
         "학생증 발급/재발급 방법", "모바일 학생증", "국제학생증(ISIC) 발급", "성적증명서 우편 발송", "휴학증명서"]},
    {"category": "기숙사", "n": 8, "docs": ["web-dorm", "web-team-intl"],
     "questions": ["기숙사 신청 시기와 방법", "기숙사비", "기숙사 선발 기준(거리, 성적)", "기숙사 위치·호실 구성",
                   "기숙사 문의처", "방학 중 기숙사", "기숙사 퇴사·환불"]},
    {"category": "셔틀·교통", "n": 5, "docs": ["web-directions", "web-tour02", "faq-750"],
     "questions": ["셔틀버스 노선과 시간", "광운대역에서 학교 가는 법", "주차", "셔틀 정보가 최신인가"]},
    {"category": "도서관", "n": 8, "docs": ["web-facility03", "web-facility07", "web-facility01"],
     "questions": ["도서관 운영시간", "열람실 좌석 예약", "도서 대출 권수·기간", "졸업생·휴학생 도서관 이용",
                   "스터디룸 예약", "타 대학 도서 상호대차", "전산실(컴퓨터실) 이용"]},
    {"category": "학식·편의시설", "n": 8,
     "docs": ["web-facility11", "web-facility01", "web-facility09", "web-facility12", "web-counsel"],
     "questions": ["학식 메뉴·가격·운영시간", "천원의 아침밥", "교내 편의점·카페·서점", "와이파이 접속 방법",
                   "학생상담실 이용", "보건실", "체력단련실"]},
    {"category": "병무·예비군", "n": 7, "docs": ["web-military", "web-military01", "faq-791", "faq-776", "faq-775", "faq-774", "faq-53053"],
     "questions": ["입영 연기(재학생 입영연기) 신청", "예비군 훈련 공결", "군휴학 후 복학", "군 복무 중 e러닝 학점 인정",
                   "병무 문의처", "전역 후 복학 시기"]},
]

# Second round: what the first pass listed under gaps, with the documents fetched for it, plus 기타.
SUPPLEMENTS = [
    {"category": "수업·출석", "n": 6, "docs": ["reg-90", "annex-class-3", "annex-class-4", "reg-78", "web-info03"],
     "questions": ["가족 상·결혼·입원·출산 같은 유고결석은 며칠까지 인정되고 무슨 서류 내나", "전염병 격리 결석",
                   "한 과목 수강인원 최대 몇 명", "폐강 기준 인원(몇 명 미만이면 폐강)", "폐강되면 어떻게 하나",
                   "취업 면접 결석"]},
    {"category": "전과·전공배정", "n": 5, "docs": ["reg-189", "web-info04", "reg-89"],
     "questions": ["자율전공학부는 언제 전공 고르나", "자율전공학부에서 못 가는 학과 있나", "자율전공학부 전공 선택 기준",
                   "자율전공학부 학생도 다전공 해야 하나", "자율전공학부 교양 이수 기준"]},
    {"category": "장학", "n": 6, "docs": ["annex-scholar-1", "reg-114", "web-scholar01", "web-summary"],
     "questions": ["수석·참빛·비마 장학금 기준과 금액 차이", "가정형편 장학(화도·동해) 조건", "봉사 장학(프론티어) 조건",
                   "장학금 받으려면 직전학기 몇 학점·평점", "장학 규정상 장학금 종류 전체 목록"]},
    {"category": "기타", "n": 10,
     "docs": ["reg-218", "reg-87", "web-counsel", "web-facility07", "web-isic", "web-team-career"],
     "questions": ["창업휴학 몇 학기까지, 서류", "창업하면 학점으로 인정해 주나(창업대체학점)", "현장실습 학기제 학점 몇 학점",
                   "현장실습 신청 자격과 기간", "학생상담실 상담 받는 법, 비용", "교내 컴퓨터실·프린트",
                   "취업 상담·경력개발팀 프로그램", "현장실습 문의처"]},
]

# Third round: topics the first eval round found thin (휴학·복학, 등록금 반환, 국가장학금 환수, 출석·공결, 근로장학,
# graduation.json rules, campus links). It may also return existing entries with added detail (same id).
ROUND3 = [
    {"category": "학적변동", "n": 10,
     "docs": ["web-info08", "reg-188", "reg-218", "reg-230", "faq-774", "faq-34897", "notice-52788", "faq-52309"],
     "questions": ["휴학 종류별(일반·군입대·창업·질병·임신출산육아) 최대 기간과 횟수", "휴학 신청 KLAS 경로와 서류",
                   "휴학 중에 계절학기 들을 수 있나", "복학 종류(일반·월반·유급)와 신청 방법·시기",
                   "군 제대 후 복학 서류, 개강 후 몇 주까지 전역하면 복학 가능", "휴학·복학 신청이 처리됐는지 확인하는 법",
                   "복학하면 해야 할 일(수강신청·등록금·예비군)", "휴학 중 등록금 납부·도서 반납", "재입학 자격과 시기"]},
    {"category": "등록·등록금", "n": 5, "docs": ["reg-230", "faq-781", "web-info08", "faq-783", "web-team-finance"],
     "questions": ["휴학하면 등록금 언제 얼마 돌려받나(시기별)", "자퇴하면 등록금 반환 비율", "군휴학 등록금 처리",
                   "등록금 반환 신청 방법과 계좌", "수업료와 입학금 반환 차이"]},
    {"category": "장학", "n": 6,
     "docs": ["notice-53624", "notice-53561", "web-scholar01", "web-scholar02", "web-summary", "reg-114",
              "web-team-student"],
     "questions": ["휴학·자퇴하면 국가장학금 토해내야 하나(환수)", "국가장학금 결격사유와 반환·제재부가금",
                   "국가장학금 선발 결과·지급일 확인 방법", "국가장학금 지급 방식(고지서 감면·계좌·대출상환)",
                   "근로장학 신청 방법과 담당 부서", "화도·동해장학금 2차 신청 대상"]},
    {"category": "수업·출석", "n": 8,
     "docs": ["notice-53077", "reg-90", "annex-class-4", "notice-53083", "notice-53449", "web-info05",
              "faq-49939", "web-info03"],
     "questions": ["몇 번 결석하면 F(1/4 규정)", "공결 인정 사유와 서류", "유고결석 출석인정 신청 절차와 제출처·기한",
                   "공결·유고결석 인정 안 되는 경우(면접·코로나 등)", "출석 정정은 어떻게 하나",
                   "예비군 훈련 출석 처리", "조기취업 출석 인정", "과목마다 출석 규정이 다른가(강의계획서)"]},
    {"category": "재수강·성적", "n": 6,
     "docs": ["notice-53174", "notice-53320", "notice-52850", "reg-221", "web-info05", "faq-53053"],
     "questions": ["취득학점 포기 대상(폐지된 과목만)과 절차·기간", "수강과목 포기 기간·방법", "재수강 제한(과목 수·성적)",
                   "성적 확인과 성적증명서 발급", "군 e-러닝 학점 인정 한도"]},
    {"category": "졸업", "n": 4, "docs": ["notice-53138", "reg-early-grad", "web-info07", "faq-829"],
     "questions": ["조기졸업 기준(평점·학점·학기)", "조기졸업·졸업연기 신청 기간과 방법", "졸업연기 대상과 비용"]},
    {"category": "계절학기", "n": 4, "docs": ["reg-188", "notice-53557", "web-info03"],
     "questions": ["계절학기 최대 학점(6학점)", "겨울 계절학기 타대학 학점교류 신청", "휴학생 계절학기 수강"]},
    {"category": "기숙사", "n": 5, "docs": ["dorm-admission", "dorm-apply", "dorm-contact", "web-dorm"],
     "questions": ["기숙사 공지·입사 안내는 어디서 보나", "입사 신청 절차(온라인 단계)", "입사할 때 필요한 서류(폐결핵 검사)",
                   "기숙사 반입 금지 물품", "기숙사 행정실·관리사무실 전화번호와 운영시간"]},
    {"category": "도서관", "n": 3, "docs": ["seat-status", "web-facility03"],
     "questions": ["열람실 남은 좌석 실시간으로 어디서 봄", "열람실 몇 개, 좌석 몇 석", "도서관 홈페이지 주소"]},
    {"category": "셔틀·교통", "n": 2, "docs": ["web-directions", "web-tour02", "faq-750"],
     "questions": ["셔틀버스 시간표와 정보 날짜(최신인지)", "셔틀 타는 곳"]},
]

# Fourth round: everyday questions (IT and accounts, 학생증, support centres, facilities, careers, clubs, and the
# 수강신청 gaps), with entries from other categories that already touch them passed as `related`.
ROUND4 = [
    {"category": "IT·계정", "n": 10,
     "docs": ["web-facility07", "web-facility12", "notice-53458", "notice-53457", "notice-53483", "faq-755",
              "web-team-it", "web-team-network"],
     "related": ["campus-wifi-access", "library-it-support", "etc-it-webmail-registration"],
     "questions": ["학교 이메일(@kw.ac.kr) 만드는 법", "Office 365 학생도 무료로 쓸 수 있나, 신청 자격", "와이파이 이름·비번·접속법",
                   "eduroam 되나", "KLAS 비밀번호 잊어버림", "해외에서 KLAS 로그인할 때 2차 인증", "졸업하면 KLAS 로그인 되나",
                   "학교가 주는 소프트웨어(한글, MATLAB, 백신 등)", "어도비 학교 라이선스 있나", "인터넷·와이파이 장애 문의처"]},
    {"category": "증명서·학생증", "n": 4, "docs": ["web-studentid", "faq-49939", "web-isic", "web-cert01"],
     "questions": ["학생증 처음 발급·재발급(분실) 방법", "모바일 학생증(QR) 쓰는 법", "학생증 사진 바꾸기", "학생증으로 뭐 할 수 있나"]},
    {"category": "상담·학생지원", "n": 8,
     "docs": ["web-counsel", "web-humanrights", "web-disability", "web-team-student", "notice-53549", "notice-53505",
              "notice-52442", "web-facility01"],
     "related": ["campus-student-counseling", "campus-health-center"],
     "questions": ["학생상담실 상담 예약 방법·비용·위치", "인권·성평등 상담(성희롱·성폭력) 어디에", "장애학생 지원 내용(우선수강신청 등)",
                   "보건실 위치·전화", "폭력예방교육 꼭 들어야 하나", "심리검사·해석상담 프로그램"]},
    {"category": "학식·편의시설", "n": 8,
     "docs": ["web-facility10", "notice-53558", "web-facility09", "web-facility11", "web-facility01", "web-facility03",
              "notice-53599", "notice-53462", "web-team-sports", "web-team-general", "web-team-facility"],
     "questions": ["풋살장·농구장 예약 방법과 시간", "스터디룸·세미나실 예약", "체육시설 이용", "학교 주차(출입구·통제)",
                   "분실물 어디서 찾나", "편의점·카페·서점 운영시간", "함지마루 말고 다른 학생식당", "학생회관에 뭐 있나"]},
    {"category": "진로·취업", "n": 9,
     "docs": ["job-counsel-info", "job-program-intro", "job-notice-12476", "job-51947", "job-home", "web-team-career",
              "internship-home", "reg-87", "web-team-internship"],
     "related": ["etc-career-center", "etc-field-practice-contact", "class-field-practice-credit"],
     "questions": ["진로·취업 상담 예약 방법", "취업 프로그램 종류(이력서 클리닉, 면접캠프 등)", "채용공고 어디서 봄(인스타그램)",
                   "현장실습 학점 인정", "현장실습 문의처", "진로·취업 교과목", "졸업생도 취업상담 되나", "국민취업지원제도"]},
    {"category": "동아리·학생자치", "n": 6, "docs": ["web-activity01", "web-activity02", "web-activity03", "web-team-student"],
     "questions": ["동아리 가입·등록 방법", "중앙동아리 목록과 동아리방 위치", "총학생회 연락처·홈페이지", "총동아리연합회 연락처",
                   "학생회비 내야 하나, 어디에 쓰나", "동아리 활동 장소 빌리기"]},
    {"category": "수강신청", "n": 5,
     "docs": ["notice-52981", "notice-52920", "notice-52987", "dept-electric-852", "reg-221", "reg-78", "web-info13"],
     "questions": ["수강신청 장바구니(희망과목) 있나", "선수과목 안 듣고 후수과목 들으면?", "학부생이 대학원 과목 들을 수 있나(학석사연계)",
                   "폐강 기준", "수강신청자료집·강의시간표 어디서"]},
]

# Fifth round: the language requirement, the items earlier rounds could not source, and thin topics. Update mode:
# an entry that keeps an existing id replaces it; `related` lists entries in other categories that touch it.
ROUND5 = [
    {"category": "졸업", "n": 2,
     "docs": ["web-info07", "web-info08", "reg-272", "web-team-intl", "reg-79", "annex-hakchik-6"],
     "related": ["grad-foreign-topik"],
     "questions": ["졸업하려면 토익 필요해? 영어 점수 졸업요건 있어?",
                   "KLAS 졸업사정 화면에 어학이 '대상'이라고 뜨는데 뭐야, 뭘 확인해야 돼?",
                   "공학인증(공학프로그램)이면 영어 성적 따로 내야 해?", "외국인 유학생은 TOPIK 몇 급 있어야 졸업?"]},
    # second pass on the same category (own output file): the first one listed the KLAS question as a gap
    {"category": "졸업", "n": 1, "suffix": "-extra5b",
     "docs": ["web-info07", "web-info08", "reg-272", "web-team-intl", "reg-79", "annex-hakchik-6"],
     "questions": [("KLAS 졸업사정 화면에 어학 항목이 '대상'이라고 떠. 토익 내야 돼? Answer with what the documents settle "
                   "(no school-wide English requirement since 2015-02 graduates; TOPIK 4급 for foreign students "
                   "admitted from 2020-2; programme rules in each 학과 내규) and tell the student what to check and "
                   "where: their own student type, their 학과 사무실 for 학과/공학프로그램 내규, and 교육지원팀 for what "
                   "the KLAS item means. Do not guess what the KLAS screen means. Prefer updating "
                   "grad-english-certification (add these questions) over a new entry.")]},
    {"category": "IT·계정", "n": 2,
     "docs": ["web-facility07", "web-facility12", "notice-53458", "office365-home", "faq-755", "web-team-it",
              "web-team-network"],
     "related": ["campus-wifi-access"],
     "questions": ["Office 365 어디서 신청해? 주소 직접 치면 막히던데", "eduroam 되나"]},
    {"category": "학식·편의시설", "n": 4,
     "docs": ["web-facility11", "notice-53200", "notice-53200-image", "web-facility09", "web-facility01",
              "council-lost-found", "council-notices", "web-team-student", "web-tour01", "notices-student-1"],
     "questions": ["함지마루 몇 시까지 해? 저녁도 팔아?", "학교에 다른 식당·카페·편의점 있어? 몇 시까지?",
                   "분실물 어디서 찾아?", "학생회관(복지관)에 뭐 있어?"]},
    {"category": "동아리·학생자치", "n": 3,
     "docs": ["web-activity01", "web-activity02", "web-activity03", "council-home", "council-notices",
              "council-student-fee", "council-fee-check", "web-team-student"],
     "questions": ["학생회비(자율적학생경비) 얼마고 어떻게 내? 냈는지 어디서 확인해?", "동아리 새로 등록하려면 어떻게 해?",
                   "중앙동아리 가입은 언제 어떻게?"]},
    {"category": "수강신청", "n": 3,
     "docs": ["notice-52920", "notice-52981", "web-info13", "notices-haksa-2", "reg-221", "notice-52987"],
     "questions": ["다음 학기 수강신청 언제야? 어디 올라와?", "수강신청 장바구니(희망과목 담기) 있어?",
                   "수강신청 공고 제목 뭐로 검색하면 돼?"]},
    {"category": "상담·학생지원", "n": 2,
     "docs": ["sangdam-notice", "web-counsel", "web-humanrights"],
     "related": ["campus-student-counseling"],
     "questions": ["학생상담실 상담 예약 어떻게 해? 온라인 신청 돼?", "학생상담실 운영시간이랑 비용"]},
    {"category": "계절학기", "n": 1, "docs": ["reg-188", "notice-53174", "web-info03", "notice-53561"],
     "related": ["status-leave-cancel"],
     "questions": ["휴학 중에 계절학기 들을 수 있어?", "휴학생이 계절 들으면 꼭 복학해야 돼?"]},
    {"category": "다전공", "n": 4,
     "docs": ["reg-damajor-isu", "reg-damajor-unyeong", "web-info11", "annex-damajor-1"],
     "questions": ["부전공 포기(취소)하면 들은 과목 어떻게 돼?", "졸업 때까지 부전공 학점 못 채우면?",
                   "다전공 상호인정 유형별로 몇 학점까지? 마이크로전공도 돼?", "다전공 신청 전에 들은 과목도 인정돼?",
                   "복전 포기하고 부전공으로 바꿀 수 있어?"]},
]

# Low-confidence entries are re-checked against the documents they cite plus these pages fetched since.
REVERIFY_DOCS = {"진로·취업": ["job-notice-12624"], "IT·계정": ["office365-home"]}

# The Daple snapshot is not a document Claude sees, so a re-check would otherwise drop it as an unknown source.
KEEP_DAPLE = " Keep a daple-snapshot source (and the Daple link) wherever an entry already has one."

PERSON_PATTERNS = [
    re.compile(r"[가-힣]{2,4}\s?(교수님?|선생님|팀장님?|과장|계장|주임|조교|대리)(?![가-힣])"),
    re.compile(r"(담당자|담당)\s?[:：]?\s?[가-힣]{2,4}\s?(\(|0\d)"),
]

SYSTEM = """You build a Korean FAQ knowledge base for 광운대학교(Kwangwoon University) undergraduates. The source
documents are official public pages and regulations, all checked on 2026-11-07 (today).

Rules for every entry:
- Use only the supplied documents. Never invent dates, amounts, credit limits, phone numbers, URLs or menu
  paths. If the documents don't settle a question, leave it out and list it under gaps, or answer only the part
  they do settle and say what to confirm with which office.
- answer: Korean 합니다체, concise (2-5 sentences), actionable. Lead with the direct answer (the number, the
  yes/no, the deadline rule).
- Paraphrase. At most one verbatim quote per entry, under 15 words, and only in a source's `quote` field.
- No personal names of anyone (staff, professors, students). Offices by name, main numbers only, and only numbers
  that appear in the documents.
- questions: 3-6 ways a student would actually type it on Everytime: casual, short, 반말 and 줄임말 are fine
  (e.g. "재수강하면 성적 몇까지 받음?", "계절학기 최대 몇 학점임?", "휴학 몇 번까지 됨?"). Vary the wording and
  keywords so a keyword search finds the entry.
- conditions_exceptions: the conditions, limits and exceptions that change the answer (admission year, student
  type, transfer students, architecture's 5-year program, etc.). Empty list if none.
- how_to: where to do it - the KLAS menu path or the office/online route exactly as the documents give it. If
  the documents give no path, say which office to ask.
- contact_office: the office that handles it, with its main number from the documents ("" if not given).
- sources: every document the answer rests on, by source_id, with the article (제n조 제n항, or the page section)
  in `article`. quote: "" unless you use the one short quote.
- applies_to: which admission years / student types the rule covers ("전체 학부생", "2025학번 이후", ...).
- confidence: high = stated directly in a current regulation or official page and unambiguous; medium = stated
  but possibly outdated, or needs a small inference; low = sources conflict or the answer is partly inferred.
- disagreement: when two documents (or a page and a regulation, or two revisions) say different things, describe
  both in one or two sentences and lower confidence. Never pick one silently. "" if none.
- Where a rule depends on admission year, say which years; current rules are 2026학년도 unless stated.
- id: "<prefix>-<short-english-slug>", lowercase, unique, e.g. "grade-retake-cap"."""

ENTRY_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "questions": {"type": "array", "items": {"type": "string"}},
        "answer": {"type": "string"},
        "conditions_exceptions": {"type": "array", "items": {"type": "string"}},
        "how_to": {"type": "string"},
        "contact_office": {"type": "object", "properties": {"name": {"type": "string"}, "phone": {"type": "string"}},
                           "required": ["name", "phone"], "additionalProperties": False},
        "sources": {"type": "array", "items": {
            "type": "object",
            "properties": {"source_id": {"type": "string"}, "article": {"type": "string"},
                           "quote": {"type": "string"}},
            "required": ["source_id", "article", "quote"], "additionalProperties": False}},
        "applies_to": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "disagreement": {"type": "string"},
    },
    "required": ["id", "questions", "answer", "conditions_exceptions", "how_to", "contact_office", "sources",
                 "applies_to", "confidence", "disagreement"],
    "additionalProperties": False,
}


def _schema() -> dict:
    """One schema for every call. It is part of the cached prompt prefix, so a per-call schema (an enum of
    that category's source ids, or extra fields for the reviewer) would stop every cache hit. Source ids are
    checked locally in assemble() instead."""
    return {"type": "object", "properties": {
        "entries": {"type": "array", "items": ENTRY_SCHEMA},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "dropped": {"type": "array", "items": {
            "type": "object", "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["id", "reason"], "additionalProperties": False}},
        "changes": {"type": "array", "items": {"type": "string"}}},
        "required": ["entries", "gaps", "dropped", "changes"], "additionalProperties": False}


NAME_COLUMNS = ("성명", "직위", "이메일", "E-mail", "e-mail")


def scrub_people(text: str) -> str:
    """Staff tables keep 담당업무·소속·전화 and lose 성명·직위·이메일; stray e-mail addresses are removed."""
    out, header_cols, keep = [], None, None
    for line in text.split("\n"):
        if line == "[표]":
            header_cols = keep = None
            out.append(line)
            continue
        if line == "[표 끝]":
            header_cols = keep = None
            out.append(line)
            continue
        cells = [c.strip() for c in line.split("|")] if "|" in line else [line]
        if header_cols is None and len(cells) > 1 and any(c in NAME_COLUMNS for c in cells):
            header_cols = cells
            keep = [i for i, c in enumerate(cells) if c not in NAME_COLUMNS]
            out.append(" | ".join(cells[i] for i in keep))
            continue
        if keep is not None and len(cells) == len(header_cols):
            out.append(" | ".join(cells[i] for i in keep))
            continue
        out.append(line)
    return re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "", "\n".join(out))


def doc_text(sid: str) -> str | None:
    p = TEXT / f"{sid}.txt"
    if not p.exists():
        return None
    t = p.read_text(encoding="utf-8")
    t = scrub_people(t.replace('id="jwxe_main_content">', "").strip())
    if sid in SLICES:
        a, b = SLICES[sid]
        t = t[a:b]
    if len(t) > MAX_DOC_CHARS:
        t = t[:MAX_DOC_CHARS] + "\n…(이하 생략)"
    return t


def _image(sid: str) -> dict | None:
    path = next((p for p in RAW.glob(f"{sid}.*") if p.suffix in (".png", ".jpg")), None)
    if path is None:
        return None
    media = "image/png" if path.suffix == ".png" else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media,
                                        "data": base64.b64encode(path.read_bytes()).decode()}}


def _docs(ids: list[str], titles: dict[str, str], cache_last: bool) -> tuple[list[dict], list[str]]:
    from claude_client import doc_block
    blocks, used = [], []
    for sid in ids:
        t = doc_text(sid)
        if t is None and (img := _image(sid)):  # a notice whose body is a poster image
            blocks += [{"type": "text", "text": f"[{sid}] {titles.get(sid, sid)} (이미지)"}, img]
            used.append(sid)
            continue
        if not t or t.startswith("(읽지 못함"):
            continue
        blocks.append(doc_block(f"[{sid}] {titles.get(sid, sid)}", t))
        used.append(sid)
    if cache_last and blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks, used


def _prefix(topic: dict, titles: dict[str, str]) -> tuple[list[dict], list[str]]:
    core, core_ids = _docs(CORE_DOCS + CONTACT_DOCS, titles, cache_last=True)
    own_ids = [d for d in topic["docs"] if d not in core_ids]
    own, own_used = _docs(own_ids, titles, cache_last=True)
    return core + own, core_ids + own_used


def entry_files(prefix: str) -> list:
    """The category's entry files: the first pass, then every later round (faq-<prefix>-extra*.json)."""
    later = [p for p in sorted(OUT.glob(f"faq-{prefix}-extra*.json"))
             if not p.stem.endswith(("-draft", "-review", "-audit"))]
    return [p for p in [OUT / f"faq-{prefix}.json", *later] if p.exists()]


def _existing(cat: str, full: bool = False) -> list[dict]:
    out = []
    for p in entry_files(PREFIX[cat]):
        for e in json.loads(p.read_text(encoding="utf-8"))["entries"]:
            out.append(e if full else {"id": e["id"], "questions": e["questions"]})
    return out


def _related(ids: list[str]) -> list[dict]:
    out = []
    for c, prefix in CATEGORIES:
        for p in entry_files(prefix):
            for e in json.loads(p.read_text(encoding="utf-8"))["entries"]:
                if e["id"] in ids:
                    out.append({"id": e["id"], "category": c, "questions": e["questions"], "answer": e["answer"]})
    return out


def run_topic(topic: dict, titles: dict[str, str], budget: float, review: bool = True, suffix: str = "",
              update: bool = False) -> dict:
    from claude_client import call
    cat, prefix = topic["category"], PREFIX[topic["category"]]
    content, ids = _prefix(topic, titles)
    qs = "\n".join(f"- {q}" for q in topic["questions"])
    have = _existing(cat, full=update) if suffix else []
    related = _related(topic.get("related", []))
    elsewhere = ("\nThese entries already answer nearby questions in other categories. Do not repeat them; if one of "
                 "your entries fully covers one of them, put that old id in `dropped` with the reason:\n"
                 + json.dumps(related, ensure_ascii=False)) if related else ""
    if update:
        avoid = ("\nThese entries already exist in this category. Where the documents above add to or correct one of "
                 "them, return it in full with the same id; otherwise write new entries with new ids. Do not repeat "
                 "an existing entry unchanged:\n" + json.dumps(have, ensure_ascii=False)) if have else ""
    else:
        avoid = ("\nThese entries already exist in this category; do not repeat them, write only new ones (new "
                 "ids):\n" + json.dumps(have, ensure_ascii=False)) if have else ""
    ask = (f"Category: {cat} (id prefix: {prefix}). Write about {topic['n']} entries.{avoid}{elsewhere}\n"
           f"Cover these student questions (merge questions that share one answer; skip any the documents "
           f"can't answer and list it under gaps):\n{qs}\n"
           f"Then add entries for other points in these documents that students often ask about and the list "
           f"misses. Source ids you may cite: {', '.join(ids)}. Leave dropped and changes empty.")
    draft = call(note=f"faq-{prefix}{suffix}-draft", system=SYSTEM, content=content + [{"type": "text", "text": ask}],
                 schema=_schema(), budget=budget, effort="medium", max_tokens=32000)
    if not review:
        return {"category": cat, "entries": draft["data"]["entries"], "gaps": draft["data"]["gaps"]}
    check = ("You are now the reviewer. Below are draft entries for this category. Check every factual claim "
             "(numbers, deadlines, conditions, menu paths, offices, phone numbers, article numbers) against the "
             "documents above. Fix what is wrong, remove what the documents don't support, make confidence "
             "honest, fill disagreement wherever documents conflict, keep questions casual and varied, remove any "
             "personal name, and keep each quote under 15 words. Return the full corrected list (same ids); drop "
             "an entry only if nothing in it can be supported, and say why. List your changes briefly; leave gaps "
             "empty.\n\n"
             + json.dumps(draft["data"]["entries"], ensure_ascii=False))
    final = call(note=f"faq-{prefix}{suffix}-review", system=SYSTEM, content=content + [{"type": "text", "text": check}],
                 schema=_schema(), budget=budget, effort="medium", max_tokens=32000)
    data = final["data"]
    entries = data["entries"]
    if update:  # an entry that kept an existing id replaces it where it lives
        known = {e["id"] for e in _existing(cat)}
        updated = {e["id"]: e for e in entries if e["id"] in known}
        for p in entry_files(prefix):
            d = json.loads(p.read_text(encoding="utf-8"))
            hit = [i for i, e in enumerate(d["entries"]) if e["id"] in updated]
            for i in hit:
                d["entries"][i] = updated[d["entries"][i]["id"]]
            if hit:
                d.setdefault("changes", []).append(f"round {suffix}: updated " + ", ".join(
                    d["entries"][i]["id"] for i in hit))
                dump_json(p, d)
        entries = [e for e in entries if e["id"] not in known]
    gone = {x["id"] for x in data["dropped"]} & {r["id"] for r in related}
    if gone:  # an older entry elsewhere that the new one replaces
        for _, other in CATEGORIES:
            for p in entry_files(other):
                d = json.loads(p.read_text(encoding="utf-8"))
                keep = [e for e in d["entries"] if e["id"] not in gone]
                if len(keep) != len(d["entries"]):
                    d["entries"] = keep
                    d.setdefault("changes", []).append(f"round {suffix}: replaced by {cat}: " + ", ".join(sorted(gone)))
                    dump_json(p, d)
    out = {"category": cat, "entries": entries, "gaps": draft["data"]["gaps"],
           "dropped": data["dropped"], "changes": data["changes"]}
    dump_json(OUT / f"faq-{prefix}{suffix}.json", out)
    return out


AUDIT_CATEGORIES = ["졸업", "다전공", "수강신청", "재수강·성적", "장학", "학적변동", "등록·등록금"]


def audit(cat: str, titles: dict[str, str], budget: float) -> list[str]:
    """A third, independent pass for the high-stakes categories: an auditor who did not write the entries
    re-checks every claim against the documents and returns only the entries that need a fix."""
    from claude_client import call
    prefix = PREFIX[cat]
    data = {p: json.loads(p.read_text(encoding="utf-8")) for p in entry_files(prefix)}
    docs = [d for t in TOPICS + SUPPLEMENTS + ROUND3 + ROUND4 + ROUND5 if t["category"] == cat for d in t["docs"]]
    content, ids = _prefix({"docs": list(dict.fromkeys(docs))}, titles)
    entries = [e for d in data.values() for e in d["entries"]]
    ask = ("You are an independent auditor; someone else wrote and reviewed these entries. Check every number, "
           "deadline, condition, admission-year scope, office, phone number and article citation against the "
           "documents above. Return in `entries` ONLY the entries that need a correction, each in full with the "
           "fix applied (same id). Where documents conflict and the entry does not say so, add it to "
           "disagreement and lower confidence. Do not rewrite style. Describe each fix in `changes` as "
           "'<id>: what was wrong -> what it is now'. Leave gaps and dropped empty. Source ids you may cite: "
           f"{', '.join(ids)}.{KEEP_DAPLE}\n\n" + json.dumps(entries, ensure_ascii=False))
    r = call(note=f"faq-{prefix}-audit", system=SYSTEM, content=content + [{"type": "text", "text": ask}],
             schema=_schema(), budget=budget, effort="medium", max_tokens=32000)
    fixed = {e["id"]: e for e in r["data"]["entries"]}
    applied = []
    for p, d in data.items():
        for i, e in enumerate(d["entries"]):
            if e["id"] in fixed:
                d["entries"][i] = fixed[e["id"]]
                applied.append(e["id"])
        d.setdefault("audit_changes", []).extend(r["data"]["changes"])
        dump_json(p, d)
    return applied


def reverify(cat: str, titles: dict[str, str], budget: float) -> list[str]:
    """Round 5: every low-confidence entry of a category is re-checked against the documents it cites and the
    newer pages fetched since. Confirmed -> raised; contradicted -> fixed; still unsettled -> kept low with a
    note that says what is unsettled and whom to ask. Returns the ids changed."""
    from claude_client import call
    prefix = PREFIX[cat]
    data = {p: json.loads(p.read_text(encoding="utf-8")) for p in entry_files(prefix)}
    low = [e for d in data.values() for e in d["entries"] if e["confidence"] == "low"]
    if not low:
        return []
    cited = [s["source_id"] for e in low for s in e["sources"]]
    content, ids = _prefix({"docs": list(dict.fromkeys(cited + REVERIFY_DOCS.get(cat, [])))}, titles)
    ask = ("These entries were marked low confidence. Re-check each one against the documents above (all "
           "checked today). For each entry decide:\n"
           "- confirmed: the documents now settle it (e.g. a current regulation clearly governs and the page that "
           "disagreed is older, or the conflict is about different admission years or a rule that only takes "
           "effect later) -> raise confidence to medium, and say in disagreement why the older/other statement "
           "does not apply (keep it short); high only if no disagreement is left to note;\n"
           "- contradicted: the answer is wrong -> fix it and set confidence honestly;\n"
           "- still unsettled: keep low, and make sure disagreement says what is unsettled and the answer says "
           "which office to ask.\n"
           "Return EVERY entry below in full (same id), with the decision applied. In `changes`, one line per "
           "entry: '<id>: confirmed|fixed|kept - reason'. Leave gaps and dropped empty. Source ids you may cite: "
           f"{', '.join(ids)}.{KEEP_DAPLE}\n\n" + json.dumps(low, ensure_ascii=False))
    r = call(note=f"faq-{prefix}-reverify", system=SYSTEM, content=content + [{"type": "text", "text": ask}],
             schema=_schema(), budget=budget, effort="medium", max_tokens=32000)
    fixed = {e["id"]: e for e in r["data"]["entries"] if e["id"] in {x["id"] for x in low}}
    applied = []
    for p, d in data.items():
        for i, e in enumerate(d["entries"]):
            if e["id"] in fixed:
                d["entries"][i] = fixed[e["id"]]
                applied.append(e["id"])
        d.setdefault("reverify_changes", []).extend(c for c in r["data"]["changes"]
                                                    if any(c.startswith(x) for x in fixed))
        dump_json(p, d)
    return applied


def crosscheck(budget: float) -> dict:
    """Reads every reviewed entry at once and fixes contradictions between categories (one call)."""
    from claude_client import call
    titles = _titles()
    paths = {p.stem: p for _, prefix in CATEGORIES for p in entry_files(prefix)}
    data = {k: json.loads(f.read_text(encoding="utf-8")) for k, f in paths.items()}
    compact = []
    for p, d in data.items():
        for e in d["entries"]:
            compact.append({"id": e["id"], "category": d["category"], "answer": e["answer"],
                            "conditions_exceptions": e["conditions_exceptions"], "applies_to": e["applies_to"],
                            "how_to": e["how_to"], "contact_office": e["contact_office"],
                            "confidence": e["confidence"], "disagreement": e["disagreement"],
                            "sources": [f"{s['source_id']} {s['article']}" for s in e["sources"]]})
    docs, _ = _docs(CORE_DOCS + CONTACT_DOCS, titles, cache_last=True)
    ask = ("Below are all entries of the knowledge base, written category by category. Find places where two "
           "entries contradict each other (different numbers, limits, deadlines, offices or phone numbers for the "
           "same thing), where an entry contradicts the two regulations above, or where an office's phone number "
           "differs from the contact documents above. For each problem, return the corrected entry in full (same "
           "id, all fields; keep its sources and add any source you rely on) - only entries that need a change. "
           "If documents themselves disagree, keep both views in disagreement and lower confidence instead of "
           "choosing. List each problem briefly in `changes`. Also, where two entries answer the same question "
           "(e.g. one in 기타 repeating one in its own category), put the weaker duplicate's id in `dropped` with "
           "the id it duplicates in the reason; keep entries that only overlap partly.\n\n"
           + json.dumps(compact, ensure_ascii=False))
    schema = _schema()
    r = call(note="faq-crosscheck", system=SYSTEM, content=docs + [{"type": "text", "text": ask}],
             schema=schema, budget=budget, effort="medium", max_tokens=48000)
    fixed = {e["id"]: e for e in r["data"]["entries"]}
    drop = {x["id"] for x in r["data"]["dropped"]} - set(fixed)
    applied = []
    for p, d in data.items():
        for i, e in enumerate(d["entries"]):
            if e["id"] in fixed:
                d["entries"][i] = fixed[e["id"]]
                applied.append(e["id"])
        d["dropped"] = d.get("dropped", []) + [x for x in r["data"]["dropped"]
                                               if x["id"] in {e["id"] for e in d["entries"]}]
        d["entries"] = [e for e in d["entries"] if e["id"] not in drop]
        d.setdefault("changes", []).extend(c for c in r["data"]["changes"] if any(a in c for a in applied))
        dump_json(paths[p], d)
    dump_json(OUT / "faq-crosscheck-result.json", {"applied": applied, "changes": r["data"]["changes"],
                                                     "dropped": r["data"]["dropped"]})
    print("crosscheck fixed", len(applied), "entries")
    return r["data"]


def _titles() -> dict[str, str]:
    return {s["id"]: s["title"] for s in load_sources()}


def dry_run(topics: list[dict]) -> None:
    titles = _titles()
    for t in topics:
        _, ids = _prefix(t, titles)
        chars = sum(len(doc_text(i) or "") for i in ids)
        missing = [d for d in t["docs"] if doc_text(d) is None]
        print(f"{t['category']}: {len(ids)} docs, {chars:,} chars (~{chars // 2:,} tokens), missing {missing}")


def _source_meta() -> dict[str, dict]:
    meta = {}
    for s in load_sources():
        sid, url = s["id"], s["url"]
        regulation = article_date = None
        t = (TEXT / f"{sid}.txt")
        if sid.startswith(("reg-",)) and t.exists():
            head = t.read_text(encoding="utf-8")[:600]
            name = re.search(r"\n(광운대학교[^\n]{2,40}|[^\n]{2,40}(규정|세칙|내규|학칙))\n", "\n" + head)
            rev = re.search(r"개정\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", head)
            made = re.search(r"제정\s*(\d{4})\.\s*(\d{1,2})\.\s*(\d{1,2})", head)
            d = rev or made
            regulation = (name.group(1).strip() if name else s["title"])
            article_date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else None
        meta[sid] = {"title": s["title"], "url": url, "regulation": regulation, "effective_date": article_date}
    return meta


def assemble() -> dict:
    """Merges out/faq-*.json into the shipped faq.json, with source metadata filled in locally."""
    meta = _source_meta()
    entries, seen, gaps, skipped = [], set(), {}, []
    add_path = OUT / "faq-question-additions.json"
    additions = json.loads(add_path.read_text(encoding="utf-8")) if add_path.exists() else {}
    for cat, prefix in CATEGORIES:
        parts = [json.loads(p.read_text(encoding="utf-8")) for p in entry_files(prefix)]
        if not parts:
            continue
        gaps[cat] = [g for d in parts for g in d.get("gaps", [])]
        for e in (e for d in parts for e in d["entries"]):
            eid = re.sub(r"[^a-z0-9-]", "-", e["id"].lower()).strip("-")
            if not eid.startswith(prefix + "-"):
                eid = f"{prefix}-{eid}"
            while eid in seen:
                eid += "-2"
            seen.add(eid)
            sources = []
            for s in e["sources"]:
                if s["source_id"] not in meta:  # not a document we gave Claude: never ship it
                    skipped.append(f"{eid}: unknown source {s['source_id']}")
                    continue
                m = meta[s["source_id"]]
                quote = s.get("quote") or ""
                if len(quote.split()) >= 15:
                    quote = ""
                sources.append({"title": m["title"], "url": m["url"],
                                "regulation": m.get("regulation"), "article": s.get("article") or None,
                                "effective_date": m.get("effective_date"), "checked_at": CHECKED_AT,
                                "source_id": s["source_id"], **({"quote": quote} if quote else {})})
            if not sources:
                skipped.append(f"{eid}: dropped, no known source")
                continue
            questions = list(e["questions"])
            for q in additions.get(eid, []):  # missed phrasings from eval_search.py --augment
                if len(questions) < 6 and q not in questions:
                    questions.append(q)
            confidence = e["confidence"]
            if e["disagreement"] and confidence == "high":  # a noted disagreement always caps confidence
                confidence = "medium"
            entries.append({
                "id": eid, "category": cat, "questions": questions, "answer": e["answer"],
                "conditions_exceptions": e["conditions_exceptions"], "how_to": e["how_to"],
                "contact_office": e["contact_office"], "sources": sources, "applies_to": e["applies_to"],
                "confidence": confidence, "disagreement": e["disagreement"] or None,
                "last_verified": CHECKED_AT,
            })
    for line in skipped:
        print("assemble:", line)
    return {"entries": entries, "gaps": gaps}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--budget", type=float, default=45.0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-review", action="store_true")
    ap.add_argument("--assemble", action="store_true")
    ap.add_argument("--crosscheck", action="store_true", help="one call over all entries: fix contradictions")
    ap.add_argument("--supplement", action="store_true", help="second round: SUPPLEMENTS -> faq-<prefix>-extra.json")
    ap.add_argument("--audit", action="store_true", help="independent re-check of AUDIT_CATEGORIES")
    ap.add_argument("--round3", action="store_true", help="third round: ROUND3 -> faq-<prefix>-extra3.json")
    ap.add_argument("--round4", action="store_true", help="fourth round: ROUND4 -> faq-<prefix>-extra4.json")
    ap.add_argument("--round5", action="store_true", help="fifth round: ROUND5 -> faq-<prefix>-extra5.json")
    ap.add_argument("--reverify", action="store_true", help="re-check every low-confidence entry (per category)")
    args = ap.parse_args()
    if args.reverify:
        titles = _titles()
        cats = [c for c, _ in CATEGORIES if not args.only or c in args.only]
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(reverify, c, titles, args.budget): c for c in cats}
            for f in cf.as_completed(futs):
                try:
                    changed = f.result()
                    if changed:
                        print(futs[f], "reverified", len(changed), flush=True)
                except Exception as e:  # noqa: BLE001 - one failed category doesn't stop the others
                    print(futs[f], "reverify FAILED", type(e).__name__, str(e)[:200], flush=True)
        return
    if args.round3 or args.round4 or args.round5:
        titles = _titles()
        rounds, sfx = ((ROUND3, "-extra3") if args.round3 else (ROUND4, "-extra4") if args.round4
                       else (ROUND5, "-extra5"))
        todo = [t for t in rounds if not args.only or t["category"] in args.only]
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_topic, t, titles, args.budget, True, t.get("suffix", sfx), True): t for t in todo}
            for f in cf.as_completed(futs):
                try:
                    print(futs[f]["category"], sfx, len(f.result()["entries"]), "new entries", flush=True)
                except Exception as e:  # noqa: BLE001 - one failed category doesn't stop the others
                    print(futs[f]["category"], sfx, "FAILED", type(e).__name__, str(e)[:200], flush=True)
        return
    topics = [t for t in TOPICS if not args.only or t["category"] in args.only]
    if args.supplement:
        titles = _titles()
        sups = [t for t in SUPPLEMENTS if not args.only or t["category"] in args.only]
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_topic, t, titles, args.budget, True, "-extra"): t for t in sups}
            for f in cf.as_completed(futs):
                try:
                    print(futs[f]["category"], "extra", len(f.result()["entries"]), "entries", flush=True)
                except Exception as e:  # noqa: BLE001 - one failed category doesn't stop the others
                    print(futs[f]["category"], "extra FAILED", type(e).__name__, str(e)[:200], flush=True)
        return
    if args.crosscheck:
        crosscheck(args.budget)
        return
    if args.audit:
        titles = _titles()
        cats = [c for c in (args.only or AUDIT_CATEGORIES) if c in PREFIX]
        with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(audit, c, titles, args.budget): c for c in cats}
            for f in cf.as_completed(futs):
                try:
                    print(futs[f], "audit fixed", len(f.result()), flush=True)
                except Exception as e:  # noqa: BLE001 - one failed category doesn't stop the others
                    print(futs[f], "audit FAILED", type(e).__name__, str(e)[:200], flush=True)
        return
    if args.assemble:
        built = assemble()
        target = KNOWLEDGE / "faq.json"
        doc = {"version": {"built_at": datetime.date.today().isoformat(), "checked_at": CHECKED_AT},
               "entries": built["entries"], "gaps": built["gaps"]}
        # atomic: a running reader (the eval, the MCP server) never sees a half-written file
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        dump_json(tmp, doc)
        os.replace(tmp, target)
        print(len(built["entries"]), "entries ->", target)
        return
    if args.dry_run:
        dry_run(topics)
        return
    titles = _titles()
    # The first topic alone writes the shared cache (core regulations); the rest then read it.
    first, rest = topics[0], topics[1:]
    results = [run_topic(first, titles, args.budget, not args.skip_review)]
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(run_topic, t, titles, args.budget, not args.skip_review): t for t in rest}
        for f in cf.as_completed(futs):
            t = futs[f]
            try:
                r = f.result()
                results.append(r)
                print(t["category"], len(r["entries"]), "entries", flush=True)
            except Exception as e:  # noqa: BLE001 - one failed category doesn't stop the others
                print(t["category"], "FAILED", type(e).__name__, str(e)[:200], flush=True)


if __name__ == "__main__":
    main()
