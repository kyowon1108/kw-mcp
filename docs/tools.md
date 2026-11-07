# 도구

[README](../README.md)로 돌아가기

확장이 실제로 내놓는 도구 목록(43개)은 [`manifest.json`](../manifest.json)의 `tools`입니다. 아래 표에 아직 없는 도구: `simulate_graduation`, `explore_multi_major`, `get_academic_status`, `get_scholarships`, `school_guide`, `department_curriculum`, `read_school_notice`, `check_update`, `download_update`.

| 도구 | 내용 |
|---|---|
| `list_semesters` | 수강 이력이 있는 학기와 학기별 과목명 |
| `get_courses` | 과목명, 담당교수, 강의 시간·강의실 |
| `get_assignments` | 과제: 마감, 지각 마감, 제출 여부, 점수 (`pending_only`) |
| `get_online_lectures` | 온라인 강의: 주차, 수강 기간, 진도율 (`incomplete_only`) |
| `get_team_projects` | 팀 프로젝트: 제목, 기간, 제출 여부, 점수, 팀 번호 (팀원 정보는 내보내지 않음) |
| `get_course_notices` | 과목 게시판 최근 글 (공지·강의 자료실 등) |
| `get_quizzes` | 퀴즈: 유형, 시작·마감, 제출 여부, 제한 시간, 문항 수 |
| `get_deadlines` | N일 안에 마감되는 안 한 일: 과제·퀴즈·온라인시험(재응시 포함)·팀플·설문, 미완료 온라인 강의, 끝나 가는 토론. 목록 하나를 못 읽어도 나머지는 주고 `incomplete`로 알림 |
| `get_online_tests` | 온라인시험: 응시 기간, 응시 여부, 재응시 기간 |
| `get_surveys` | 과목 설문: 기간, 참여 여부 |
| `get_discussions` | 과목 토론: 기간, 글 수(참여 여부는 KLAS 목록에 없음) |
| `get_course_overview` | 과목별 한눈에 보기(KLAS 과목 홈과 같은 숫자): 온라인강의 완료/전체, 과제·퀴즈·시험·팀플·설문 제출/전체, 토론 참여/전체, 새 글, 출석 횟수 |
| `get_course_evaluation` | 수업평가: 평가 기간인지(중간/기말), 아직 평가하지 않은 과목 |
| `get_grades` | 학기별 과목 성적·학기 평점(계산값), KLAS 평량평균(학적부·성적증명서 기준), 전공·교양·기타 신청/취득/삭제 학점, 학과·학년·학적 상태, 학기별 석차·학사경고, 성적 조회 기간, 전공·전공 외·F 제외 평점과 재수강하지 않은 F(계산값). 이름·학번·이메일·지도교수는 뺌 |
| `get_assignment_detail` | 과제 하나의 상세: 무엇을 내야 하는지(본문), 제출 형식·용량, 첨부 이름, 지금 제출 가능한지, 내 제출·점수(공개된 경우)·교수 의견 |
| `get_syllabus` | 강의계획서: 개요·학습목표, 주차별 계획, 평가 비율, 교재, 교수 이메일·연구실 전화(휴대전화·조교 정보는 뺌). 교수가 쓴 서술은 고치지 않고 그대로 넘긴다 |
| `get_graduation_progress` | 졸업 이수 현황: 취득 학점(전공·교양·기타), 필수교양(광운인되기)·균형교양 8개 영역별 학점, 입학 연도별 교양 규칙 충족 여부, 학교 졸업 사정 결과(명단에 오른 경우 졸업 가능 여부·불가 사유) |
| `get_attendance` | 출석 현황(KLAS 전자출석): 과목별 출석·결석·지각·조퇴·공결 횟수와 회차별 기록 |
| `get_exam_info` | 과목별 강의계획서 시험 관련 주차·평가 비율 + 게시판의 '시험'·'고사' 글 |
| `get_class_changes` | 전 과목 공지사항의 최근 휴강·보강·결강·비대면·강의실 변경 글 |
| `get_attachment_text` | 게시글·과제 첨부 파일 내용을 텍스트로(PDF·PPTX·DOCX·XLSX·HWP·HWPX·ipynb·코드, zip은 목록). 길면 part로 나눠 읽음 |
| `search_course_posts` | 한 과목의 공지사항·자료실 전체에서 키워드 검색(예: "시험"). `get_course_notices`는 홈 화면의 최근 글만 본다 |
| `get_course_post` | 강의 공지사항·자료실 글 하나의 본문과 첨부 이름(작성자 정보는 뺌, Q&A는 다른 학생 글이라 제외) |
| `klas_status` | 연결 상태 점검(KLAS에 요청하지 않음): 버전, 로그인 정보 출처와 가린 학번, 마지막 로그인 결과, 최근 10분 KLAS 요청 수, 공개 API 설정 여부, 업데이트 상태, 웹·폰 연결(`web_connection`: 연결 여부, 연결 서버, 자동 실행, 에이전트 실행 여부, 연결한 앱) |
| `connect_other_devices` | 웹·폰 연결(읽기 전용이 아니라 Claude가 먼저 묻는다). [how-it-works.md](how-it-works.md)의 "웹·폰에서 쓰기" |
| `disconnect_app` | `app_id` 없이: 이 PC의 연결 코드로 연결한 앱(이름은 리디렉트 호스트로 정함, 연결·마지막 사용 시각, ID). `app_id`를 주면 그 연결 하나만 끊는다(PC 연결과 다른 앱은 그대로) |
| `disconnect_this_pc` | 이 PC의 웹·폰 연결 끊기: 연결 서버에서 기기를 지우고(초대 자리도 돌려받음), 자동 실행을 없애고, `connect_other_devices`가 복사해 둔 키체인 로그인만 지운다(학생이 직접 저장한 것은 그대로) |

