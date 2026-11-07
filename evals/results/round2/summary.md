# Eval summary: round 2

- cases graded: 150 (ok 150, truncated 0), errors: 0
- mean total: 0.898 ± 0.020 (95% CI)
- failing: 24
- answer cost: $9.41, judge cost: $7.03, ledger eval total: $33.70
- model: claude-opus-5-5, effort answer/judge: medium/medium
- provisional tools: {}

## Per category

| category | n | total | correct | sourced | actionable | honest | no_hallucination | scope | failing | top gap | Δ vs prev |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 마감·할 일 | 10 | 0.89 | 1.70 | 1.50 | 1.90 | 1.80 | 1.80 | 2.00 | 0 | model_misuse 4 | +0.00 |
| 휴강·강의실 변경 | 10 | 0.90 | 1.90 | 1.90 | 1.80 | 1.60 | 1.70 | 1.90 | 1 | other 1, model_misuse 1 | +0.01 |
| 시험 | 10 | 0.92 | 1.90 | 1.80 | 1.90 | 1.80 | 1.70 | 1.90 | 0 | model_misuse 2 | +0.04 |
| 출석 | 10 | 0.86 | 1.80 | 2.00 | 1.80 | 1.70 | 1.30 | 1.70 | 1 | model_misuse 3 | +0.14 |
| 성적·재수강 | 10 | 0.94 | 2.00 | 1.90 | 2.00 | 2.00 | 1.70 | 1.70 | 0 | model_misuse 1 | +0.08 |
| 장학 | 10 | 0.92 | 1.80 | 2.00 | 2.00 | 1.90 | 1.60 | 1.70 | 1 | model_misuse 2, missing_data 1 | +0.03 |
| 졸업요건 | 10 | 0.91 | 1.80 | 1.90 | 2.00 | 1.80 | 1.80 | 1.60 | 2 | missing_data 1, model_misuse 1 | +0.06 |
| 다전공 | 10 | 0.87 | 1.80 | 1.90 | 1.90 | 1.60 | 1.60 | 1.60 | 2 | model_misuse 3 | +0.01 |
| 수강신청·정정·포기 | 10 | 0.95 | 1.80 | 1.90 | 2.00 | 1.90 | 1.90 | 1.90 | 1 | model_misuse 2, missing_data 1 | +0.12 |
| 휴학·복학 | 10 | 0.83 | 1.70 | 1.90 | 2.00 | 1.30 | 1.60 | 1.50 | 4 | model_misuse 4, missing_data 1 | +0.21 |
| 학식 | 10 | 0.87 | 1.80 | 1.80 | 1.90 | 1.80 | 1.20 | 1.90 | 3 | missing_tool 1, model_misuse 1 | -0.01 |
| 셔틀·기숙사·도서관 | 10 | 0.97 | 1.90 | 2.00 | 2.00 | 2.00 | 1.80 | 2.00 | 5 | missing_data 3, missing_tool 2 | +0.11 |
| 학교 공지 찾기 | 10 | 0.90 | 1.90 | 2.00 | 1.90 | 1.80 | 1.80 | 1.40 | 0 | other 1, model_misuse 1 | +0.07 |
| 학과 공지 | 10 | 0.85 | 1.70 | 1.80 | 1.90 | 1.80 | 1.60 | 1.40 | 4 | model_misuse 3, missing_data 2 | +0.03 |
| 첨부·이미지 공지 읽기 | 10 | 0.90 | 1.90 | 1.70 | 1.90 | 1.90 | 1.80 | 1.60 | 0 | model_misuse 3 | -0.00 |

## Worst 20

### cf06 (학식) total 0.33, gap model_misuse
- Q: 수욜 머신러닝 끝나고 학식 먹을수있나 ㅋㅋ 메뉴 뭐임 강의실 어디였지
- tools: cafeteria_menu, get_courses, school_guide
- judge: 학식 시간과 메뉴 미수집은 정직하게 안내했지만, 강의실 변경 공지를 확인하지 않아 옛 강의실(한울관 B101)을 안내함.
- 0점 correct: 강의실을 한울관 B101로 안내했는데, 11/11부터 새빛관 B105로 바뀐다는 공지를 놓쳤음. 핵심 사실이 틀림.
- 0점 honest: must_not 위반: 강의실을 한울관 B101로 단정함. 저녁 운영 여부와 메뉴 미수집은 솔직하게 밝혔음.
- 0점 no_hallucination: must_not인 '강의실을 한울관 B101로 안내'에 해당. 운영시간은 도구 근거가 있어 지어낸 것은 아님.
- misuse: get_class_changes를 부르지 않아 머신러닝 강의실 변경 공지를 확인하지 않았음. 시간표의 강의실만 보고 단정함.
- fix: 특정 날짜의 강의실·수업을 물으면 get_class_changes나 search_course_posts로 변경 공지를 확인하도록 get_courses 설명에 '강의실은 변경 공지를 함께 확인' 안내를 추가.

