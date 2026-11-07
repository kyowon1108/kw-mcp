# Eval summary: round 4

- cases graded: 150 (ok 150, truncated 0), errors: 0
- mean total: 0.930 ± 0.014 (95% CI)
- failing: 18
- answer cost: $9.75, judge cost: $7.39, ledger eval total: $66.27
- model: claude-opus-5-5, effort answer/judge: medium/medium
- provisional tools: {}

## Per category

| category | n | total | correct | sourced | actionable | honest | no_hallucination | scope | failing | top gap | Δ vs prev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 마감·할 일 | 10 | 0.93 | 1.70 | 1.70 | 1.90 | 1.80 | 2.00 | 2.00 | 0 | model_misuse 4 | +0.03 |
| 휴강·강의실 변경 | 10 | 0.93 | 2.00 | 1.70 | 1.90 | 1.80 | 2.00 | 1.80 | 0 | other 1 | +0.03 |
| 시험 | 10 | 0.89 | 1.90 | 2.00 | 1.70 | 1.50 | 1.70 | 1.90 | 2 | model_misuse 2, other 2 | -0.07 |
| 출석 | 10 | 0.88 | 1.60 | 2.00 | 1.80 | 1.50 | 1.70 | 1.90 | 3 | model_misuse 3, other 1 | -0.06 |
| 성적·재수강 | 10 | 0.93 | 1.90 | 2.00 | 1.90 | 1.90 | 1.80 | 1.60 | 1 | model_misuse 1 | -0.03 |
| 장학 | 10 | 0.95 | 1.80 | 2.00 | 2.00 | 1.90 | 1.70 | 2.00 | 2 | model_misuse 2, missing_data 1 | -0.00 |
| 졸업요건 | 10 | 0.95 | 2.00 | 1.90 | 2.00 | 2.00 | 1.90 | 1.60 | 0 | - | +0.07 |
| 다전공 | 10 | 0.92 | 2.00 | 2.00 | 2.00 | 1.80 | 1.60 | 1.60 | 1 | missing_data 1 | +0.02 |
| 수강신청·정정·포기 | 10 | 0.96 | 1.90 | 2.00 | 2.00 | 1.80 | 1.80 | 2.00 | 0 | model_misuse 2 | +0.05 |
| 휴학·복학 | 10 | 0.91 | 1.90 | 1.90 | 1.80 | 1.90 | 1.80 | 1.60 | 0 | model_misuse 2 | +0.02 |
| 학식 | 10 | 0.97 | 2.00 | 2.00 | 2.00 | 2.00 | 1.60 | 2.00 | 2 | missing_data 2 | +0.10 |
| 셔틀·기숙사·도서관 | 10 | 0.98 | 1.90 | 2.00 | 2.00 | 2.00 | 1.90 | 2.00 | 3 | missing_tool 2, model_misuse 1 | +0.01 |
| 학교 공지 찾기 | 10 | 0.95 | 2.00 | 2.00 | 2.00 | 1.90 | 1.80 | 1.70 | 1 | missing_data 1 | +0.02 |
| 학과 공지 | 10 | 0.89 | 1.70 | 1.80 | 1.90 | 1.80 | 1.70 | 1.80 | 2 | model_misuse 4, missing_data 1 | -0.02 |
| 첨부·이미지 공지 읽기 | 10 | 0.92 | 1.80 | 1.90 | 1.90 | 1.90 | 1.90 | 1.60 | 1 | model_misuse 2, wrong_shaping 1 | +0.03 |

## Worst 20

### gr10 (성적·재수강) total 0.58, gap model_misuse
- Q: f 재수강 계절로 들어도 됨? 겨울에
- tools: get_grades, school_guide, school_notices
- judge: 규정 설명과 개설 미확인 고지는 좋습니다. 하지만 학사일정을 조회하지 않아 수강신청·수업 기간을 빠뜨렸고, 6학점 포함 여부를 근거 없이 추정했습니다.
- misuse: academic_calendar·academic_deadlines를 호출하지 않아 동계 계절수업 수강신청·수업 일정을 놓쳤습니다.
- fix: 계절학기 질문에는 academic_calendar(또는 academic_deadlines)로 계절수업 일정을 함께 조회하도록 school_guide 결과나 서버 안내에서 유도해야 합니다(not_in_documents의 '수강신청 일정 없음' 항목에 학사일정 도구를 쓰라는 힌트 추가).

