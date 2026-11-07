# Eval summary: round 3

- cases graded: 150 (ok 150, truncated 0), errors: 0
- mean total: 0.916 ± 0.016 (95% CI)
- failing: 16
- answer cost: $9.35, judge cost: $7.23, ledger eval total: $49.74
- model: claude-opus-5-5, effort answer/judge: medium/medium
- provisional tools: {}

## Per category

| category | n | total | correct | sourced | actionable | honest | no_hallucination | scope | failing | top gap | Δ vs prev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 마감·할 일 | 10 | 0.89 | 1.70 | 1.50 | 1.90 | 1.80 | 1.80 | 2.00 | 0 | model_misuse 4 | +0.00 |
| 휴강·강의실 변경 | 10 | 0.90 | 1.90 | 1.70 | 1.80 | 1.60 | 2.00 | 1.80 | 1 | model_misuse 1, other 1 | -0.00 |
| 시험 | 10 | 0.96 | 1.90 | 1.90 | 1.90 | 1.90 | 2.00 | 1.90 | 0 | model_misuse 1 | +0.04 |
| 출석 | 10 | 0.93 | 1.70 | 2.00 | 2.00 | 1.90 | 1.80 | 1.80 | 0 | model_misuse 3 | +0.07 |
| 성적·재수강 | 10 | 0.96 | 2.00 | 2.00 | 2.00 | 1.80 | 1.90 | 1.80 | 0 | - | +0.02 |
| 장학 | 10 | 0.95 | 1.90 | 2.00 | 2.00 | 1.90 | 2.00 | 1.60 | 1 | missing_data 1, model_misuse 1 | +0.03 |
| 졸업요건 | 10 | 0.88 | 1.70 | 1.90 | 2.00 | 1.70 | 1.80 | 1.50 | 2 | model_misuse 2, missing_data 1 | -0.03 |
| 다전공 | 10 | 0.90 | 1.90 | 2.00 | 2.00 | 1.80 | 1.60 | 1.50 | 0 | model_misuse 2 | +0.03 |
| 수강신청·정정·포기 | 10 | 0.91 | 1.70 | 2.00 | 2.00 | 1.60 | 1.80 | 1.80 | 2 | model_misuse 3, missing_data 1 | -0.04 |
| 휴학·복학 | 10 | 0.88 | 1.80 | 1.80 | 1.90 | 1.70 | 1.80 | 1.60 | 3 | model_misuse 3, missing_data 1 | +0.05 |
| 학식 | 10 | 0.87 | 1.90 | 1.50 | 2.00 | 1.70 | 1.50 | 1.80 | 3 | missing_tool 1, model_misuse 1 | +0.00 |
| 셔틀·기숙사·도서관 | 10 | 0.97 | 1.90 | 2.00 | 2.00 | 2.00 | 1.80 | 2.00 | 1 | model_misuse 2, missing_data 1 | -0.00 |
| 학교 공지 찾기 | 10 | 0.93 | 1.90 | 2.00 | 2.00 | 1.80 | 1.80 | 1.60 | 1 | other 1, missing_data 1 | +0.02 |
| 학과 공지 | 10 | 0.91 | 1.70 | 1.90 | 2.00 | 1.90 | 1.90 | 1.50 | 0 | model_misuse 3 | +0.06 |
| 첨부·이미지 공지 읽기 | 10 | 0.89 | 1.90 | 1.80 | 1.90 | 1.80 | 1.80 | 1.50 | 2 | model_misuse 1, missing_data 1 | -0.01 |

## Worst 20

### ac01 (첨부·이미지 공지 읽기) total 0.42, gap model_misuse
- Q: 디비 과제2 제출형식 첨부 뭐라고 써있음
- tools: get_assignment_detail, get_attachment_text
- judge: 마감·미제출 정보는 맞았습니다. 그러나 질문이 가리킨 게시글 첨부(과제2_제출형식.docx)를 찾지 않고 다른 첨부를 요약했고, 제출 형식이 본문에만 있다고 근거 없이 단정했습니다.
- 0점 honest: 게시판을 확인하지 않고 '제출 형식은 과제 본문에만 있어요'라고 단정했습니다. 별도 안내 글이 있는데 '못 찾음'을 '없음'처럼 말한 셈입니다.
- misuse: search_course_posts·get_course_post로 '과제 2 제출 형식 안내' 게시글을 찾지 않고 과제 첨부만 읽었습니다. 그 뒤 제출 형식이 본문에만 있다고 단정했습니다.
- fix: 질문에 '제출형식 첨부'처럼 특정 글을 가리키는 말이 있으면 search_course_posts(keyword='제출 형식')로 게시판을 먼저 찾고, get_course_post와 get_attachment_text(source='post')로 해당 첨부를 읽도록 유도해야 합니다. get_attachment_text 설명에 '과제 첨부와 게시글 첨부가 다를 수 있음'을 명시하는 것도 방법입니다.