### mm08 (다전공) total 0.42, gap model_misuse
- Q: 세부전공 바꾸고 싶은데 이것도 다전공 신청하는거임?
- tools: school_guide, school_notices
- judge: 제도 구분과 규정 요약은 맞지만 해당 공고를 찾지 못했고, 신청 시기를 추측해 must_not을 위반했습니다.
- 0점 no_hallucination: '보통 겨울방학 즈음일 것'이라며 신청 시기를 추측했습니다. 추측이라고 표시했어도 must_not 위반입니다.
- misuse: school_notices를 '전공변경' 한 번만 검색했습니다. 결과가 비었는데도 '세부전공'·'세부전공 변경'으로 다시 찾지 않았고, read_school_notice로 공고를 읽지도 않았습니다.
- fix: 공지 검색 결과가 비면 동의어('세부전공', '전공 변경', '전공배정')로 재검색하도록 school_notices 설명에 안내를 추가하세요. 날짜를 추측하지 말라는 지침도 보강하세요.

### cc10 (휴강·강의실 변경) total 0.50, gap model_misuse
- Q: 수요일 머신러닝 5교시 맞지? 몇시부터임
- tools: get_courses
- judge: 교시는 맞혔으나 강의실 변경을 놓치고 시각을 지어냄.
- 0점 no_hallucination: must_not인 교시 시각 추측을 어김. '75분, 15:00~17:45'를 지어냄.
- missing: 교시-시각 매핑을 주는 도구·데이터가 없음
- misuse: get_class_changes를 부르지 않아 강의실 변경 공지를 놓쳤고, 근거 없이 시각을 추측함
- fix: 시간·강의실 질문에서는 get_class_changes도 함께 부르도록 하고, 확인 못 한 시각은 추측하지 말라고 지시. 교시-시각표 데이터를 school_guide에 추가.

### dn05 (학과 공지) total 0.50, gap model_misuse
- Q: 취업박람회 며칠임? 수업 빼야하나
- tools: get_courses, read_school_notice, school_notices
- judge: 날짜·시간은 맞지만 운영체제 휴강을 확인하지 않아 화요일 충돌을 잘못 안내했습니다. 강의실 정보와 학부 공지 링크가 빠졌고, 포스터 세부 내용이 장황합니다.
- misuse: get_class_changes를 호출하지 않아 운영체제 11/10 휴강을 놓쳤습니다. 읽은 학부 공지 링크 대신 메인 공지를 인용했습니다.
- fix: '수업 빼야 하나'처럼 행사 날짜와 수업을 비교하는 질문에는 get_class_changes로 해당 날짜의 휴강·보강을 확인하도록 서버 안내에 명시하세요. 출처는 실제로 사실을 가져온 공지(학생 학과 게시판)를 인용하게 하세요.

### gd09 (졸업요건) total 0.50, gap model_misuse
- Q: 졸업종합시험 지금 하는거임? 나도 봐야됨?
- tools: my_notices, school_guide, school_notices, simulate_graduation
- judge: 학사일정을 조회하지 않아 졸업종합시험 기간을 놓쳤고, 3학년은 대상이 아니라고 단정했습니다. 학과사무실 확인 안내와 근거 제시는 양호합니다.
- 0점 correct: academic_calendar를 호출하지 않아 졸업종합시험 기간(11/2~11/13)을 놓쳤습니다. '지금 하는 거냐'는 질문에도 다른 학부 일정일 수 있다는 식으로 잘못 답했습니다.
- 0점 honest: 게시판에서 못 찾은 것을 진행 여부 불명이나 타 학부 일정으로 몰아갔습니다. 또 '지금은 안 봐도 돼요', '이번 학기에는 대상이 아니에요'라고 대상 여부를 단정했습니다.
- misuse: 일정 질문인데 academic_calendar(또는 academic_deadlines)를 호출하지 않고 공지 검색에만 의존했습니다.
- fix: '지금 하는 거냐'처럼 학사 일정을 묻는 질문에는 academic_calendar를 먼저 호출하도록 서버 안내나 school_guide 결과에 학사일정 확인 힌트를 추가하세요.

### at03 (출석) total 0.58, gap model_misuse
- Q: 예비군 갔다왔는데 공결 어케 신청함? 다 똑같이 하면 되나
- tools: read_school_notice, school_guide, school_notices
- judge: 타 학과 공지를 근거로 예비군 공결 일괄처리를 안내했지만, 학생 본인 과목(현대사회와윤리)의 공결 공지를 찾지 않아 must_include를 모두 놓쳤습니다.
- misuse: 학생 수강과목 게시판을 search_course_posts('공결')로 검색하지 않았습니다. 대신 다른 학과 공지에 의존했습니다.
- fix: 출석·공결 질문이면 먼저 수강 과목별로 search_course_posts(keyword='공결'/'출석')를 실행해 과목 공지를 확인하도록 해야 합니다. 그 결과를 일반화하지 말고 과목별로 다를 수 있다고 안내하도록 지침을 보강합니다.