### ac01 (첨부·이미지 공지 읽기) total 0.67, gap model_misuse
- Q: 디비 과제2 제출형식 첨부 뭐라고 써있음
- tools: get_assignment_detail, get_attachment_text
- judge: 마감·미제출 안내는 정확하지만, 학생이 물은 게시글 첨부(과제2_제출형식.docx)가 아닌 과제 ERD 가이드를 요약했습니다.
- misuse: search_course_posts·get_course_post로 '과제 2 제출 형식 안내' 게시글을 찾지 않고, 과제 첨부만 읽었습니다.
- fix: '제출형식 첨부'처럼 게시글 첨부를 묻는 질문이면 search_course_posts로 관련 글을 찾고, get_attachment_text(source=post)로 읽도록 해야 합니다.

### at01 (출석) total 0.67, gap other
- Q: 확통 결석 3번에 지각 2번인데 이거 f각임??ㅠㅠ
- tools: get_attendance, get_course_post, get_syllabus, school_guide, search_course_posts
- judge: 출석 데이터와 학교 규정을 근거와 함께 잘 정리했고, 운영체제 규칙을 옮겨 쓰는 함정도 피했습니다. 다만 F가 아니라는 단정 어조, 추정 수업 횟수에 기댄 안전 범위, 교수 확인 안내 누락이 아쉽습니다.
- fix: 학교 규정 기준 판단은 참고용이라고 밝히고, 과목별 출석·지각 기준은 담당 교수(최교수 이메일·연구실 전화)에게 확인하도록 안내해야 합니다. 총 수업 횟수 추정에서 나온 '안전 범위'는 단정하지 않아야 합니다.

### at03 (출석) total 0.67, gap model_misuse
- Q: 예비군 갔다왔는데 공결 어케 신청함? 다 똑같이 하면 되나
- tools: get_attendance, read_school_notice, school_guide
- judge: 학교 공지 기반 예비군 공결 안내와 출석 현황 연결은 좋았습니다. 하지만 과목 공지를 확인하지 않고 모든 과목이 같은 절차라고 단정해 핵심 함정에 걸렸습니다.
- 0점 honest: 과목 게시판을 확인하지 않고 '모든 과목이 같은 방식'이라고 단정했습니다(must_not 위반).
- misuse: '다 똑같이 하면 되나'를 묻는 질문인데 search_course_posts로 과목별 공결 공지를 찾지 않았습니다. 학교 공지만 보고 모든 과목이 같다고 단정했습니다.
- fix: 과목별 절차를 묻는 질문에서는 수강 과목마다 search_course_posts(keyword='공결')를 호출하도록 해야 합니다. 확인하지 못한 과목은 '각 과목 공지·교수 확인 필요'로 남기도록 지시하세요.

### ex09 (시험) total 0.67, gap other
- Q: 기말 시험 겹치는거 있나 확인좀
- tools: get_class_changes, get_course_post, get_courses, get_exam_info, get_online_tests, search_course_posts
- judge: 도구를 잘 써서 확인된 일정은 정확하게 비교했고 AI 온라인시험까지 찾아냈습니다. 다만 운체·윤리는 가정에 기댄 추측성 분석을 덧붙여 약간 감점했습니다.
- fix: 공지가 없는 과목은 수업 시간을 가정해 겹침 여부를 판단하지 말고, '미확인, 교수 공지 또는 문의로 확인 필요'로만 표시하세요.

### sc07 (장학) total 0.67, gap model_misuse
- Q: 장학금 신청기간 언제야 klas에서 하는거
- tools: academic_deadlines, school_notices
- judge: 핵심 날짜와 KLAS 상태는 맞았습니다. 그러나 마지막 문장에서 다른 모든 장학금을 같은 기간으로 단정해 must_not을 어겼습니다.
- 0점 no_hallucination: '그 밖의 장학금은 12월 1~14일 신청'이라고 해 외부 장학까지 그 기간으로 단정했습니다(must_not 위반).
- misuse: 학사일정의 장학금 신청기간을 모든 장학금에 적용되는 것으로 과잉 일반화했습니다.
- fix: 학사일정 장학 신청기간은 교내(KLAS) 장학 기준이며, 교외·개별 장학은 각 공지를 확인하라고 한정해 말해야 합니다. KLAS 창 상태와 공지 사이의 불일치도 짚어 줘야 합니다.