### cf09 (학식) total 0.50, gap model_misuse
- Q: 12/14 데베 기말 끝나고 학식 하나 그날 메뉴 뭐임
- tools: cafeteria_menu, get_course_post, get_exam_info
- judge: 시험 정보와 메뉴 미등록 안내는 정확합니다. 그러나 휴무 여부와 점심 시간 내 식사 가능을 근거 없이 단정해 must_not을 어겼습니다.
- 0점 honest: 학사일정을 확인하지 않고 '쉬는 날은 아니다'라고 단정해 must_not(운영 여부 단정)을 어겼습니다.
- 0점 no_hallucination: 휴무 여부와 점심 운영 시간을 근거 없이 단정했습니다. 식단이 보통 그 주에 올라온다는 근거 없는 일반론도 있습니다.
- misuse: academic_calendar를 확인하지 않고 12/14 운영·휴무 여부를 단정했고, 학식 운영 시간도 근거 없이 추정했습니다.
- fix: 운영 여부는 academic_calendar로 확인한 뒤 말하고, 확인하지 못했으면 '운영 여부와 시간은 확인 못 함'이라고 쓰도록 합니다. 식단 미수집 note를 운영 판단 근거로 쓰지 않게 합니다.

### gd09 (졸업요건) total 0.58, gap model_misuse
- Q: 졸업종합시험 지금 하는거임? 나도 봐야됨?
- tools: my_notices, school_guide, school_notices, simulate_graduation
- judge: 학칙 기반 대체요건 설명과 학과 사무실 안내는 좋았다. 하지만 학사일정을 확인하지 않아 지금 진행 중인 졸업종합시험 기간을 놓쳤고, 3학년은 대상이 아니라고 단정했다.
- 0점 correct: 학사일정상 졸업종합시험 기간(11/2~11/13)이 지금인데 '지금 볼 차례 아니다', '관련 공지 없다'고 답해 핵심 질문을 틀렸다.
- 0점 honest: 학과 요건을 확인하지 못했다고 하면서도 3학년은 이번 학기 대상이 아니라고 단정했다. 공지 검색에서 못 찾은 것을 근거로 지금은 시험 시기가 아니라는 식으로 결론 냈다.
- misuse: '지금 하는 거냐'는 날짜 질문인데 academic_calendar(또는 academic_deadlines)를 부르지 않았다. 공지 검색 결과만 보고 시험 기간이 아니라고 판단했다.
- fix: '지금/언제' 같은 시기 질문에는 academic_calendar를 먼저 조회하게 한다. school_notices 결과가 비면 학사일정 확인을 권하는 안내를 도구 설명에 넣는다.

### cc06 (휴강·강의실 변경) total 0.67, gap model_misuse
- Q: 월요일 디비 휴강 공지 있었나
- tools: get_class_changes, get_courses, search_course_posts
- judge: 도구는 제대로 썼고 근거 제시도 좋습니다. 다만 첫 문장에서 휴강이 없고 수업이 정상 진행된다고 단정해 '못 찾음≠없음' 함정에 걸렸습니다.
- 0점 honest: '공지는 없어요', '원래대로 해요'로 시작해 못 찾음을 없음으로 단정했습니다. 끝에 단서를 달았지만 must_not 위반입니다.
- misuse: get_class_changes의 note('여기 없다고 휴강이 아니라는 뜻은 아님')를 첫 문장에 반영하지 않고 수업이 정상 진행된다고 단정함
- fix: 검색에서 못 찾은 경우 '찾지 못했어요, 평소대로라면 월 3교시 새빛관 203'처럼 조건부로 말하도록 시스템 안내를 강화하고, 단서를 답변 앞부분에 두게 하세요.

### cf07 (학식) total 0.67, gap none
- Q: 다음주 학식 메뉴 한번에 보여줘
- tools: cafeteria_menu
- judge: 날짜 계산과 날짜별 조회는 정확했고, 빈 날도 지어내지 않았습니다. 업로드 시점 추정과 공휴일 단정이 근거 없는 사소한 흠입니다.
- fix: 메뉴 업로드 시점 같은 근거 없는 패턴은 말하지 않습니다. 공휴일 여부는 academic_calendar로 확인하거나 '확인하지 않음'으로 표현합니다.