### lv02 (휴학·복학) total 0.58, gap model_misuse
- Q: 군휴학 하려면 뭐 내야돼? 입영통지서만 있으면 됨?
- tools: school_guide
- judge: 근거·절차 안내는 좋으나, 첫 문장에서 입영통지서만으로 충분하다고 단정해 must_not을 위반함.
- 0점 honest: 도구는 '입영통지서 사본 첨부'만 말할 뿐 그것만으로 충분하다고 하지 않음. 그런데도 첫 줄에서 '네, 하나만 있으면 돼요'라고 단정해 must_not을 어김.
- misuse: school_guide 결과의 '입영통지서 사본 첨부'를 '그것 하나만 있으면 된다'로 과장해 단정함
- fix: 자료에 명시된 서류는 입영통지서 사본뿐이라고만 전달하고, 추가 서류가 필요한지는 확인하지 못했으니 교육지원팀(02-940-5511)에 확인하라고 안내해야 함.

### lv04 (휴학·복학) total 0.58, gap model_misuse
- Q: 나 휴학하면 이번학기 받은 국장 토해내야 함?
- tools: academic_calendar, get_scholarships, school_guide
- judge: 금액·규정·연락처는 정확하고 근거도 충실합니다. 하지만 장학금이 등록금 감면 방식이라고 추측해 must_not을 어겼고, 반환액 추정도 근거가 약합니다.
- 0점 honest: '돌려받을 등록금에서 장학금 몫을 빼는 방식일 가능성이 커요'는 도구가 추측하지 말라고 한 감면/별도 지급 여부를 추측한 것으로 must_not 위반입니다. 나머지 한계 고지는 좋았습니다.
- misuse: get_scholarships note와 도구 설명이 감면/별도 지급을 추측하지 말라고 했는데 반환 방식을 추측했습니다. 적용 방식이 불명확하다는 안내에도 구체 반환액을 계산했습니다.
- fix: get_scholarships note를 지키도록, 장학금 지급 형태나 반환 방식을 추측하는 문장을 금지하는 지침을 강화합니다. 규정 적용이 불명확할 때는 구체 금액을 계산하지 않도록 유도합니다.

### dn02 (학과 공지) total 0.67, gap model_misuse
- Q: 스탬프투어 커피쿠폰 그거 뭐임 ㅋㅋ
- tools: my_notices, read_school_notice, school_notices
- judge: 내용은 원문과 정확하고 실용적입니다. 하지만 학생 학부(정보융합학부)의 3522 대신 단과대 3524 글을 인용했고, 비대면 수업 시간에 다녀오라는 부적절한 권유가 덧붙었습니다.
- misuse: my_notices에 같은 제목 글이 두 개(인공지능융합대학 3524, 정보융합학부 3522) 있었는데, 학생 학부 글인 3522가 아니라 3524를 읽고 인용함
- fix: 같은 제목 공지가 여러 개면 department_scope의 학생 학과와 일치하는 글을 우선 고르도록 도구 설명이나 결과에 안내를 추가

### mm09 (다전공) total 0.67, gap model_misuse
- Q: 평점 3.5면 복전 붙음?
- tools: explore_multi_major, read_school_notice, school_guide
- judge: 신청 자격 안내와 출처는 좋습니다. 그러나 평점 조회를 빠뜨렸고, 평점 기준이 없다고 단정해 함정에 빠졌습니다.
- 0점 honest: '평점 기준이 없습니다', '붙고 떨어지는 방식이 아니라 자격만 되면 신청'이라고 단정해 '못 찾음'을 '없음'으로 바꿨습니다. 끝에 확인하지 못했다는 단서를 달았지만 앞의 단정과 모순됩니다.
- misuse: get_grades를 호출하지 않아 학생의 실제 평점(3.52)을 확인하지 않았습니다. 선발 기준이 자료에 없는 것을 '평점 기준이 없음'으로 단정했습니다.
- fix: get_grades로 평점을 확인해 전달하세요. 선발 평점 기준은 '자료에서 확인 못함'으로만 말하고, 학과사무실·교육지원팀 확인을 안내하세요.

### ac01 (첨부·이미지 공지 읽기) total 0.75, gap model_misuse
- Q: 디비 과제2 제출형식 첨부 뭐라고 써있음
- tools: get_assignment_detail, get_attachment_text
- judge: 과제 첨부(ERD 가이드)와 마감은 정확히 안내했습니다. 그러나 학생이 물은 게시판 '과제 2 제출 형식 안내' 글의 docx 첨부를 찾지 못해 핵심을 놓쳤습니다.
- misuse: '제출형식 첨부'를 묻자 과제 첨부만 열었습니다. search_course_posts로 '제출 형식' 게시글을 찾고 get_course_post·get_attachment_text(source=post)로 읽지 않았습니다.
- fix: 질문에 '첨부'·'안내' 표현이 있고 과제 첨부가 질문 주제(제출 형식)와 맞지 않으면, search_course_posts로 과목 게시판에서 관련 글을 찾아 첨부까지 읽도록 유도해야 합니다.