### dl04 (마감·할 일) total 0.75, gap model_misuse
- Q: 디비 과제2 pdf로 내는거 맞나? 형식 뭐였더라
- tools: get_assignment_detail
- judge: 과제 상세로 PDF·마감·지각 기한은 정확히 답했지만, 게시판의 제출 형식 안내 공지와 첨부 docx를 확인하지 않아 세부 형식이 빠졌습니다.
- misuse: '형식'을 물었는데 search_course_posts·get_course_post·get_attachment_text로 게시판의 제출 형식 안내 공지와 첨부를 찾지 않고 과제 상세 하나로 끝냈습니다.
- fix: 제출 형식을 물으면 과제 상세와 함께 search_course_posts(keyword='과제 2' 또는 '형식')로 게시판 공지를 찾고, 첨부 파일을 읽어 요약하도록 유도해야 합니다. get_assignment_detail 설명에 '형식 안내 공지가 따로 있을 수 있음'을 넣는 것도 방법입니다.

### dn01 (학과 공지) total 0.75, gap model_misuse
- Q: 우리 과 공지 새로 뭐 올라옴?
- tools: my_notices
- judge: 공지 내용과 링크는 정확합니다. 하지만 정보융합학부로 태그된 글을 학부 글로 구분하지 못했고, 학부 게시판이 빠져 있다는 잘못된 한계를 말했습니다.
- misuse: my_notices 결과의 department 필드('정보융합학부')를 무시하고 학부 글이 수집되지 않는다고 오독했습니다.
- fix: department 필드로 우리 학부 글과 단과대 공통 글을 구분해 표시하도록 서버 안내·도구 설명에 명시해야 합니다.

### ex04 (시험) total 0.75, gap model_misuse
- Q: 운체 기말 범위 공지 떴냐
- tools: get_exam_info, search_course_posts
- judge: 핵심 사실은 맞습니다. 다만 '안 올라왔다'는 단정적 표현, 열지 않은 글 내용 단정, 교수님 확인 안내 누락으로 감점했습니다.
- misuse: 중간고사 글을 get_course_post로 열지 않고 본문 내용을 단정했습니다.
- fix: '검색으로는 찾지 못했다'로 표현하고, 열지 않은 글의 내용은 단정하지 말 것. 교수님 문의나 KLAS 게시판 재확인을 안내할 것.

### ac03 (첨부·이미지 공지 읽기) total 0.83, gap none
- Q: 확통 과제3 뭐 내라는거야 첨부 있음?
- tools: get_assignment_detail
- judge: 18:00 마감 함정을 피했고, 본문·형식·첨부 없음을 정확히 전한 간결한 답변입니다.
- fix: 출처(KLAS 과제 상세)를 한 줄 밝히고, 도구 결과에 없는 '1개' 같은 세부는 빼면 됩니다.

### ac08 (첨부·이미지 공지 읽기) total 0.83, gap model_misuse
- Q: 취업박람회 참가기업 표 이미지던데 IT회사 있어?
- tools: read_school_notice, school_notices
- judge: 포스터 이미지를 읽어 IT 관련 기업을 근거와 함께 답했지만, 기대한 학과 공지 aicon-3512의 표는 확인하지 않았습니다.
- misuse: 검색 결과에 학생 학과(정보융합학부) 게시글 aicon-3512가 있었는데 읽지 않고 경력개발팀 원글 이미지만 읽었습니다.
- fix: 학과 게시판 공지(aicon-3512)도 images=true로 열어 참가기업 표가 따로 있는지 확인한 뒤 답하도록 유도하세요.

### at02 (출석) total 0.83, gap none
- Q: 운체 지각 3번이면 결석 1번이라던데 ㄹㅇ? 나 지금 몇개임
- tools: get_attendance, get_course_post, get_courses, get_syllabus, school_guide, search_course_posts
- judge: 과목 공지를 검색해 본문까지 열어 정확히 답했고 출석 수치도 맞습니다. 결석 상한을 추정치로 제시한 점만 아쉽습니다.
- fix: 총 수업 횟수를 모를 때는 1/4 상한을 숫자로 추정하지 말고, 강의계획서·교육지원팀 확인만 안내하도록 하면 좋겠습니다.