### lv02 (휴학·복학) total 0.67, gap model_misuse
- Q: 군휴학 하려면 뭐 내야돼? 입영통지서만 있으면 됨?
- tools: school_guide
- judge: 출처와 절차 안내는 좋습니다. 하지만 '입영통지서 사본 하나만 있으면 된다'고 단정해 must_not을 어겼습니다.
- 0점 honest: 자료에 없는 '이것만으로 충분'을 단정해 must_not을 어겼습니다. 신청 기간 불일치와 성적 처리 불명확은 솔직히 알렸습니다.
- misuse: 도구 결과는 '입영통지서 사본 첨부'만 말했는데, 이를 '하나만 있으면 된다'로 과잉 해석했습니다.
- fix: 자료에 명시된 서류(입영통지서 사본)만 전하고, 다른 서류가 필요한지는 교육지원팀에 확인하라고 덧붙여야 합니다.

### rg06 (수강신청·정정·포기) total 0.67, gap model_misuse
- Q: 수강신청 프로그램 따로 깔아야됨?
- tools: school_guide
- judge: FAQ 링크와 설치 경로, 문의처는 잘 제시했습니다. 하지만 2020년 FAQ 기반 정보를 최신인 것처럼 단정했고, 최근 공지 확인도 하지 않았습니다.
- 0점 honest: 2020년 리뉴얼 FAQ에 기반한 정보인데 현재와 다를 수 있다는 경고 없이 '네, 따로 설치해야 해요'라고 단정해 must_not을 어겼습니다. 신뢰도 '중간' 표기만으로는 부족합니다.
- misuse: school_notices로 최근 수강신청 공지를 찾거나 read_school_notice로 FAQ를 열어 최신 여부를 확인하지 않았습니다. 오래된 자료라는 점도 학생에게 알리지 않았습니다.
- fix: 출처 날짜가 오래된 경우(2020년 FAQ) 현재와 다를 수 있다고 명시하도록 해야 합니다. 또 school_notices로 최근 수강신청 자료집·공지를 확인한 뒤 답하도록 유도해야 합니다.

### cf08 (학식) total 0.75, gap missing_tool
- Q: 학식 말고 학교 근처 맛집 ㅊㅊ
- tools: (none)
- judge: 도구 한계를 정직하게 밝히고 가게 이름을 지어내지 않은 좋은 답변입니다. 다만 동네별 일반론은 근거가 없습니다.
- missing: 학교 주변 식당 정보 도구가 없음
- fix: 범위 밖 질문에는 도구 한계를 알리고 검색 방법만 짧게 안내하도록 하며, 확인되지 않은 동네별 특징 서술은 줄이게 합니다.

### dl04 (마감·할 일) total 0.75, gap model_misuse
- Q: 디비 과제2 pdf로 내는거 맞나? 형식 뭐였더라
- tools: get_assignment_detail
- judge: 과제 상세 기준으로는 정확하지만, 게시판의 형식 안내 공지와 첨부 docx를 확인하지 않아 핵심 must_include 두 개를 놓쳤습니다.
- misuse: '형식'을 물었는데 search_course_posts·get_course_post·get_attachment_text로 게시판의 제출 형식 안내 공지와 첨부를 찾아 읽지 않고, 과제 상세 하나만 보고 끝냈습니다.
- fix: 형식·제출 방법 질문에는 과제 상세 뒤에 search_course_posts(keyword='과제2' 또는 '형식')로 관련 공지를 찾고, 첨부가 있으면 get_attachment_text로 읽도록 유도해야 합니다.

### dn02 (학과 공지) total 0.75, gap model_misuse
- Q: 스탬프투어 커피쿠폰 그거 뭐임 ㅋㅋ
- tools: get_class_changes, get_course_post, get_courses, get_grades, my_notices, read_school_notice, school_notices
- judge: 내용은 정확하고 실용적이지만, 내 학부 게시글 대신 단과대 게시글을 골라 출처 링크가 기대와 다릅니다.
- misuse: my_notices 결과에서 department가 '정보융합학부'인 3522 글 대신 '인공지능융합대학' 3524 글을 열어 출처로 씀
- fix: 같은 제목 글이 여러 개면 학생 학과(department_scope.department)와 일치하는 글을 우선 고르라고 도구 설명이나 서버 안내에 명시하기

