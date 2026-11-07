"""Builds sources.json: the seed list of public pages, plus pages found inside already-fetched ones.

    python discover.py --seed      # write the seed list (keeps entries already there)
    python discover.py --derive    # add pages linked from fetched files (regulation bodies, department
                                   # curriculum tabs, FAQ articles); run fetch.py --sources again after

Every entry: {id, url, title, feeds: [faq|curricula|rules_tables|contacts], host}. Nothing here fetches KLAS or
daple.kwuniv.com; the school's own www, rule, oia and library hosts only. The one Daple entry is a citation for
facts from the owner's snapshot (fetch: false).
"""

from __future__ import annotations

import argparse
import re
import urllib.parse
from html import unescape

from extract import decode_html, links
from kbcommon import RAW, SOURCES, dump_json, load_sources

WWW = "https://www.kw.ac.kr"
RULE = "https://rule.kw.ac.kr/lmxsrv/law"

WWW_PAGES = [  # (id, path, title, feeds)
    ("web-info01", "/ko/life/bachelor_info01.jsp", "학사정보 교과안내(이수구분)", ["faq"]),
    ("web-info03", "/ko/life/bachelor_info03.jsp", "학사정보 수업안내", ["faq"]),
    ("web-info04", "/ko/life/bachelor_info04.jsp", "학사정보 전공배정 신청 안내", ["faq"]),
    ("web-info05", "/ko/life/bachelor_info05.jsp", "학사정보 성적평가 안내", ["faq"]),
    ("web-info07", "/ko/life/bachelor_info07.jsp", "학사정보 수료/졸업요건 안내", ["faq"]),
    ("web-info08", "/ko/life/bachelor_info08.jsp", "학사정보 학적변동 구분", ["faq"]),
    ("web-info09", "/ko/life/bachelor_info09.jsp", "학사정보 특별프로그램 안내", ["faq"]),
    ("web-info11", "/ko/life/bachelor_info11.jsp", "학사정보 다전공 이수제도 안내", ["faq"]),
    ("web-info12", "/ko/life/bachelor_info12.jsp", "학사정보 입학연도별 졸업학점 안내", ["faq"]),
    ("web-info13", "/ko/life/bachelor_info13.jsp", "학사정보 수강신청/강의시간표", ["faq"]),
    ("web-info02", "/ko/life/bachelor_info02.jsp", "학사정보 필수과목 개설안내(연도별/학과별)", ["curricula"]),
    ("web-rule", "/ko/life/bachelor_rule.jsp", "학칙 및 학사관련규정", ["faq"]),
    ("web-summary", "/ko/life/summary.jsp", "장학안내", ["faq"]),
    ("web-scholar01", "/ko/life/scholarship01.jsp", "교내장학금", ["faq"]),
    ("web-scholar02", "/ko/life/scholarship02.jsp", "교외장학금", ["faq"]),
    ("web-scholar03", "/ko/life/scholarship03.jsp", "장학재단 예우", ["faq"]),
    ("web-cert01", "/ko/life/certificate01.jsp", "제증명안내", ["faq"]),
    ("web-cert02", "/ko/life/certificate02.jsp", "인터넷 증명발급", ["faq"]),
    ("web-cert06", "/ko/life/certificate06.jsp", "증명서 자동발급기", ["faq"]),
    ("web-cert07", "/ko/life/certificate07.jsp", "증명서 창구 발급", ["faq"]),
    ("web-studentid", "/ko/life/student_id.jsp", "학생증발급 안내", ["faq"]),
    ("web-isic", "/ko/life/isic.jsp", "국제학생증 발급 안내", ["faq"]),
    ("web-military", "/ko/life/military_consulting.jsp", "병무안내", ["faq"]),
    ("web-military01", "/ko/life/military_guide01.jsp", "병사업무안내", ["faq"]),
    ("web-facility01", "/ko/life/facility01.jsp", "복지 편의시설", ["faq"]),
    ("web-facility03", "/ko/life/facility03.jsp", "문화학습지원", ["faq"]),
    ("web-facility07", "/ko/life/facility07.jsp", "전산멀티미디어지원", ["faq"]),
    ("web-facility09", "/ko/life/facility09.jsp", "편의시설안내", ["faq"]),
    ("web-facility11", "/ko/life/facility11.jsp", "식단안내", ["faq"]),
    ("web-facility12", "/ko/life/facility12.jsp", "Wi-Fi 이용 안내", ["faq"]),
    ("web-dorm", "/ko/department/affiliated_etc02.jsp", "생활관", ["faq"]),
    ("web-directions", "/ko/tour/directions.jsp", "위치 및 교통안내(셔틀)", ["faq"]),
    ("web-tour02", "/ko/tour/tour02.jsp", "위치 및 교통안내", ["faq"]),
    ("web-phone", "/ko/tour/phone.jsp", "조회서비스(전화번호)", ["contacts"]),
    ("web-team-edu", "/ko/department/view.jsp?hpage=intro_0004", "교육지원팀 소개", ["contacts"]),
    ("web-team-student", "/ko/department/view.jsp?hpage=intro_0005", "학생처(학생복지팀) 소개", ["contacts"]),
    ("web-team-intl", "/ko/department/view.jsp?hpage=intro_0014", "국제교류팀 소개", ["contacts"]),
    ("web-team-finance", "/ko/department/view.jsp?hpage=intro_0017", "재무팀 소개", ["contacts"]),
    ("web-team-career", "/ko/department/view.jsp?hpage=intro_0008", "경력개발팀 소개", ["contacts"]),
    ("web-counsel", "/ko/department/admin32.jsp", "학생상담실", ["faq"]),
    ("web-faq-all", "/ko/life/faq.jsp?MaxRows=100&tpage=1&searchKey=1&searchVal=&srCategoryId=", "종합 FAQ 목록", ["faq"]),
]