### at04 (출석) total 0.83, gap model_misuse
- Q: 윤리 공결 냈는데 klas엔 아직 결석으로 뜸 왜이럼
- tools: get_attendance, school_guide
- judge: 기록 확인과 학교 절차 안내는 정확하고 실행 가능합니다. 다만 과목 공지를 확인하지 않아 '반영까지 1~2주' 핵심 정보가 빠졌습니다.
- misuse: 윤리 과목 게시판의 공결 반영 안내를 찾으려면 search_course_posts·get_course_post를 불러야 했는데 부르지 않아, 1~2주 반영 지연 정보를 놓쳤습니다.
- fix: 출석 반영 지연 질문이면 해당 과목 게시판을 '공결'·'출석' 키워드로 search_course_posts 하도록 get_attendance나 school_guide 결과의 안내에 넣으세요.

### at06 (출석) total 0.83, gap model_misuse
- Q: 내 과목들 중에 출석 제일 위험한거 뭐임
- tools: get_attendance, get_syllabus
- judge: 수치와 최위험 과목 판단은 맞지만, 운영체제 지각 환산 규칙과 현대사회와윤리 출석 비율 20%를 확인하지 않아 일부 누락이 있습니다.
- misuse: 현대사회와윤리 강의계획서를 조회하지 않았고, search_course_posts로 출석·지각 규정 공지를 찾지 않아 지각 환산 규칙과 출석 비율을 놓쳤습니다.
- fix: 출석 위험도를 비교할 때는 결석이 있는 모든 과목의 get_syllabus를 확인하고, search_course_posts(keyword='출석'/'지각')로 과목별 규정을 찾도록 유도해야 합니다.

### cc08 (휴강·강의실 변경) total 0.83, gap none
- Q: 오늘 수업 있음?
- tools: get_course_post, today_briefing
- judge: 요일을 정확히 인식해 토요일 수업 없음을 바로 답했고, 덧붙인 마감·변경 공지도 정확함. 다만 부가 정보가 다소 많음.

### cc09 (휴강·강의실 변경) total 0.83, gap other
- Q: 학교 전체 휴강하는 날 이번달에 있음? 축제같은거
- tools: academic_calendar, get_class_changes, school_notices
- judge: 도구를 적절히 썼고 정확합니다. 다만 마지막 문장이 단정적이고, 학교 공지를 확인하라는 안내가 빠졌습니다.
- fix: '못 찾음'에서 '평소처럼 수업'으로 단정하지 말고, 학교 공지나 총학 공지를 계속 확인하라고 안내하도록 응답 지침을 보강합니다.

### dl07 (마감·할 일) total 0.83, gap model_misuse
- Q: 다음주 화요일 전에 끝내야 되는거만
- tools: get_deadlines
- judge: 목록과 날짜, 18:00 함정 처리는 정확합니다. 다만 화요일 당일 마감인 ML 실습 4를 경계 항목으로 언급하지 않았습니다.
- misuse: 도구 결과에 있던 ML 실습 4(11/10 23:59)를 '전에'의 경계 항목으로 따로 알리지 않고 빼 버렸습니다.
- fix: '~전에'처럼 범위 경계가 애매하면 경계 당일 마감 항목을 별도로 덧붙이도록 안내합니다(예: "화요일 당일 마감: ML 실습 4").

### dl08 (마감·할 일) total 0.83, gap model_misuse
- Q: 윤리 토론 나 참여했나? 안했으면 언제까지임
- tools: get_course_overview, get_discussions
- judge: 핵심 사실(미참여 0/1, 11/9 23:59 마감)은 정확합니다. 다만 토론실에서 직접 확인하라는 안내와 참여 경로가 빠졌습니다.
- misuse: get_discussions 설명의 '참여 여부는 토론실에서 확인' 안내를 답변에 전달하지 않았습니다.
- fix: 토론 참여 여부를 답할 때는 과목 홈 집계(0/1)와 함께 'KLAS 토론실에서 직접 확인·작성'을 안내하도록 합니다.