### lv01 (휴학·복학) total 0.75, gap missing_data
- Q: 휴학 신청 언제까지임?? 이번주 안에 해야되나
- tools: academic_calendar, academic_deadlines, school_guide, school_notices
- judge: 도구를 적절히 써서 일정을 찾지 못했다고 밝히고 교육지원팀을 안내했습니다. 다만 첫 문장의 단정과 시기 추정이 약간 아쉽습니다.
- missing: 학사일정·공지 DB에 다음 학기 휴학 신청 일정이 없음
- fix: 결론 문장을 '학사일정·공지에서 이번 주 휴학 마감은 찾지 못했다'처럼 확인 범위를 밝혀 쓰고, 시기 추정 표현은 빼야 합니다.

### rg03 (수강신청·정정·포기) total 0.75, gap model_misuse
- Q: 지금 수강포기 됨? 확통 망한듯ㅠㅠ
- tools: academic_calendar, academic_deadlines, school_guide, school_notices
- judge: 수강포기 불가 결론과 대안 안내는 좋지만, KLAS 취득학점포기 상태를 빠뜨렸고 마감일을 다소 단정했습니다.
- misuse: academic_deadlines 결과의 drop_earned_credits(open=false)를 답변에 반영하지 않았고, 취득학점포기 제도를 설명하지 않았습니다.
- fix: academic_deadlines의 drop_earned_credits 상태를 함께 알리고, 수강포기와 취득학점포기가 다른 제도임을 구분해 설명합니다. 1/4선 마감은 추정임을 밝히고 공지로 확인하라고 안내합니다.

### sn09 (학교 공지 찾기) total 0.75, gap missing_data
- Q: 자퇴 말고 휴학 신청 공지 ㄱ
- tools: academic_deadlines, school_guide, school_notices
- judge: 자퇴 FAQ 함정은 피했고 신청 방법과 교육지원팀 안내도 좋습니다. 다만 첫 문장에서 '공지 없음'으로 단정했고, 확인하지 않은 과거 학기 패턴을 언급해 감점했습니다.
- missing: 공지 DB에 휴학 신청 관련 공지가 없음
- fix: 검색 결과가 비었을 때 '공지가 없다'가 아니라 '찾지 못했다'로 말하도록 서버 안내를 강화하세요. 확인하지 않은 과거 학기 패턴은 말하지 않게 하세요.

### ac03 (첨부·이미지 공지 읽기) total 0.83, gap none
- Q: 확통 과제3 뭐 내라는거야 첨부 있음?
- tools: get_assignment_detail
- judge: 정확하고 간결한 답변입니다. 18:00 마감 함정도 피했습니다. 출처 표기가 없고 '1개'라는 근거 없는 사소한 세부만 아쉽습니다.
- fix: 출처(KLAS 과제 상세)를 한 줄 밝히고, 데이터에 없는 '1개' 같은 세부는 빼기.

### at03 (출석) total 0.83, gap model_misuse
- Q: 예비군 갔다왔는데 공결 어케 신청함? 다 똑같이 하면 되나
- tools: school_guide
- judge: 학교 공지 기반의 예비군 일괄 처리 안내는 정확하고 근거도 분명합니다. 하지만 과목 게시판을 검색하지 않아 현대사회와윤리 공지 내용과 과목별 확인 필요성을 빠뜨렸습니다.
- misuse: 과목별 공결 절차를 확인하려면 search_course_posts·get_course_post로 과목 게시판을 찾아야 했는데, school_guide만 호출했습니다.
- fix: '다 똑같이?'처럼 과목별 차이를 묻는 질문에는 수강 과목별로 search_course_posts(keyword='공결')를 호출해야 합니다. 과목 공지가 있으면 학교 기준과 함께 안내하고, 공지가 없는 과목은 교수 확인이 필요하다고 명시해야 합니다.

### at04 (출석) total 0.83, gap model_misuse
- Q: 윤리 공결 냈는데 klas엔 아직 결석으로 뜸 왜이럼
- tools: get_attendance, school_guide
- judge: 출석 기록과 공결 절차 안내는 정확합니다. 다만 과목 공지를 조회하지 않아 반영 기간 정보가 빠졌습니다.
- misuse: search_course_posts와 get_course_post로 과목 공지를 확인하지 않아 반영 기간(1~2주) 정보를 놓쳤습니다.
- fix: 출석 반영 질문이면 해당 과목 게시판을 '공결'·'출석'으로 검색해 교수 공지를 확인하도록 유도해야 합니다.