DEPARTMENTS = [  # (id, hpage or page, name)
    ("college_001_01", "전자공학과"), ("college_001_04", "전자통신공학과"), ("college_001_05", "전자융합공학과"),
    ("college_001_02", "전기공학과"), ("college_001_03", "전자재료공학과"), ("college_001_08", "반도체시스템공학부"),
    ("college_011_01", "컴퓨터정보공학부"), ("college_011_02", "소프트웨어학부"), ("college_011_03", "정보융합학부"),
    ("college_011_04", "로봇학부"), ("college_011_05", "정보제어·지능시스템전공"), ("ai06_1", "지능형로봇학과"),
    ("college_003_01", "건축공학과"), ("college_003_02", "화학공학과"), ("college_003_03", "환경공학과"),
    ("college_003_04", "건축학과"), ("college_004_01", "수학과"), ("college_004_02", "전자바이오물리학과"),
    ("college_004_04", "화학과"), ("college_004_05", "스포츠융합과학과"), ("college_005_01", "국어국문학과"),
    ("college_005_02", "영어산업학과"), ("college_005_03", "미디어커뮤니케이션학부"), ("college_005_06", "산업심리학과"),
    ("college_005_07", "동북아문화산업학부"), ("college_006_01", "행정학과"), ("college_006_02", "법학부"),
    ("college_006_05", "국제학부"), ("college_007_01", "경영학부"), ("college_007_02", "국제통상학부"),
    ("college_010_01", "금융부동산법무학과"), ("college_010_02", "게임콘텐츠학과"),
    ("college_010_03", "스마트전기전자학과"), ("college_010_04", "스포츠상담재활학과"),
    # majors inside a 학부 that have their own www page
    ("college_001_07", "지능시스템전공"), ("college_005_04", "인터랙티브미디어커뮤니케이션전공"),
    ("college_005_05", "전략커뮤니케이션전공"), ("college_005_08", "문화콘텐츠개발전공"),
    ("college_006_08", "기업법무전공"), ("college_006_04", "과학기술법무전공"),
    ("college_006_03", "국제법무전공"), ("college_006_06", "글로벌코리아전공"), ("college_007_03", "빅데이터경영전공"),
    ("college_007_04", "국제금융전공"), ("college_007_05", "글로벌비즈니스전공"),
]

MUST_XLS = [f"must_2026_{n:02d}" for n in range(1, 35) if n != 27] + ["must_2026_18", "must_2026_33"]