### ac08 (첨부·이미지 공지 읽기) total 0.75, gap none
- Q: 취업박람회 참가기업 표 이미지던데 IT회사 있어?
- tools: read_school_notice, school_notices
- judge: 경력개발팀 공지의 포스터 이미지를 읽어 IT 관련 기업(오라클·롯데이노베이트 등)을 답했다. 출처 링크가 없고 IT와 무관한 정보가 다소 많다.
- fix: 답변에 공지 URL을 붙이고, IT 관련 부스 위주로 줄이면 좋다.

### at01 (출석) total 0.75, gap model_misuse
- Q: 확통 결석 3번에 지각 2번인데 이거 f각임??ㅠㅠ
- tools: get_attendance, get_course_post, get_syllabus, school_guide, search_course_posts
- judge: 학교 규정을 근거와 함께 정확히 인용했고 다른 과목 규칙을 옮겨 쓰지도 않았습니다. 다만 과목별 기준을 못 찾았다는 점을 밝히지 않았고, 추정한 회차로 '안전' 범위를 단정한 점이 아쉽습니다.
- misuse: 과목 게시판을 '출석'으로만 검색하고 '결석'·'지각'으로는 찾지 않았습니다. 과목별 기준을 못 찾은 사실도 밝히지 않았습니다. 총 수업 횟수는 강의계획서·학사일정으로 확인하지 않고 추정했습니다.
- fix: 과목 게시판을 '결석'·'지각' 키워드로도 검색하고, 과목별 기준을 못 찾았으면 그렇게 밝히세요. 총 수업 횟수를 추정해 '몇 번까지 안전'이라고 단정하지 말고 교수 확인을 앞세우세요.

### cc09 (휴강·강의실 변경) total 0.75, gap other
- Q: 학교 전체 휴강하는 날 이번달에 있음? 축제같은거
- tools: academic_calendar, school_notices
- judge: 도구 사용과 사실 전달은 적절함. 다만 '평소처럼 수업' 단정과 축제 시기 추측이 있고, 학교 공지 확인 안내가 부족함.
- fix: '찾지 못함'과 '없음'을 구분해 표현하고, 축제 시기 같은 일반론 추측은 빼기. 학교 공지사항 확인 경로를 안내하기.

### dl04 (마감·할 일) total 0.75, gap model_misuse
- Q: 디비 과제2 pdf로 내는거 맞나? 형식 뭐였더라
- tools: get_assignment_detail
- judge: 과제 상세 기준으로는 정확하지만, 게시판의 형식 안내 공지와 첨부 docx를 확인하지 않아 핵심 must_include 두 개를 놓쳤습니다.
- misuse: '형식'을 물었는데 search_course_posts·get_course_post·get_attachment_text로 게시판의 제출 형식 안내 공지와 첨부를 찾아 읽지 않고, 과제 상세 하나만 보고 끝냈습니다.
- fix: 형식·제출 방법 질문에는 과제 상세 뒤에 search_course_posts(keyword='과제2' 또는 '형식')로 관련 공지를 찾고, 첨부가 있으면 get_attachment_text로 읽도록 유도해야 합니다.

### dn01 (학과 공지) total 0.75, gap model_misuse
- Q: 우리 과 공지 새로 뭐 올라옴?
- tools: my_notices
- judge: 필수 항목은 모두 충족했고 한계도 정직하게 밝혔습니다. 다만 건수 요약에 오류가 있고 부가 정보가 다소 많습니다.
- misuse: 도구 결과의 학부/단과대 공지 건수를 잘못 셈(학부 4건을 3건으로, 총 5건을 4건으로 표기)
- fix: 요약 건수를 표의 항목 수와 일치시키고, 학과 질문에는 과목 공지 부연을 줄이세요.

### ex07 (시험) total 0.75, gap model_misuse
- Q: ai리터러시 시험은 온라인으로 봄?
- tools: get_exam_info, get_online_tests
- judge: KLAS 온라인시험 등록과 강의계획서에 근거해 온라인 시험이라고 답했고, 근거가 두 곳에서 일치해 단정 금지 위반으로 보지는 않았습니다. 다만 게시판 공지를 검색하지 않았고, 학생에게 과목 공지를 직접 확인하라는 안내가 빠졌습니다.
- misuse: get_exam_info의 hint가 search_course_posts로 '기말' 검색을 권했는데 호출하지 않고 끝냈습니다.
- fix: exam_posts가 비면 search_course_posts로 '기말'·'시험'을 검색하게 하세요. 못 찾으면 KLAS 과목 공지를 직접 확인하라고 안내하고, 방식이 바뀔 수 있다는 단서를 붙이세요.

### lv01 (휴학·복학) total 0.75, gap missing_data
- Q: 휴학 신청 언제까지임?? 이번주 안에 해야되나
- tools: academic_deadlines, school_guide, school_notices
- judge: 필요한 도구를 모두 써서 휴학 일정을 찾지 못했다고 밝히고 교육지원팀을 안내한 좋은 답변입니다. 다만 첫 문장의 단정, 공지 검색 결과를 '없음'으로 표현한 점, '12월 말~1월' 시기 추정이 감점 요인입니다.
- missing: 학사일정 스냅숏과 공지 DB에 다음 학기 휴학 신청 일정이 없음
- fix: 공지 검색이 빈 결과일 때 '못 찾음'과 '없음'을 구분해 말하도록 도구 결과에 안내 문구를 넣고, 근거 없는 시기 추정을 피하게 하세요.