**합친 도구** (KLAS 개인 데이터 + kw-campus 공개 정보를 이 PC에서 합침)

| 도구 | 내용 |
|---|---|
| `this_week` | 이번 주 할 일: 마감 목록 + 같은 기간 학사일정 |
| `today_briefing` | 오늘 수업(교시·시각·강의실, 시각은 KLAS 시간표의 교시표), 오늘·내일 마감, 오늘 학식, 최근 과목 게시판 글과 학교 공지, 건물 통제·정전·휴일 같은 학교 전체 알림 |
| `my_notices` | 최근 N일 내 과목 게시판 글 + 학교 학사·장학 공지 + 내 학과·단과대 공지 |
| `academic_deadlines` | 학사 기한 모음: KLAS가 알려 주는 장학 신청·취득학점포기·성적 조회·수업평가 기간 + 학사일정의 수강신청·정정·포기, 등록, 휴·복학, 성적·이의신청, 계절학기, 졸업 일정 |
| `school_notices`, `cafeteria_menu`, `academic_calendar` | 공개 정보만 (kw-campus 공개 API) |

공개 정보는 kw-campus 공개 API에서 가져온다. 주소는 `KW_CAMPUS_INVITE`(초대 코드, `.mcpb`가 넘김), `KW_CAMPUS_API_URL`, `~/.config/kw-campus/api-url` 첫 줄 순서로 찾는다. 이 API로는 날짜 범위와 분류 같은 일반 조건만 보내고 개인 정보는 보내지 않는다. 설정이 없으면 KLAS 기능만 동작한다.

`course`는 과목명 일부("데이터")로 거르고, `semester`는 `"2026,2"` 형식이며 생략하면 현재 학기다. 제목이 같은 과제·글이 여럿이면 목록에 나온 `id`로, 첨부가 여럿이면 `file_index`로 고른다. 과제 제출, 출석 처리 같은 쓰기 기능은 일부러 넣지 않았다.

게시글 본문, 과제 설명·교수 의견, 첨부 내용, 강의계획서 서술처럼 다른 사람이 쓴 글은 `<<<KLAS_CONTENT … KLAS_CONTENT>>>` 표시 안에 담아 넘기고, 그 안의 지시는 따르지 말라고 모델에 알린다.