REGULATIONS = [  # (SEQ, title) - 제4편 제3장 교무행정 and others; the body needs SEQ_HISTORY from the view page
    (188, "4-3-3 계절수업 운영에 관한 규정"), (221, "4-3-4 수강신청에 관한 규정"),
    (223, "4-3-6 국내대학 수학 및 이수학점 인정에 관한 시행세칙"), (211, "4-3-11 학사경고자 관리 및 지원에 관한 규정"),
    (79, "4-3-18 국제기관 교환학생에 대한 내규"), (89, "4-3-31 전과에 관한 규정"), (90, "4-3-32 수업 운영에 관한 규정"),
    (87, "4-3-27 현장실습학기제 운영 규정"), (218, "4-3-33 학생창업 학사지원에 관한 규정"),
    # second round, for gaps the first FAQ pass reported (폐강 기준, 자율전공학부 전공 선택)
    (78, "4-3-10 교과과정 편성 및 운영에 관한 규정"), (189, "4-3-39 자율전공학부 운영에 관한 규정"),
]
RULE_TREES = [(13, "제4편 제4장 재무행정 목록"), (15, "제4편 제6장 학생행정 목록")]
# Already read by the rules worker (scratchpad/rules/raw), reused rather than fetched again.
REUSED = [
    ("reg-hakchik", f"{RULE}/lawFullContent.do?SEQ=21&SEQ_HISTORY=675", "2-0-1 광운대학교 학칙 (2026.10.28.)"),
    ("reg-sihaeng", f"{RULE}/lawFullContent.do?SEQ=22&SEQ_HISTORY=614", "2-0-2 학칙 시행세칙 (2026.02.11.)"),
    ("reg-damajor-isu", f"{RULE}/lawFullContent.do?SEQ=95&SEQ_HISTORY=672", "4-3-8 다전공 이수에 관한 내규"),
    ("reg-damajor-unyeong", f"{RULE}/lawFullContent.do?SEQ=96&SEQ_HISTORY=525", "4-3-9 다전공 운영에 관한 내규"),
    ("reg-early-grad", f"{RULE}/lawFullContent.do?SEQ=216&SEQ_HISTORY=422", "4-3-2 조기졸업에 관한 규정"),
    ("reg-gyoyang", f"{RULE}/lawFullContent.do?SEQ=77&SEQ_HISTORY=509", "4-3-1 교양교육 운영 규정"),
]
ANNEXES = [
    ("annex-hakchik-6", 3092, "학칙 [별표 6] 입학년도별 단과대학(학과)별 이수학점 안내 (HWP)"),
    ("annex-damajor-1", 3086, "다전공 이수에 관한 내규 [별표1] 연계전공별 이수학점 및 학위명 (HWP)"),
    ("annex-gyoyang-2", 2708, "교양교육 운영 규정 [별표2] 교양교과목 분류 (HWP)"),
    ("annex-class-3", 2715, "수업 운영에 관한 규정 [별표3] 수강인원 (HWP)"),
    ("annex-class-4", 2716, "수업 운영에 관한 규정 [별표4] 유고결석 사유에 따른 결석 허용기간 (HWP)"),
    ("annex-scholar-1", 3076, "장학 규정 [별표 1] 장학금 종류별 지급대상 및 신청자격 (HWP)"),
]
FAQ_TEAMS = ("교육지원팀", "학생복지팀", "학생서비스센터", "재무팀", "대외교류팀", "예비군연대", "취업지원팀")
FAQ_SKIP = ("대체텍스트", "교육조교", "물품", "구매", "기자재", "대사증후군", "게시물", "주소지", "병력동원")
FAQ_ANY_TEAM = ("교통편",)
OTHER = [
    ("oia-outbound", "https://oia.kw.ac.kr/exchange/outbound.php", "국제교류팀 교환학생(파견) 안내", ["faq"]),
    ("kupis-home", "https://kupis.kw.ac.kr/", "중앙도서관 홈", ["faq"]),
]


# Round 3 (gaps from the first eval round): notice lists of the 학사 and 등록/장학 boards, the colleges' pages
# (교학팀 numbers), and the dormitory and reading-room sites as links.
ROUND3 = [
    ("notices-haksa-1", "/ko/life/notice.jsp?srCategoryId=1&mode=list&tpage=1", "공지사항 학사 목록 1쪽"),
    ("notices-haksa-2", "/ko/life/notice.jsp?srCategoryId=1&mode=list&tpage=2", "공지사항 학사 목록 2쪽"),
    ("notices-haksa-3", "/ko/life/notice.jsp?srCategoryId=1&mode=list&tpage=3", "공지사항 학사 목록 3쪽"),
    ("notices-jang-1", "/ko/life/notice.jsp?srCategoryId=4&mode=list&tpage=1", "공지사항 등록/장학 목록 1쪽"),
    ("notices-jang-2", "/ko/life/notice.jsp?srCategoryId=4&mode=list&tpage=2", "공지사항 등록/장학 목록 2쪽"),
] + [(f"college-{n:03d}", f"/ko/univ/college_view.jsp?hpage=college_{n:03d}", f"단과대학 소개 college_{n:03d}")
     for n in (1, 3, 4, 5, 6, 7, 8, 10, 11)]