### lv09 (휴학·복학) total 0.75, gap none
- Q: 휴학이랑 자퇴 차이 뭐임 자퇴 절차 공지 있었던거 같은데
- tools: read_school_notice, school_guide, school_notices
- judge: FAQ 공지를 찾아 원문대로 절차를 설명했고 차이도 도구 근거로 정리했습니다. 일부 추론성 세부와 장황함이 감점 요인입니다.
- fix: 휴학·자퇴 비교표의 각 항목에 출처(학사정보 페이지 등)를 붙이세요. '언제든 접수 가능'처럼 근거 없는 추론은 빼세요.

### sn07 (학교 공지 찾기) total 0.75, gap other
- Q: 최근 학교 공지 중에 나한테 해당되는거 뭐있음
- tools: get_course_post, my_notices
- judge: 링크와 정리는 좋지만 개인화 선별 근거가 약하고, 장학 자격을 사소하게 추측했다.
- fix: 장학 공지는 read_school_notice로 자격(학년·소득·지역)을 확인한 뒤 해당 여부를 이유와 함께 선별하도록 유도한다.

## Gap tallies (primary_gap)

- none: 101
- model_misuse: 33
- missing_data: 10
- missing_tool: 4
- other: 2

- capability_missing: 20, model_misused_tools: 31

## Gap details

### missing_tool (4)
- lv08 [휴학·복학] 휴학 신청 내역·처리 상태 조회 도구 없음 → KLAS 휴복학신청 내역·처리 상태를 읽는 도구 추가 고려.
- cf08 [학식] 학교 주변 식당·맛집 정보를 주는 도구가 없음 → 범위 밖 질문이므로 지금처럼 한계를 밝히고 외부 검색을 안내하면 됩니다. 확인되지 않은 지역 세부(도보 시간 등)는 '대략'이라고 표시하거나 빼는 것이 좋습니다.
- cp02 [셔틀·기숙사·도서관] 도서관 실시간 좌석 현황 조회 도구 없음 → 도서관 좌석 현황 조회 도구를 추가하거나, school_guide에 좌석 확인 시스템(앱·웹 주소) 안내를 넣기.
- cp04 [셔틀·기숙사·도서관] 행복기숙사(생활관) 홈페이지 게시판을 조회하는 도구가 없음 → 행복기숙사 홈페이지 공지 게시판을 school_notices 범위에 넣거나 별도 도구로 제공

### missing_data (10)
- dn08 [학과 공지] 학과사무실 위치·전화번호를 주는 도구나 데이터(school_guide에 학과 연락처 없음) → school_guide에 단과대·학과사무실 위치·연락처(학교 홈페이지 학과 안내 기반)를 추가하세요.
- dn09 [학과 공지] 정보융합학부 자체 게시판 공지는 수집되지 않아 단과대 게시판만 조회 가능 → 학과 자체 게시판도 수집하거나, 답변 첫 문장을 '확인한 범위에서는 못 찾았다'로 표현하도록 안내 강화
- sc04 [장학] 정보융합학부·인공지능융합대학 성적장학 자체 기준 공지와 학과 내규 데이터가 없습니다. → 학과별 성적장학 내규·기준 공지를 school_guide나 공지 DB에 추가하고, 정보융합학부 게시판을 공지 분류에 포함하세요.
- rg05 [수강신청·정정·포기] 학사일정 데이터에 2027학년도 1학기 수강신청 일정이 아직 없음 → 첫 문장을 '조회한 학사일정·공지에서는 확인되지 않았어요'로 바꾸고, 학생 소속 단과대 기준 신청일을 짚어 주면 좋습니다.
- lv01 [휴학·복학] 학사일정 스냅숏과 공지 DB에 다음 학기 휴학 신청 일정이 없음 → 공지 검색이 빈 결과일 때 '못 찾음'과 '없음'을 구분해 말하도록 도구 결과에 안내 문구를 넣고, 근거 없는 시기 추정을 피하게 하세요.
- cf10 [학식] 함지마루 외 교내 식당 메뉴 데이터·도구 없음 → 교내 다른 식당(있다면)의 메뉴를 cafeteria_menu에 추가하거나 school_guide에 식당 목록 정보를 넣기.
- cp05 [셔틀·기숙사·도서관] 기숙사비 중도 퇴사 환불 규정 데이터 → school_guide에 행복기숙사 퇴사·환불 규정(입사 안내문)을 추가
- cp06 [셔틀·기숙사·도서관] get_courses가 교시만 주고 교시별 시작 시각을 주지 않음 → get_courses 결과에 교시별 시작·종료 시각을 함께 넣기.
- cp10 [셔틀·기숙사·도서관] 교내 프린터·전산실 위치와 운영시간 데이터가 school_guide에 없음 → school_guide에 도서관·학생회관 등 교내 프린터·전산실 위치와 운영시간 안내를 추가
- gd07 [졸업요건] 정보융합학부의 졸업논문·대체요건 세부 기준 데이터가 없음 → school_guide 또는 simulate_graduation에 학과별 졸업논문·대체요건 표(학과 사무실 공지 기반)를 추가합니다.