### dl09 (마감·할 일) total 0.83, gap model_misuse
- Q: 이번 학기 과제 다 낸거 맞지? 밀린거 있나 ㅋㅋ
- tools: get_assignments, get_deadlines
- judge: 미제출 6개와 지각 기한은 정확하고 행동 안내도 좋습니다. 다만 제출 완료 과제를 보여 주지 않았고, 11/27 에세이를 '다음 주' 표에 넣은 사소한 분류 오류가 있습니다.
- misuse: get_assignments를 pending_only=true로만 불러 제출 완료 과제 목록을 확인·제시하지 못함
- fix: '다 낸 거 맞지?'처럼 전체 현황을 묻는 질문에는 get_assignments를 pending_only 없이 호출해 제출 완료 과제도 함께 보여 주도록 안내

### dn02 (학과 공지) total 0.83, gap model_misuse
- Q: 스탬프투어 커피쿠폰 그거 뭐임 ㅋㅋ
- tools: get_class_changes, get_course_post, get_courses, my_notices, read_school_notice, school_notices
- judge: 행사 내용 요약과 시간표 연계는 좋지만, 내 학부 공지가 아닌 단과대 공지를 출처로 써서 must_include의 학부 글·링크를 놓쳤습니다.
- misuse: my_notices 학과 공지 중 같은 제목의 여러 글 가운데 학생 소속 학부(정보융합학부) 글 no=3522 대신 인공지능융합대학 글 no=3524를 열었습니다.
- fix: 같은 제목 공지가 여러 게시판에 있으면 학생 소속 학과 게시판 글을 우선 고르도록 도구 설명에 안내하거나, 결과에서 소속 학과 글을 표시해 주세요.

## Gap tallies (primary_gap)

- none: 111
- model_misuse: 23
- missing_data: 8
- other: 4
- missing_tool: 3
- wrong_shaping: 1

- capability_missing: 16, model_misused_tools: 24

## Gap details

### missing_tool (3)
- dn10 [학과 공지] 공지 푸시 알림 기능 → 알림 기능이 없을 때는 대안만 짧게 안내하고, 추가 공지 목록은 학생이 원할 때만 보여 주도록 유도합니다.
- cp04 [셔틀·기숙사·도서관] 행복기숙사(happydorm) 공지사항 게시판을 조회하는 도구 → school_notices나 read_school_notice가 kw.happydorm.or.kr 공지사항을 읽을 수 있게 하거나, 기숙사 공지 전용 도구를 추가합니다.
- cp10 [셔틀·기숙사·도서관] 교내 프린터·전산실 위치 정보가 학교 안내 자료에 없음 → school_guide 자료에 교내 프린터·전산실(도서관 포함) 위치와 이용 방법을 추가

### missing_data (8)
- sn09 [학교 공지 찾기] 공지 DB에 휴학 관련 공지가 검색되지 않음 → 공지 DB에 학기별 휴·복학 신청 공지를 포함시키기
- dn08 [학과 공지] 정보융합학부 학과사무실 호실(위치) 데이터가 school_guide에 없음 → school_guide의 학과 연락처 항목에 학과사무실 호실과 학과 홈페이지 URL(aicon.kw.ac.kr 등)을 추가
- sc04 [장학] 정보융합학부 성적장학 자체 선발 기준(학과 내규)이 자료에 없음 → 학과별 성적장학 내규·선발 기준을 school_guide 자료에 추가하세요.
- at10 [출석] 학생용 출석 정정 절차·기한이 규정 자료에 없음 → '문서에 없음'을 '절차 없음'으로 바꾸지 말고 '학교 공통 절차는 확인하지 못했다'고 표현하도록 응답 지침을 보강하세요.
- mm09 [다전공] 학과별 복수전공 선발 기준(평점·정원) 데이터가 규정 자료에 없음 → school_guide에 다전공 선발 기준 존재 여부(학과별 상이 등)를 넣고, not_in_documents에 '선발 평점 기준'을 명시하세요. 모델에게는 미확인 사항을 '없음'으로 표현하지 않도록 안내하세요.
- cf07 [학식] 다음 주 식단 데이터가 아직 수집되지 않음 → 도구 결과의 note에 학교 식단 게시 시점이나 수집 시점을 넣어, 식단이 비어 있는 이유를 모델이 근거를 갖고 설명할 수 있게 하기.
- cf06 [학식] 함지마루 운영시간(특히 저녁) 정보를 주는 도구·데이터가 없음 → cafeteria_menu 결과에 식당 운영시간(조식·중식·석식) 필드를 추가하기.
- cp05 [셔틀·기숙사·도서관] 기숙사 중도 퇴사 시 기숙사비 환불 비율과 보증금 반환 기준 자료가 없음 → school_guide 자료에 행복기숙사 퇴사안내·환불 규정(일할 계산, 보증금 반환 시기)을 수집해 추가