ROUND3_OTHER = [
    ("dorm-home", "https://kw.happydorm.or.kr/", "행복기숙사(빛솔재) 홈페이지"),
    ("dorm-main", "https://kw.happydorm.or.kr/00/0000.do", "행복기숙사(빛솔재) 메인"),
    ("dorm-admission", "https://kw.happydorm.or.kr/30/3010.do", "행복기숙사 입사/퇴사안내"),
    ("dorm-apply", "https://kw.happydorm.or.kr/30/3030.do", "행복기숙사 입사신청"),
    ("dorm-contact", "https://kw.happydorm.or.kr/10/1040.do", "행복기숙사 연락처"),
    ("seat-status", "http://mobileid.kw.ac.kr/seatweb/domian5.asp", "중앙도서관 열람실 좌석 현황"),
]
# Round 4 (everyday questions): IT, student ID, support centres, facilities, careers, clubs.
ROUND4 = [
    ("notices-general-1", "/ko/life/notice.jsp?srCategoryId=0&mode=list&tpage=1", "공지사항 일반 목록 1쪽"),
    ("notices-general-2", "/ko/life/notice.jsp?srCategoryId=0&mode=list&tpage=2", "공지사항 일반 목록 2쪽"),
    ("notices-general-3", "/ko/life/notice.jsp?srCategoryId=0&mode=list&tpage=3", "공지사항 일반 목록 3쪽"),
    ("notices-student-1", "/ko/life/notice.jsp?srCategoryId=2&mode=list&tpage=1", "공지사항 학생 목록 1쪽"),
    ("notices-student-2", "/ko/life/notice.jsp?srCategoryId=2&mode=list&tpage=2", "공지사항 학생 목록 2쪽"),
    ("notices-facility-1", "/ko/life/notice.jsp?srCategoryId=6&mode=list&tpage=1", "공지사항 시설 목록 1쪽"),
    ("notices-job-1", "/ko/life/job.jsp?mode=list&tpage=1", "취업게시판 목록 1쪽"),
    ("notices-job-2", "/ko/life/job.jsp?mode=list&tpage=2", "취업게시판 목록 2쪽"),
    ("web-team-it", "/ko/department/view.jsp?hpage=intro_0019", "정보통신처(정보운영팀) 소개"),
    ("web-team-network", "/ko/department/view.jsp?hpage=intro_0020", "통신운영팀 소개"),
    ("web-team-sports", "/ko/department/view.jsp?hpage=intro_0006", "체육지원팀 소개"),
    ("web-team-general", "/ko/department/view.jsp?hpage=intro_0016", "총무처(총무팀) 소개"),
    ("web-team-facility", "/ko/department/view.jsp?hpage=intro_0018", "관리처(시설안전관리팀) 소개"),
    ("web-team-internship", "/ko/department/view.jsp?hpage=intro_0009", "현장실습지원팀 소개"),
    ("web-humanrights", "/ko/department/admin31.jsp", "인권센터"),
    ("web-disability", "/ko/department/admin33.jsp", "장애학생지원실"),
    ("web-facility10", "/ko/life/facility10.jsp", "장소 사용(신청) 안내"),
    ("web-facility04", "/ko/life/facility04.jsp", "대강당/소강당"),
    ("web-tour01", "/ko/tour/tour01.jsp", "광운캠퍼스안내"),
    ("web-activity01", "/ko/life/activity01.jsp", "학생자치활동(학생자치기구)"),
    ("web-activity02", "/ko/life/activity02.jsp", "총동아리연합회"),
    ("web-activity03", "/ko/life/activity03.jsp", "중앙동아리"),
]
ROUND4_OTHER = [
    ("job-home", "https://job.kw.ac.kr/", "경력개발팀(인재개발원) 홈"),
    ("job-notice", "https://job.kw.ac.kr/community/notice.php", "경력개발팀 공지사항 목록"),
    ("internship-home", "https://internship.kw.ac.kr/index.do", "현장실습지원팀 첫 화면"),
    ("dept-electric-852", "https://electric.kw.ac.kr/community/s_notice.php?BoardMode=view&UID=852",
     "전기공학과 공지 2026-2 이수체계 준수제도 및 선수 교과목 미이수자 상담 안내"),
]