### at06 (출석) total 0.83, gap model_misuse
- Q: 내 과목들 중에 출석 제일 위험한거 뭐임
- tools: get_attendance, get_syllabus, school_guide
- judge: 출석 수치와 결론은 정확하고 근거도 잘 밝혔습니다. 다만 다른 위험 과목의 출석 비율과 과목별 지각 규칙을 확인하지 않아 비교가 불완전합니다.
- misuse: 결석이 있는 운영체제·현대사회와윤리의 강의계획서와 출석 공지를 조회하지 않았습니다(get_syllabus·search_course_posts). 그래서 과목별 지각 기준과 출석 비율 20%를 놓쳤습니다.
- fix: 막연한 '제일 위험' 비교에서는 결석·지각이 있는 모든 과목의 get_syllabus(출석 비율)와 search_course_posts('출석')를 확인하도록 유도해야 합니다.

### cc08 (휴강·강의실 변경) total 0.83, gap none
- Q: 오늘 수업 있음?
- tools: get_course_post, today_briefing
- judge: 요일을 정확히 인식해 토요일 수업 없음을 바로 답했고, 덧붙인 마감·변경 공지도 정확함. 다만 부가 정보가 다소 많음.

### cc09 (휴강·강의실 변경) total 0.83, gap other
- Q: 학교 전체 휴강하는 날 이번달에 있음? 축제같은거
- tools: academic_calendar, get_class_changes, school_notices
- judge: 도구를 적절히 썼고 정확합니다. 다만 마지막 문장이 단정적이고, 학교 공지를 확인하라는 안내가 빠졌습니다.
- fix: '못 찾음'에서 '평소처럼 수업'으로 단정하지 말고, 학교 공지나 총학 공지를 계속 확인하라고 안내하도록 응답 지침을 보강합니다.

### cf02 (학식) total 0.83, gap none
- Q: 월욜 학식 뭐나옴
- tools: cafeteria_menu
- judge: 날짜 계산과 정직한 '아직 없음' 안내는 정확하다. 게시 시점과 공휴일 여부에 근거 없는 사소한 추정이 있다.
- fix: 게시 시점이나 공휴일 여부는 확인한 경우에만 말하고, 그렇지 않으면 '확인 못 함'으로 표현하도록 한다.

## Gap tallies (primary_gap)

- none: 112
- model_misuse: 27
- missing_data: 7
- other: 2
- missing_tool: 2

- capability_missing: 15, model_misused_tools: 25

## Gap details

### missing_tool (2)
- lv08 [휴학·복학] 휴학·복학 신청 내역과 처리 상태를 조회하는 도구 → KLAS 학적관리 휴복학신청 내역(신청일·처리 상태)을 읽는 도구를 추가.
- cf08 [학식] 학교 주변 식당 정보 도구가 없음 → 범위 밖 질문에는 도구 한계를 알리고 검색 방법만 짧게 안내하도록 하며, 확인되지 않은 동네별 특징 서술은 줄이게 합니다.

### missing_data (7)
- ac05 [첨부·이미지 공지 읽기] 본문 안 '신청서 다운로드' 링크 파일이 attachments에 잡히지 않아, 도구로 신청서 서식을 읽을 수 없음 → read_school_notice가 본문 내 다운로드 링크(파일 링크)도 첨부처럼 추출해 읽을 수 있게 하기
- sn09 [학교 공지 찾기] 공지 DB에 휴학 신청 관련 공지가 없음 → 검색 결과가 비었을 때 '공지가 없다'가 아니라 '찾지 못했다'로 말하도록 서버 안내를 강화하세요. 확인하지 않은 과거 학기 패턴은 말하지 않게 하세요.
- sc04 [장학] 정보융합학부 성적장학 자체 기준과 학기별 선발 커트라인 자료가 없음 → 학과별 성적장학 내규·선발 기준을 school_guide 데이터에 추가하기
- gd07 [졸업요건] 학과별 졸업논문·대체요건 세부 기준 데이터가 없음 → school_guide나 simulate_graduation에 학과별 졸업논문·졸업작품 요구 여부 자료(학과 내규·학과 홈페이지)를 추가하세요.
- rg05 [수강신청·정정·포기] 2027학년도 1학기 수강신청 일정이 학사일정·공지에 아직 없음 → 학사일정에 다음 학기 수강신청 일정이 반영되면 자동으로 노출되게 하고, 학생 소속 단과대의 신청일 차수를 함께 계산해 주면 좋음
- lv01 [휴학·복학] 학사일정·공지 DB에 다음 학기 휴학 신청 일정이 없음 → 결론 문장을 '학사일정·공지에서 이번 주 휴학 마감은 찾지 못했다'처럼 확인 범위를 밝혀 쓰고, 시기 추정 표현은 빼야 합니다.
- cp05 [셔틀·기숙사·도서관] 기숙사비 중도 퇴사 환불 기준 데이터가 school_guide와 공지 DB에 없음 → 행복기숙사 퇴사안내·환불 규정 페이지를 school_guide 자료에 추가하고, 답변에서 근거 없는 일반론('보통 ~')은 빼도록 안내