### model_misuse (33)
- ac01 [첨부·이미지 공지 읽기] '제출형식 첨부'를 묻자 과제 첨부만 열었습니다. search_course_posts로 '제출 형식' 게시글을 찾고 get_course_post·get_attachment_text(source=post)로 읽지 않았습니다. → 질문에 '첨부'·'안내' 표현이 있고 과제 첨부가 질문 주제(제출 형식)와 맞지 않으면, search_course_posts로 과목 게시판에서 관련 글을 찾아 첨부까지 읽도록 유도해야 합니다.
- ac06 [첨부·이미지 공지 읽기] 학생 학과(정보융합학부) 게시판 글 aicon-3522 대신 같은 제목의 aicon-3524를 읽었습니다. 내용은 동일한 것으로 보여 결과에는 영향이 없습니다. → 같은 제목 공지가 여러 학과에 올라오면 학생 학과 게시판 글을 우선 읽고, 답변에 공지 제목과 URL을 함께 제시하도록 안내합니다.
- ac07 [첨부·이미지 공지 읽기] 첨부·서류가 없다는 점을 정확히 전달하고 자격도 데이터로 확인했으나, 공지 URL을 빠뜨렸고 답변이 다소 길다. → 답변에 read_school_notice의 source_url을 출처 링크로 함께 표기하도록 유도.
- dl04 [마감·할 일] '형식'을 물었는데 search_course_posts·get_course_post·get_attachment_text로 게시판의 제출 형식 안내 공지와 첨부를 찾아 읽지 않고, 과제 상세 하나만 보고 끝냈습니다. → 형식·제출 방법 질문에는 과제 상세 뒤에 search_course_posts(keyword='과제2' 또는 '형식')로 관련 공지를 찾고, 첨부가 있으면 get_attachment_text로 읽도록 유도해야 합니다.
- dl08 [마감·할 일] 핵심 사실(0/1, 11/9 23:59 마감)은 정확함. 토론실 직접 확인 안내가 빠져 must_include 하나를 놓침. → get_discussions 설명에 있는 '참여 여부는 토론실에서 확인' 안내를 답변에 반영하도록 하고, 토론 참여 질문에는 KLAS 토론실 확인 문구를 넣게 함.
- dl07 [마감·할 일] 도구 결과에 있던 ML 실습 4(11/10 23:59 마감)를 빼고, '전에'의 경계 해석에 대해 언급하지 않았습니다. → '~전에'처럼 경계가 애매한 질문에서는 경계일 당일 마감 항목(ML 실습 4, 화 23:59)을 따로 짚어 주도록 해야 합니다.
- dl09 [마감·할 일] get_assignments를 pending_only=true로만 불러 제출 완료 과제를 확인하지 않았습니다. → '다 냈는지' 묻는 질문에는 get_assignments를 pending_only 없이 불러 제출 완료와 미제출을 함께 보여 주도록 유도해야 합니다.
- ex07 [시험] get_exam_info의 hint가 search_course_posts로 '기말' 검색을 권했는데 호출하지 않고 끝냈습니다. → exam_posts가 비면 search_course_posts로 '기말'·'시험'을 검색하게 하세요. 못 찾으면 KLAS 과목 공지를 직접 확인하라고 안내하고, 방식이 바뀔 수 있다는 단서를 붙이세요.
- ex10 [시험] academic_calendar를 호출하지 않아 이번 학기 졸업종합시험 기간(11/2~11/13)을 놓쳤습니다. → '시험 일정'이나 학사 행사명이 나오는 질문에서는 academic_calendar(또는 academic_deadlines)를 함께 조회하도록 서버 안내에 명시합니다.
- at06 [출석] 확률과통계 강의계획서만 열었습니다. 운영체제(지각 환산 기준)와 현대사회와윤리(출석 비율 20%) 강의계획서·공지를 확인하지 않아 과목 간 위험도를 횟수로만 비교했습니다. → 출석 위험도를 비교할 때는 결석·지각이 있는 과목마다 get_syllabus와 search_course_posts('출석')로 환산 기준·비율·F 기준을 확인하도록 유도합니다. get_attendance 결과에 '과목별 기준은 계획서 확인' 안내를 넣는 것도 방법입니다.
- sn09 [학교 공지 찾기] 제목 검색 결과가 비어 있는 것을 '공지 없음'으로 단정해 표현함 → 검색 결과가 0건이면 '검색으로는 못 찾았다'고 표현하고, 학교 홈페이지 학사공지 게시판을 직접 확인하라고 안내하도록 유도한다.
- dn01 [학과 공지] 도구 결과의 학부/단과대 공지 건수를 잘못 셈(학부 4건을 3건으로, 총 5건을 4건으로 표기) → 요약 건수를 표의 항목 수와 일치시키고, 학과 질문에는 과목 공지 부연을 줄이세요.
- dn02 [학과 공지] my_notices에 같은 제목 글이 두 개(인공지능융합대학 3524, 정보융합학부 3522) 있었는데, 학생 학부 글인 3522가 아니라 3524를 읽고 인용함 → 같은 제목 공지가 여러 개면 department_scope의 학생 학과와 일치하는 글을 우선 고르도록 도구 설명이나 결과에 안내를 추가
- dn05 [학과 공지] get_class_changes를 호출하지 않아 운영체제 11/10 휴강을 놓쳤습니다. 읽은 학부 공지 링크 대신 메인 공지를 인용했습니다. → '수업 빼야 하나'처럼 행사 날짜와 수업을 비교하는 질문에는 get_class_changes로 해당 날짜의 휴강·보강을 확인하도록 서버 안내에 명시하세요. 출처는 실제로 사실을 가져온 공지(학생 학과 게시판)를 인용하게 하세요.
- sc01 [장학] academic_deadlines의 klas.scholarship_application open:false 결과를 답변에 반영하지 않았고, 화도/동해 KLAS 신청 경로와 충돌하는 점도 알리지 않았습니다. → KLAS가 알려 준 장학 신청 창 상태(닫힘)를 명시하고, 공지의 신청 기간과 다르면 그 차이를 학생에게 알려 확인하도록 안내하세요.
- sc08 [장학] '또 하고싶다'는 질문인데 get_scholarships로 과거 근로장학 수혜 이력을 확인하지 않았습니다. → '또'·'다시' 같은 표현이 있으면 개인 이력 도구(get_scholarships)를 먼저 호출하도록 유도합니다. 공지 미발견은 '최근 공지에서 못 찾음'으로 표현하게 합니다.
- cc10 [휴강·강의실 변경] 교시-시각 매핑을 주는 도구·데이터가 없음 → 시간·강의실 질문에서는 get_class_changes도 함께 부르도록 하고, 확인 못 한 시각은 추측하지 말라고 지시. 교시-시각표 데이터를 school_guide에 추가.
- at01 [출석] 과목 게시판을 '출석'으로만 검색하고 '결석'·'지각'으로는 찾지 않았습니다. 과목별 기준을 못 찾은 사실도 밝히지 않았습니다. 총 수업 횟수는 강의계획서·학사일정으로 확인하지 않고 추정했습니다. → 과목 게시판을 '결석'·'지각' 키워드로도 검색하고, 과목별 기준을 못 찾았으면 그렇게 밝히세요. 총 수업 횟수를 추정해 '몇 번까지 안전'이라고 단정하지 말고 교수 확인을 앞세우세요.
- at03 [출석] 학생 수강과목 게시판을 search_course_posts('공결')로 검색하지 않았습니다. 대신 다른 학과 공지에 의존했습니다. → 출석·공결 질문이면 먼저 수강 과목별로 search_course_posts(keyword='공결'/'출석')를 실행해 과목 공지를 확인하도록 해야 합니다. 그 결과를 일반화하지 말고 과목별로 다를 수 있다고 안내하도록 지침을 보강합니다.
- gr06 [성적·재수강] D+ 제외 평점을 3.75가 아닌 3.5로 잘못 계산함 → 모델이 직접 계산한 값을 제시할 때는 산식을 확인하거나 생략하도록 하고, 필요하면 도구에서 과목 제외 평점 계산을 제공하세요.
- rg03 [수강신청·정정·포기] academic_deadlines 결과의 drop_earned_credits open:false를 답변에 반영하지 않음 → 취득학점포기 제도를 설명할 때 KLAS에서 받은 현재 신청 가능 여부(open:false)를 함께 알리도록 유도하세요.
- lv02 [휴학·복학] school_guide 결과의 '입영통지서 사본 첨부'를 '그것 하나만 있으면 된다'로 과장해 단정함 → 자료에 명시된 서류는 입영통지서 사본뿐이라고만 전달하고, 추가 서류가 필요한지는 확인하지 못했으니 교육지원팀(02-940-5511)에 확인하라고 안내해야 함.
- rg09 [수강신청·정정·포기] school_guide가 과목별 결석 기준은 강의 공지를 확인하라고 했는데도 search_course_posts로 '결석' 공지를 찾지 않았습니다. → 출결·F 기준 질문에서는 search_course_posts(keyword='결석')로 과목 공지를 함께 확인하도록 도구 설명이나 지침을 보강합니다.
- lv04 [휴학·복학] get_scholarships note와 도구 설명이 감면/별도 지급을 추측하지 말라고 했는데 반환 방식을 추측했습니다. 적용 방식이 불명확하다는 안내에도 구체 반환액을 계산했습니다. → get_scholarships note를 지키도록, 장학금 지급 형태나 반환 방식을 추측하는 문장을 금지하는 지침을 강화합니다. 규정 적용이 불명확할 때는 구체 금액을 계산하지 않도록 유도합니다.
- lv07 [휴학·복학] school_notices로 동계 계절수업 공지를 찾지 않고 제안만 했습니다. last_verified를 '지금 기준 재확인'으로 과장했습니다. → school_notices로 동계 계절수업 공지를 바로 검색해야 합니다. 휴학생 자격은 규정상 조건부 가능이라고 전하되, 해당 학기 공지·교육지원팀에서 최종 확인하라고 명시해야 합니다.
- lv06 [휴학·복학] search_course_posts·get_course_post로 운영체제 과목 공지(결석 처리 기준)를 찾지 않고 학교 일반 규정만 인용했습니다. → 출석 관련 질문에서는 해당 과목 게시판을 '결석'·'출석'으로 검색해 교수 공지를 확인하도록 유도해야 합니다. 예: school_guide 출석 답변에 search_course_posts 사용 힌트를 추가.
- cf06 [학식] get_class_changes를 부르지 않아 머신러닝 강의실 변경 공지를 확인하지 않았음. 시간표의 강의실만 보고 단정함. → 특정 날짜의 강의실·수업을 물으면 get_class_changes나 search_course_posts로 변경 공지를 확인하도록 get_courses 설명에 '강의실은 변경 공지를 함께 확인' 안내를 추가.
- cp03 [셔틀·기숙사·도서관] 기말 기간 날짜를 확인하려면 academic_calendar(또는 academic_deadlines)를 불렀어야 하는데 호출하지 않았습니다. → '기말 기간' 같은 시기 표현이 나오면 academic_calendar로 해당 기간을 조회해 함께 제시하도록 유도해야 합니다.
- cp07 [셔틀·기숙사·도서관] 운행 중단·출입 통제 같은 campus_alerts를 주는 today_briefing을 부르지 않음(경미함). → 루머성 운영 변동 질문에서는 today_briefing의 campus_alerts도 확인하도록 도구 설명에 명시하세요.
- gd09 [졸업요건] 일정 질문인데 academic_calendar(또는 academic_deadlines)를 호출하지 않고 공지 검색에만 의존했습니다. → '지금 하는 거냐'처럼 학사 일정을 묻는 질문에는 academic_calendar를 먼저 호출하도록 서버 안내나 school_guide 결과에 학사일정 확인 힌트를 추가하세요.
- mm06 [다전공] 기대 도구 explore_multi_major를 부르지 않았다. 과목별 인정 계산이 가능한 것처럼 제안했다. → explore_multi_major로 이 학생 기준 상호인정 범위를 함께 확인하고, 과목별 인정 여부는 도구가 판정하지 않는다고 명시한다. 과목별 계산을 해 주겠다는 제안은 빼야 한다.
- mm08 [다전공] school_notices를 '전공변경' 한 번만 검색했습니다. 결과가 비었는데도 '세부전공'·'세부전공 변경'으로 다시 찾지 않았고, read_school_notice로 공고를 읽지도 않았습니다. → 공지 검색 결과가 비면 동의어('세부전공', '전공 변경', '전공배정')로 재검색하도록 school_notices 설명에 안내를 추가하세요. 날짜를 추측하지 말라는 지침도 보강하세요.
- mm09 [다전공] get_grades를 호출하지 않아 학생의 실제 평점(3.52)을 확인하지 않았습니다. 선발 기준이 자료에 없는 것을 '평점 기준이 없음'으로 단정했습니다. → get_grades로 평점을 확인해 전달하세요. 선발 평점 기준은 '자료에서 확인 못함'으로만 말하고, 학과사무실·교육지원팀 확인을 안내하세요.