# Round 4 notices, picked by hand from the 2026-11-07 lists of the 일반·학생·시설·학사 boards and the 취업게시판
ROUND4_NOTICES = [
    (53558, "[학생] 장소사용 신청 안내(2026년 11월)"), (53200, "[학생] 2026-2 복지관 3층 학생식당(함지마루) 운영 안내"),
    (53599, "[시설] 한울관 및 아이스링크 주차장 입구 차량 출입 통제 안내"), (53462, "[시설] 한울관 및 아이스링크 주차장 출입구 변경 안내"),
    (53458, "[정보통신처] 불법 소프트웨어, 이미지, 폰트 사용 및 배포 방지를 위한 협조 안내"),
    (53457, "[정보통신처] 내PC지키미를 이용한 PC보안 및 알약 점검 협조 요청"),
    (53483, "[학사] KLAS 종합정보서비스 보안 강화 조치 시행 안내"),
    (53549, "[학생상담실] 뇌파·맥파 측정 체험 및 해석상담"), (53505, "[인권센터 특강] AI·SNS 시대 디지털 경계"),
    (52442, "[학생] 2026 폭력예방교육 수강 안내"),
    (53210, "[취업] 2026-2 비교과프로그램 운영 안내"), (53211, "[취업] 2026-2 온라인 이력서 클리닉"),
    (52987, "[학사] 2026-2 학부·대학원 연계과목(학석사연계과정) 수강신청 안내"), (52981, "[학사] 2026-2 수강신청자료집"),
]
ROUND4_OTHER_2 = [
    ("job-51947", "https://www.kw.ac.kr/ko/life/job.jsp?BoardMode=view&DUID=51947",
     "취업게시판 경력개발팀 취업정보 인스타그램(@kwu_career) 제공 안내"),
    ("job-counsel-info", "https://job.kw.ac.kr/jobprogram/counsel_info.php", "경력개발팀 진로·취업 상담안내"),
    ("job-program-intro", "https://job.kw.ac.kr/jobprogram/program_intro.php", "경력개발팀 취업프로그램"),
    ("job-notice-12476", "https://job.kw.ac.kr/community/notice.php?BoardMode=view&UID=12476",
     "경력개발팀 공지 10월 외부상담사(온라인) 진로 및 취업상담 신청 안내"),
    ("faq-755", "https://www.kw.ac.kr/ko/life/faq.jsp?BoardMode=view&DUID=755",
     "종합 FAQ [정보운영팀] 홈페이지 및 종합정보서비스 비밀번호를 분실한 경우"),
]

NOTICE_PICK = ("국가장학금 지급", "동계계절수업", "유고결석 및 공결", "수강과목 포기", "취득학점 포기",
               "졸업연기 및 조기졸업", "수강신청 공고", "조기취업자", "성적 확인 및 성적증명서", "화도 및 동해장학금",
               "중간고사 일정", "재입학 전형")