### model_misuse (27)
- dl04 [마감·할 일] '형식'을 물었는데 search_course_posts·get_course_post·get_attachment_text로 게시판의 제출 형식 안내 공지와 첨부를 찾아 읽지 않고, 과제 상세 하나만 보고 끝냈습니다. → 형식·제출 방법 질문에는 과제 상세 뒤에 search_course_posts(keyword='과제2' 또는 '형식')로 관련 공지를 찾고, 첨부가 있으면 get_attachment_text로 읽도록 유도해야 합니다.
- dl08 [마감·할 일] 핵심 사실(0/1, 11/9 23:59 마감)은 정확함. 토론실 직접 확인 안내가 빠져 must_include 하나를 놓침. → get_discussions 설명에 있는 '참여 여부는 토론실에서 확인' 안내를 답변에 반영하도록 하고, 토론 참여 질문에는 KLAS 토론실 확인 문구를 넣게 함.
- dl07 [마감·할 일] 도구 결과에 있던 ML 실습 4(11/10 23:59 마감)를 빼고, '전에'의 경계 해석에 대해 언급하지 않았습니다. → '~전에'처럼 경계가 애매한 질문에서는 경계일 당일 마감 항목(ML 실습 4, 화 23:59)을 따로 짚어 주도록 해야 합니다.
- dl09 [마감·할 일] get_assignments를 pending_only=true로만 불러 제출 완료 과제를 확인하지 않았습니다. → '다 냈는지' 묻는 질문에는 get_assignments를 pending_only 없이 불러 제출 완료와 미제출을 함께 보여 주도록 유도해야 합니다.
- ac01 [첨부·이미지 공지 읽기] search_course_posts·get_course_post로 '과제 2 제출 형식 안내' 게시글을 찾지 않고 과제 첨부만 읽었습니다. 그 뒤 제출 형식이 본문에만 있다고 단정했습니다. → 질문에 '제출형식 첨부'처럼 특정 글을 가리키는 말이 있으면 search_course_posts(keyword='제출 형식')로 게시판을 먼저 찾고, get_course_post와 get_attachment_text(source='post')로 해당 첨부를 읽도록 유도해야 합니다. get_attachment_text 설명에 '과제 첨부와 게시글 첨부가 다를 수 있음'을 명시하는 것도 방법입니다.
- dn02 [학과 공지] my_notices 결과에서 department가 '정보융합학부'인 3522 글 대신 '인공지능융합대학' 3524 글을 열어 출처로 씀 → 같은 제목 글이 여러 개면 학생 학과(department_scope.department)와 일치하는 글을 우선 고르라고 도구 설명이나 서버 안내에 명시하기
- dn06 [학과 공지] category를 정보융합학부로만 걸러 검색해서, 인공지능융합대학 게시판 전체의 '졸업작품' 글(타 학부 전시회)을 찾지 못했습니다. 그래서 타 학부 글과 구분해 안내하지 못했습니다. → 학과 필터 결과가 비면 단과대 category(인공지능융합대학)로 '졸업작품'·'전시회'를 다시 검색하세요. 그리고 다른 학과 글은 어느 학과 것인지 명시하라고 도구 설명에 안내하세요.
- dn05 [학과 공지] 공지·시간표·휴강을 잘 결합했습니다. 다만 학생 학부 공지 링크와 확률과통계 강의실이 누락됐습니다. → 검색 결과 중 학생 소속 학부(정보융합학부) 공지를 우선 인용·링크하고, 시간표 강의실을 빠짐없이 적도록 합니다.
- sc08 [장학] '또 하고싶다'는 질문인데 get_scholarships로 이전 근로장학 수혜 이력을 확인하지 않았습니다. → '또', '다시' 같은 개인 이력 표현이 있는 장학 질문에서는 get_scholarships를 먼저 호출하도록 school_guide나 get_scholarships 설명에 안내를 넣으세요.
- cc06 [휴강·강의실 변경] get_class_changes의 note('여기 없다고 휴강이 아니라는 뜻은 아님')를 첫 문장에 반영하지 않고 수업이 정상 진행된다고 단정함 → 검색에서 못 찾은 경우 '찾지 못했어요, 평소대로라면 월 3교시 새빛관 203'처럼 조건부로 말하도록 시스템 안내를 강화하고, 단서를 답변 앞부분에 두게 하세요.
- ex10 [시험] academic_calendar나 academic_deadlines를 호출하지 않아 학사일정의 졸업종합시험 기간(11/2~11/13)을 놓쳤습니다. → '○○시험' 질문에는 academic_calendar로 학사일정상 기간을 함께 확인하도록 school_guide·서버 안내에 힌트를 추가합니다.
- at03 [출석] 과목별 공결 절차를 확인하려면 search_course_posts·get_course_post로 과목 게시판을 찾아야 했는데, school_guide만 호출했습니다. → '다 똑같이?'처럼 과목별 차이를 묻는 질문에는 수강 과목별로 search_course_posts(keyword='공결')를 호출해야 합니다. 과목 공지가 있으면 학교 기준과 함께 안내하고, 공지가 없는 과목은 교수 확인이 필요하다고 명시해야 합니다.
- at04 [출석] search_course_posts와 get_course_post로 과목 공지를 확인하지 않아 반영 기간(1~2주) 정보를 놓쳤습니다. → 출석 반영 질문이면 해당 과목 게시판을 '공결'·'출석'으로 검색해 교수 공지를 확인하도록 유도해야 합니다.
- at06 [출석] 결석이 있는 운영체제·현대사회와윤리의 강의계획서와 출석 공지를 조회하지 않았습니다(get_syllabus·search_course_posts). 그래서 과목별 지각 기준과 출석 비율 20%를 놓쳤습니다. → 막연한 '제일 위험' 비교에서는 결석·지각이 있는 모든 과목의 get_syllabus(출석 비율)와 search_course_posts('출석')를 확인하도록 유도해야 합니다.
- gd09 [졸업요건] '지금 하는 거냐'는 날짜 질문인데 academic_calendar(또는 academic_deadlines)를 부르지 않았다. 공지 검색 결과만 보고 시험 기간이 아니라고 판단했다. → '지금/언제' 같은 시기 질문에는 academic_calendar를 먼저 조회하게 한다. school_notices 결과가 비면 학사일정 확인을 권하는 안내를 도구 설명에 넣는다.
- gd08 [졸업요건] school_guide 결과에 있던 2018년 FAQ URL을 답변 근거 목록에 넣지 않았습니다. → 출처 간 불일치를 언급할 때는 해당 출처(2018 FAQ) 링크도 함께 제시하도록 유도하고, 질문과 무관한 졸업 잔여 학점 섹션은 줄이세요.
- mm06 [다전공] explore_multi_major를 부르지 않았다. 과목별 인정 계산이 불가능하다는 한계를 알리는 대신 계산해 주겠다고 과잉 약속했다. → 과목별 상호인정 여부는 도구가 판정·계산하지 않는다고 명시하도록 유도해야 한다. explore_multi_major 설명에 '과목별 인정 여부 미계산'을 적고, 해당 학과 사무실·교육지원팀·Daple 확인을 안내하게 한다.
- mm09 [다전공] 개인 평점을 묻는 질문인데 get_grades를 호출하지 않아 실제 평점 3.52를 확인하지 않았습니다. → 평점이 들어간 다전공 질문에서는 get_grades로 실제 평점을 함께 확인하도록 유도하고, Daple(https://daple.kwuniv.com)·학과사무실 안내를 how_to에 포함하세요.
- rg03 [수강신청·정정·포기] academic_deadlines 결과의 drop_earned_credits(open=false)를 답변에 반영하지 않았고, 취득학점포기 제도를 설명하지 않았습니다. → academic_deadlines의 drop_earned_credits 상태를 함께 알리고, 수강포기와 취득학점포기가 다른 제도임을 구분해 설명합니다. 1/4선 마감은 추정임을 밝히고 공지로 확인하라고 안내합니다.
- rg06 [수강신청·정정·포기] school_notices로 최근 수강신청 공지를 찾거나 read_school_notice로 FAQ를 열어 최신 여부를 확인하지 않았습니다. 오래된 자료라는 점도 학생에게 알리지 않았습니다. → 출처 날짜가 오래된 경우(2020년 FAQ) 현재와 다를 수 있다고 명시하도록 해야 합니다. 또 school_notices로 최근 수강신청 자료집·공지를 확인한 뒤 답하도록 유도해야 합니다.
- rg09 [수강신청·정정·포기] search_course_posts로 운영체제 게시판의 결석 처리 기준 공지를 찾지 않아 지각 환산 규칙을 놓쳤습니다. → 출석·F 기준 질문에서는 강의계획서와 함께 search_course_posts(keyword '결석'/'출석')로 과목 공지도 확인하도록 서버 안내에 명시합니다.
- lv02 [휴학·복학] 도구 결과는 '입영통지서 사본 첨부'만 말했는데, 이를 '하나만 있으면 된다'로 과잉 해석했습니다. → 자료에 명시된 서류(입영통지서 사본)만 전하고, 다른 서류가 필요한지는 교육지원팀에 확인하라고 덧붙여야 합니다.
- lv07 [휴학·복학] academic_calendar나 academic_deadlines를 부르지 않아, 학사일정에 있는 동계 계절수업 수강신청·수업 기간을 놓침. → 계절학기 질문에서 공지 검색 결과가 없으면 academic_calendar(11~1월)로 일정을 확인하도록 school_notices·school_guide 안내에 명시하기.
- lv06 [휴학·복학] search_course_posts·get_course_post로 운영체제 과목 공지 '결석 처리 기준 안내'를 찾지 않고, 강의계획서와 학칙으로 대신했습니다. → 과목별 출결 질문에서는 school_guide가 '교수 공지 확인'을 안내하면 search_course_posts(keyword='결석')를 먼저 호출하도록 서버 안내에 명시하세요.
- cf09 [학식] academic_calendar를 확인하지 않고 12/14 운영·휴무 여부를 단정했고, 학식 운영 시간도 근거 없이 추정했습니다. → 운영 여부는 academic_calendar로 확인한 뒤 말하고, 확인하지 못했으면 '운영 여부와 시간은 확인 못 함'이라고 쓰도록 합니다. 식단 미수집 note를 운영 판단 근거로 쓰지 않게 합니다.
- cp03 [셔틀·기숙사·도서관] academic_calendar를 호출하지 않아 기말고사 기간을 알려 주지 못했습니다. → '기말 기간'처럼 시기를 묻는 질문에서는 academic_calendar로 해당 날짜를 확인해 함께 제시하도록 해야 합니다.
- cp07 [셔틀·기숙사·도서관] 휴업·출입 통제 같은 campus_alerts를 주는 today_briefing을 호출하지 않았습니다(경미). → 운행 중단·휴업 같은 루머를 검증할 때는 today_briefing의 campus_alerts도 함께 확인하도록 안내를 보강하세요.

### other (2)
- sn02 [학교 공지 찾기] 올바른 공고를 찾아 링크·날짜·부서와 핵심 내용을 정확히 요약하고, 신입생 공지와도 구분한 좋은 답변입니다. 다만 신청 시작일을 '다음 주 월요일'이라고 잘못 말했습니다. → 상대 날짜('다음 주' 등)를 쓸 때 오늘 날짜 기준으로 정확히 계산하도록 하거나, 절대 날짜만 쓰게 합니다.
- cc09 [휴강·강의실 변경] 도구를 적절히 썼고 정확합니다. 다만 마지막 문장이 단정적이고, 학교 공지를 확인하라는 안내가 빠졌습니다. → '못 찾음'에서 '평소처럼 수업'으로 단정하지 말고, 학교 공지나 총학 공지를 계속 확인하라고 안내하도록 응답 지침을 보강합니다.

## Tool use

school_guide 69, school_notices 57, read_school_notice 32, get_course_post 24, search_course_posts 19, get_courses 19, get_grades 18, academic_deadlines 17, get_class_changes 13, simulate_graduation 11, get_scholarships 10, academic_calendar 10, my_notices 9, get_syllabus 9, get_exam_info 9, get_attendance 9, cafeteria_menu 9, get_assignment_detail 7, explore_multi_major 6, get_assignments 5, get_online_tests 4, get_deadlines 3, get_online_lectures 3, department_curriculum 3, get_graduation_progress 3, get_team_projects 2, get_course_overview 2, get_attachment_text 2, this_week 1, get_discussions 1, get_course_evaluation 1, today_briefing 1, get_quizzes 1, klas_status 1