### other (2)
- cc09 [휴강·강의실 변경] 도구 사용과 사실 전달은 적절함. 다만 '평소처럼 수업' 단정과 축제 시기 추측이 있고, 학교 공지 확인 안내가 부족함. → '찾지 못함'과 '없음'을 구분해 표현하고, 축제 시기 같은 일반론 추측은 빼기. 학교 공지사항 확인 경로를 안내하기.
- sn07 [학교 공지 찾기] 링크와 정리는 좋지만 개인화 선별 근거가 약하고, 장학 자격을 사소하게 추측했다. → 장학 공지는 read_school_notice로 자격(학년·소득·지역)을 확인한 뒤 해당 여부를 이유와 함께 선별하도록 유도한다.

## Tool use

school_guide 65, school_notices 56, read_school_notice 29, search_course_posts 19, get_course_post 19, academic_deadlines 18, get_courses 16, get_grades 15, simulate_graduation 12, get_exam_info 10, academic_calendar 9, get_syllabus 9, get_attendance 9, my_notices 9, get_scholarships 8, cafeteria_menu 8, get_assignment_detail 7, get_class_changes 6, explore_multi_major 5, get_assignments 4, get_deadlines 3, get_online_lectures 3, get_online_tests 3, get_graduation_progress 3, get_attachment_text 2, get_team_projects 2, get_course_overview 2, department_curriculum 2, get_course_notices 1, this_week 1, get_discussions 1, get_course_evaluation 1, today_briefing 1, get_quizzes 1, klas_status 1