# Round 5 (owner's real use): missing curricula (지능형로봇학과, 글로벌코리아전공), 어학 졸업요건, unsourced retries.
ROUND5 = [
    ("web-sitemap", "/ko/info/sitemap.jsp", "홈페이지 사이트맵"),
    ("web-data-1", "/ko/life/data.jsp?mode=list&tpage=1", "KW-LIFE 자료실 목록 1쪽"),
    ("web-data-2", "/ko/life/data.jsp?mode=list&tpage=2", "KW-LIFE 자료실 목록 2쪽"),
    ("web-ai06-5", "/ko/univ/ai06_5.jsp", "지능형로봇학과 교과목안내"),
    ("web-law06-1", "/ko/univ/law06_1.jsp", "국제학부 글로벌코리아전공 소개"),
    ("web-calendar", "/ko/life/bachelor_calendar.jsp", "학사일정"),
]
ROUND5_OTHER = [
    ("share-home", "https://share.kw.ac.kr/", "지능형로봇학과(지능형로봇혁신융합대학사업단) 홈"),
    ("sangdam-notice", "https://sangdam.kw.ac.kr/board/notice.php", "학생상담실 공지사항 목록"),
    ("council-home", "https://www.kwu-studentcouncil.co.kr/", "총학생회 이음 홈"),
    ("council-notices", "https://www.kwu-studentcouncil.co.kr/notices", "총학생회 이음 공지사항"),
    ("regview-272", "https://rule.kw.ac.kr/lmxsrv/law/lawFullView.do?SEQ=272", "4-3-40 공학프로그램 운영 규정 (개정 정보)"),
    ("web-law06-4", "https://www.kw.ac.kr/ko/univ/law06_4.jsp", "국제학부 글로벌코리아전공 교육과정"),
    ("web-law06-5", "https://www.kw.ac.kr/ko/univ/law06_5.jsp", "국제학부 글로벌코리아전공 교과목안내"),
    ("share-main", "https://share.kw.ac.kr/main/main.php", "지능형로봇학과(사업단) 메인"),
    ("council-lost-found", "https://www.kwu-studentcouncil.co.kr/notices/cl1778405153738tgq2y2n",
     "총학생회 공지 분실물 게시/습득 페이지 (2026.05.10)"),
    ("council-student-fee", "https://www.kwu-studentcouncil.co.kr/notices/cl1789744608455mdfnh2u",
     "총학생회 공지 1학기 자율적학생경비 추가 납부 안내 (2026.04.30)"),
    ("robot-edu-system", "https://share.kw.ac.kr/edu_pro/edu_pro01.php?tmenu=3&smenu=1", "지능형로봇학과 교육과정체계"),
    ("robot-rules", "https://share.kw.ac.kr/edu_pro/edu_pro02.php?tmenu=3&smenu=2", "지능형로봇학과 학과내규"),
    ("robot-admission", "https://share.kw.ac.kr/department/department03.php?tmenu=2&smenu=3", "지능형로봇학과 진학안내"),
    ("robot-intro", "https://share.kw.ac.kr/department/department02.php?tmenu=2&smenu=2", "지능형로봇학과 학과소개"),
    ("robot-modules", "https://share.kw.ac.kr/department/department0403new.php?tmenu=2&smenu=4",
     "지능형로봇학과 마이크로모듈교과목안내"),
    ("robot-rules-1159", "https://share.kw.ac.kr/edu_pro/edu_pro02.php?admin_mode=read&no=1159&make=&search=&type=&tmenu=3&smenu=2&page=1&sub=",
     "지능형로봇학과 학과내규 (2022-06-06 게시)"),
    ("robot-edu-image", "https://share.kw.ac.kr/asset/images/edu_pro_img01.png", "지능형로봇학과 교육과정체계 그림"),
    ("robot-rules-image", "https://share.kw.ac.kr/board/free/photo/a_202206061718380.jpg", "지능형로봇학과 학과내규 (게시 이미지)"),
    ("robot-courses-2026", "https://share.kw.ac.kr/department/department0403new.php?admin_mode=read&no=1593&make=&search=&tmenu=2&smenu=4",
     "2026학년도 지능형로봇학과 교과목 표"),
    ("robot-modules-2026", "https://share.kw.ac.kr/department/department0403new.php?admin_mode=read&no=1592&make=&search=&tmenu=2&smenu=4",
     "2026학년도 마이크로모듈 교과목(예정)"),
    ("council-fee-check", "https://www.kwu-studentcouncil.co.kr/notices/cl1774108950706mdbkjig",
     "총학생회 공지 자율적학생경비 확인 시스템 (2026.03.22)"),
    ("council-bylaws", "https://www.kwu-studentcouncil.co.kr/resources/bylaws", "총학생회 자료실 학생회칙"),
    ("council-budgets", "https://www.kwu-studentcouncil.co.kr/resources/budgets", "총학생회 자료실 예·결산 자료"),
    ("office365-home", "https://office365.kw.ac.kr/", "Office 365 신청 포털 (직접 접속 시 응답)"),
    ("notice-53200-image", "https://www.kw.ac.kr/KWData/webeditor/2026/2026_08_27_150842.jpg",
     "[학생] 2026학년도 2학기 복지관 3층 학생식당(함지마루) 운영 안내 (본문 이미지)"),
    ("job-notice-12624", "https://job.kw.ac.kr/community/notice.php?BoardMode=view&UID=12624",
     "경력개발팀 공지 2026 광운대학교 취업박람회 개최 안내"),
    ("robot-courses-2025", "https://share.kw.ac.kr/department/department0403new.php?admin_mode=read&no=1508&make=&search=&tmenu=2&smenu=4",
     "2025학년도 지능형로봇학과 교과목 표"),
]