### wrong_shaping (1)
- ac05 [첨부·이미지 공지 읽기] 본문 안 인라인 다운로드 링크(전공인정 신청서)를 첨부로 잡거나 읽을 수 없음 → read_school_notice가 본문의 파일 다운로드 링크(href)를 attachments나 links 필드로 돌려주고, attachment 번호로 읽을 수 있게 할 것

### model_misuse (23)
- ac01 [첨부·이미지 공지 읽기] search_course_posts·get_course_post로 '과제 2 제출 형식 안내' 게시글을 찾지 않고, 과제 첨부만 읽었습니다. → '제출형식 첨부'처럼 게시글 첨부를 묻는 질문이면 search_course_posts로 관련 글을 찾고, get_attachment_text(source=post)로 읽도록 해야 합니다.
- ac08 [첨부·이미지 공지 읽기] 검색 결과에 학생 학과(정보융합학부) 게시글 aicon-3512가 있었는데 읽지 않고 경력개발팀 원글 이미지만 읽었습니다. → 학과 게시판 공지(aicon-3512)도 images=true로 열어 참가기업 표가 따로 있는지 확인한 뒤 답하도록 유도하세요.
- dn01 [학과 공지] my_notices 결과의 department 필드('정보융합학부')를 무시하고 학부 글이 수집되지 않는다고 오독했습니다. → department 필드로 우리 학부 글과 단과대 공통 글을 구분해 표시하도록 서버 안내·도구 설명에 명시해야 합니다.
- dn02 [학과 공지] my_notices 학과 공지 중 같은 제목의 여러 글 가운데 학생 소속 학부(정보융합학부) 글 no=3522 대신 인공지능융합대학 글 no=3524를 열었습니다. → 같은 제목 공지가 여러 게시판에 있으면 학생 소속 학과 게시판 글을 우선 고르도록 도구 설명에 안내하거나, 결과에서 소속 학과 글을 표시해 주세요.
- dn05 [학과 공지] 결과에 학생 학부(정보융합학부) 공지 aicon-3512가 있었는데 경력개발팀 공지만 출처로 제시함. → 학과 공지 질문에서는 학생 소속 학부 게시판 글을 우선 출처로 제시하도록 안내 강화(예: school_notices 결과에서 학적 학과와 일치하는 글 표시).
- dn07 [학과 공지] 단대 공지의 게시 학부를 표시하지 않았고, 해당 없는 글(졸업작품 등)을 왜 뺐는지 구분해 설명하지 않았습니다. → 선별 결과를 보여 줄 때 각 글의 게시 학부를 표시하고, 제외한 글(졸업작품·타 학부용)은 대상이 아니라고 짧게 밝히도록 지시해야 합니다.
- sc07 [장학] 학사일정의 장학금 신청기간을 모든 장학금에 적용되는 것으로 과잉 일반화했습니다. → 학사일정 장학 신청기간은 교내(KLAS) 장학 기준이며, 교외·개별 장학은 각 공지를 확인하라고 한정해 말해야 합니다. KLAS 창 상태와 공지 사이의 불일치도 짚어 줘야 합니다.
- sc08 [장학] '또 하고싶다'는 질문인데 get_scholarships를 호출하지 않아 이전 근로장학 수혜 이력을 확인하지 않음. → 학생이 이전 수혜를 언급하면 get_scholarships로 이력을 확인해 답에 반영하도록 서버 안내에 명시.
- dl04 [마감·할 일] '형식'을 물었는데 search_course_posts·get_course_post·get_attachment_text로 게시판의 제출 형식 안내 공지와 첨부를 찾지 않고 과제 상세 하나로 끝냈습니다. → 제출 형식을 물으면 과제 상세와 함께 search_course_posts(keyword='과제 2' 또는 '형식')로 게시판 공지를 찾고, 첨부 파일을 읽어 요약하도록 유도해야 합니다. get_assignment_detail 설명에 '형식 안내 공지가 따로 있을 수 있음'을 넣는 것도 방법입니다.
- dl08 [마감·할 일] get_discussions 설명의 '참여 여부는 토론실에서 확인' 안내를 답변에 전달하지 않았습니다. → 토론 참여 여부를 답할 때는 과목 홈 집계(0/1)와 함께 'KLAS 토론실에서 직접 확인·작성'을 안내하도록 합니다.
- dl07 [마감·할 일] 도구 결과에 있던 ML 실습 4(11/10 23:59)를 '전에'의 경계 항목으로 따로 알리지 않고 빼 버렸습니다. → '~전에'처럼 범위 경계가 애매하면 경계 당일 마감 항목을 별도로 덧붙이도록 안내합니다(예: "화요일 당일 마감: ML 실습 4").
- dl09 [마감·할 일] get_assignments를 pending_only=true로만 불러 제출 완료 과제 목록을 확인·제시하지 못함 → '다 낸 거 맞지?'처럼 전체 현황을 묻는 질문에는 get_assignments를 pending_only 없이 호출해 제출 완료 과제도 함께 보여 주도록 안내
- ex04 [시험] 중간고사 글을 get_course_post로 열지 않고 본문 내용을 단정했습니다. → '검색으로는 찾지 못했다'로 표현하고, 열지 않은 글의 내용은 단정하지 말 것. 교수님 문의나 KLAS 게시판 재확인을 안내할 것.
- ex10 [시험] 학생이 학사일정의 졸업종합시험을 가리켰을 가능성이 큰데도 academic_calendar(또는 academic_deadlines)를 부르지 않아 11/2~11/13 일정을 놓쳤습니다. → '이거'처럼 지시어로 일정·행사를 물으면 academic_calendar로 해당 항목을 먼저 확인하도록 school_guide나 서버 안내에 힌트를 추가합니다.
- at04 [출석] 윤리 과목 게시판의 공결 반영 안내를 찾으려면 search_course_posts·get_course_post를 불러야 했는데 부르지 않아, 1~2주 반영 지연 정보를 놓쳤습니다. → 출석 반영 지연 질문이면 해당 과목 게시판을 '공결'·'출석' 키워드로 search_course_posts 하도록 get_attendance나 school_guide 결과의 안내에 넣으세요.
- at03 [출석] '다 똑같이 하면 되나'를 묻는 질문인데 search_course_posts로 과목별 공결 공지를 찾지 않았습니다. 학교 공지만 보고 모든 과목이 같다고 단정했습니다. → 과목별 절차를 묻는 질문에서는 수강 과목마다 search_course_posts(keyword='공결')를 호출하도록 해야 합니다. 확인하지 못한 과목은 '각 과목 공지·교수 확인 필요'로 남기도록 지시하세요.
- at06 [출석] 현대사회와윤리 강의계획서를 조회하지 않았고, search_course_posts로 출석·지각 규정 공지를 찾지 않아 지각 환산 규칙과 출석 비율을 놓쳤습니다. → 출석 위험도를 비교할 때는 결석이 있는 모든 과목의 get_syllabus를 확인하고, search_course_posts(keyword='출석'/'지각')로 과목별 규정을 찾도록 유도해야 합니다.
- gr10 [성적·재수강] academic_calendar·academic_deadlines를 호출하지 않아 동계 계절수업 수강신청·수업 일정을 놓쳤습니다. → 계절학기 질문에는 academic_calendar(또는 academic_deadlines)로 계절수업 일정을 함께 조회하도록 school_guide 결과나 서버 안내에서 유도해야 합니다(not_in_documents의 '수강신청 일정 없음' 항목에 학사일정 도구를 쓰라는 힌트 추가).
- rg06 [수강신청·정정·포기] school_guide 결과만 쓰고 FAQ 원문을 read_school_notice로 열어 작성·수정 시점을 확인하지 않았습니다. 그 결과 오래된 자료라는 경고를 하지 못했습니다. → FAQ처럼 오래된 출처를 인용할 때는 원문 날짜를 확인하세요. '2020년 글이라 현재와 다를 수 있으니 최신 수강신청 공고를 확인하라'는 문구도 넣으세요.
- rg09 [수강신청·정정·포기] search_course_posts로 운영체제 과목의 결석 기준 공지를 찾지 않고 학칙 일반 기준만 사용했습니다. → 출결·F 판단 질문에서는 search_course_posts(keyword='결석')로 과목별 기준 공지를 확인하도록 유도해야 합니다.
- lv07 [휴학·복학] academic_calendar나 academic_deadlines를 부르지 않아 동계 계절수업 수강신청·수업 기간을 확인하지 않고 '확인 못 함'으로 넘겼습니다. → 계절학기 질문에서는 academic_calendar(또는 academic_deadlines)로 계절수업 일정을 함께 조회하도록 school_guide의 not_in_documents 항목에 '학사일정 도구로 확인' 힌트를 넣어야 합니다.
- lv06 [휴학·복학] search_course_posts와 get_course_post로 운영체제 과목 공지('결석 처리 기준 안내')를 찾지 않았습니다. 강의계획서와 학교 규정만으로 기준을 설명했습니다. → 출결 질문에는 과목 게시판에서 '결석'·'출석'을 검색해 교수 공지 원문을 확인하도록 유도해야 합니다. 예: get_attendance 결과에 search_course_posts 권장 문구를 추가합니다.
- cp03 [셔틀·기숙사·도서관] academic_calendar를 부르지 않아 기말고사 기간을 확인하지 않았습니다. → '기말 기간' 같은 질문에는 academic_calendar로 시험 기간을 함께 확인해 제시하도록 해야 합니다.