# Not fetched: facts from a Daple snapshot the owner took in their own session (scripts/knowledge/apply_daple.py).
OWNER_SNAPSHOTS = [
    ("daple-snapshot", "https://daple.kwuniv.com", "다전공 플래너(Daple) 2026-11-07 확인", ["faq"]),
]


def _entry(sid, url, title, feeds, **kw):
    return {"id": sid, "url": url, "title": title, "feeds": feeds, "host": urllib.parse.urlsplit(url).netloc, **kw}


def seed() -> list[dict]:
    out = [_entry(i, WWW + p, t, f) for i, p, t, f in WWW_PAGES]
    for hp, name in DEPARTMENTS:
        path = f"/ko/univ/{hp}.jsp" if not hp.startswith("college_") else f"/ko/univ/depart_intro.jsp?hpage={hp}"
        out.append(_entry(f"dept-{hp}", WWW + path, f"{name} 학과 소개", ["curricula"], department=name))
    for stem in dict.fromkeys(MUST_XLS):
        ext = ".xlsx" if stem in ("must_2026_18", "must_2026_33") else ".xls"
        out.append(_entry(stem.replace("_", "-"), f"{WWW}/ko/life/{stem}{ext}", f"필수과목표 {stem}", ["curricula"]))
    for seq, title in REGULATIONS:
        out.append(_entry(f"regview-{seq}", f"{RULE}/lawFullView.do?SEQ={seq}", title + " (개정 정보)", ["faq"]))
    for key, title in RULE_TREES:
        out.append(_entry(f"ruletree-{key}", f"{RULE}/lawTreeNodes.do?LAWGROUP=1&PARENT={key}&TREEDEPTH=3",
                          title, ["faq"]))
    for sid, url, title in REUSED:
        out.append(_entry(sid, url, title, ["faq", "rules_tables"], fetch=False, reused_from="rules worker"))
    for sid, fseq, title in ANNEXES:
        out.append(_entry(sid, f"https://rule.kw.ac.kr/lmxsrv/fileDown.do?FILE_SEQ={fseq}&FILE_TYPE=attach",
                          title, ["rules_tables"]))
    for sid, url, title, feeds in OTHER:
        out.append(_entry(sid, url, title, feeds))
    for sid, path, title in ROUND3:
        out.append(_entry(sid, WWW + path, title, ["faq", "contacts"] if sid.startswith("college") else ["faq"]))
    for sid, url, title in ROUND3_OTHER:
        out.append(_entry(sid, url, title, ["faq"]))
    for sid, path, title in ROUND4:
        out.append(_entry(sid, WWW + path, title, ["faq"]))
    for sid, url, title in ROUND4_OTHER:
        out.append(_entry(sid, url, title, ["faq"]))
    for duid, title in ROUND4_NOTICES:
        out.append(_entry(f"notice-{duid}", f"{WWW}/ko/life/notice.jsp?BoardMode=view&DUID={duid}", f"공지 {title}",
                          ["faq"]))
    for sid, url, title in ROUND4_OTHER_2:
        out.append(_entry(sid, url, title, ["faq"]))
    for sid, path, title in ROUND5:
        out.append(_entry(sid, WWW + path, title, ["faq", "curricula"] if "ai06" in path or "law06" in path else ["faq"]))
    for sid, url, title in ROUND5_OTHER:
        curr = sid.startswith(("robot-", "share-", "web-law06"))
        out.append(_entry(sid, url, title, ["curricula"] if curr else ["faq"]))
    for sid, url, title, feeds in OWNER_SNAPSHOTS:
        out.append(_entry(sid, url, title, feeds, fetch=False, provided_by="owner snapshot"))
    return out


def _html(sid: str) -> str | None:
    p = RAW / f"{sid}.html"
    return decode_html(p.read_bytes()) if p.exists() else None


def derive(sources: list[dict]) -> list[dict]:
    have = {s["id"] for s in sources}
    new = []
    for s in sources:
        sid = s["id"]
        h = _html(sid)
        if h is None:
            continue
        if sid.startswith("regview-"):  # -> body with the latest SEQ_HISTORY
            seq = sid.split("-")[1]
            m = re.search(rf"lawFullContent\.do\?SEQ={seq}&SEQ_HISTORY=(\d+)", h)
            if m:
                new.append(_entry(f"reg-{seq}", f"{RULE}/lawFullContent.do?SEQ={seq}&SEQ_HISTORY={m.group(1)}",
                                  s["title"].replace(" (개정 정보)", ""), ["faq"]))
        elif sid.startswith("dept-"):  # -> the department's 교육과정 tab on www
            for u, t in links(h[h.find("jwxe_main_content"):]):
                if t == "교육과정" and u.startswith("/ko/univ/"):
                    new.append(_entry(f"curr-{sid[5:]}", WWW + u, f"{s['department']} 교육과정",
                                      ["curricula"], department=s["department"]))
                    break
    # 종합 FAQ: list pages 2..8 (MaxRows is ignored by the server), then the articles from student-facing teams.
    first = _html("web-faq-all")
    if first:
        last = max([int(n) for n in re.findall(r"tpage=(\d+)&searchKey", first)] or [1])
        for n in range(2, last + 1):
            new.append(_entry(f"faqlist-{n}", f"{WWW}/ko/life/faq.jsp?MaxRows=10&tpage={n}&searchKey=1&searchVal="
                              f"&srCategoryId=", f"종합 FAQ 목록 {n}쪽", ["faq"]))
    for s in sources:
        if not (s["id"] == "web-faq-all" or s["id"].startswith("faqlist-")):
            continue
        h = _html(s["id"])
        if not h:
            continue
        for m in re.finditer(r'BoardMode=view&DUID=(\d+)[^"]*">\s*<strong class=.category.>\[([^\]]+)\]</strong>'
                             r'\s*([^<]+?)\s*<', h):
            duid, team, title = m.group(1), m.group(2), unescape(m.group(3)).strip()
            wanted = (team in FAQ_TEAMS and not any(k in title for k in FAQ_SKIP)) or any(k in title for k in FAQ_ANY_TEAM)
            if wanted:
                new.append(_entry(f"faq-{duid}", f"{WWW}/ko/life/faq.jsp?BoardMode=view&DUID={duid}",
                                  f"종합 FAQ [{team}] {title}", ["faq"]))
    # notice articles from the round-3 lists, picked by title (the 2026-11-07 lists; see NOTICE_PICK)
    titles = {}
    for s in sources:
        h = _html(s["id"]) if s["id"].startswith("notices-") else None
        for m in re.finditer(r'BoardMode=view&(?:amp;)?DUID=(\d+)[^"]*"[^>]*>(.*?)</a>', h or "", re.DOTALL):
            titles.setdefault(m.group(1), re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip())
    for duid, title in titles.items():
        if any(w in title for w in NOTICE_PICK):
            title = re.sub(r"\s*(신규게시글|Attachment)", "", title).strip()
            new.append(_entry(f"notice-{duid}", f"{WWW}/ko/life/notice.jsp?BoardMode=view&DUID={duid}",
                              f"공지 {title[:80]}", ["faq"]))
    tree_titles = ("장학 규정", "납입금 반환", "제증명 수수료")
    for sid in ("ruletree-13", "ruletree-15"):
        p = RAW / f"{sid}.html"
        if not p.exists():
            continue
        text = p.read_bytes().decode("utf-8", "replace")
        for m in re.finditer(r'"title":"([^"]+)"[^{}]*?"key":(\d+)', text):
            title, key = m.group(1), m.group(2)
            if any(k in title for k in tree_titles):
                new.append(_entry(f"regview-{key}", f"{RULE}/lawFullView.do?SEQ={key}", title + " (개정 정보)",
                                  ["faq"]))
    return [n for n in new if n["id"] not in have]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--derive", action="store_true")
    args = ap.parse_args()
    sources = load_sources()
    if args.seed:
        have = {s["id"] for s in sources}
        sources += [s for s in seed() if s["id"] not in have]
    if args.derive:
        added = derive(sources)
        sources += added
        for a in added:
            print("added", a["id"], a["url"])
    dump_json(SOURCES, sources)
    print(len(sources), "sources")


if __name__ == "__main__":
    main()