### other (4)
- cc09 [휴강·강의실 변경] 도구를 적절히 썼고 정확합니다. 다만 마지막 문장이 단정적이고, 학교 공지를 확인하라는 안내가 빠졌습니다. → '못 찾음'에서 '평소처럼 수업'으로 단정하지 말고, 학교 공지나 총학 공지를 계속 확인하라고 안내하도록 응답 지침을 보강합니다.
- ex07 [시험] 데이터와 근거는 정확합니다. 다만 '온라인으로 봐요'라고 단정해 must_not을 어겼습니다. 이 단정은 도구 데이터가 강하게 뒷받침하므로, 케이스 기대치와 데이터가 어긋났을 가능성이 있습니다. → KLAS에 온라인시험이 등록돼 있다는 근거를 들면서도 '현재 등록 기준으로는 온라인'처럼 단서를 붙여 답하게 하세요. 또는 데이터가 온라인을 명확히 보여 주는 경우 케이스의 must_not을 재검토하세요.
- ex09 [시험] 도구를 잘 써서 확인된 일정은 정확하게 비교했고 AI 온라인시험까지 찾아냈습니다. 다만 운체·윤리는 가정에 기댄 추측성 분석을 덧붙여 약간 감점했습니다. → 공지가 없는 과목은 수업 시간을 가정해 겹침 여부를 판단하지 말고, '미확인, 교수 공지 또는 문의로 확인 필요'로만 표시하세요.
- at01 [출석] 출석 데이터와 학교 규정을 근거와 함께 잘 정리했고, 운영체제 규칙을 옮겨 쓰는 함정도 피했습니다. 다만 F가 아니라는 단정 어조, 추정 수업 횟수에 기댄 안전 범위, 교수 확인 안내 누락이 아쉽습니다. → 학교 규정 기준 판단은 참고용이라고 밝히고, 과목별 출석·지각 기준은 담당 교수(최교수 이메일·연구실 전화)에게 확인하도록 안내해야 합니다. 총 수업 횟수 추정에서 나온 '안전 범위'는 단정하지 않아야 합니다.

## Tool use

school_guide 65, school_notices 53, get_course_post 23, search_course_posts 20, get_courses 18, get_grades 18, read_school_notice 16, get_class_changes 14, academic_deadlines 14, get_academic_status 13, my_notices 10, get_scholarships 10, simulate_graduation 10, get_attendance 10, academic_calendar 9, get_exam_info 9, get_syllabus 8, cafeteria_menu 8, get_assignment_detail 7, explore_multi_major 6, get_assignments 5, get_online_lectures 3, get_deadlines 3, get_graduation_progress 3, get_attachment_text 2, get_course_overview 2, get_online_tests 2, today_briefing 1, this_week 1, get_team_projects 1, get_discussions 1, get_course_evaluation 1, get_quizzes 1, department_curriculum 1, klas_status 1

