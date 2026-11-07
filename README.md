# kw-mcp

광운대학교 KLAS(klas.kw.ac.kr)의 내 데이터를 Claude 같은 MCP 클라이언트에서 조회하는 읽기 전용 MCP 서버.

학생이 터미널을 열 일은 없다.
- **Claude 데스크톱 확장(`.mcpb`)**: 설치 창에 학번·비밀번호·초대 코드를 넣으면 이 PC에서 MCP 서버로 직접 돈다(아래 도구 표).
- **웹·폰 연결(PC 에이전트)**: Claude 데스크톱에서 "웹이랑 폰에서도 쓰게 연결해 줘"라고 하면 확장이 이 PC를 kw-campus 연결 서버(bridge)에 등록하고 에이전트를 띄운다. 그 뒤로 Claude 웹·모바일(과 ChatGPT)의 커넥터 요청에 이 PC가 답한다. 비밀번호는 PC 밖으로 나가지 않는다.

전체 그림은 [`docs/plan.md`](docs/plan.md).

KLAS에는 공개 API가 없다. 웹 화면이 내부적으로 호출하는 `*.do` JSON 엔드포인트를, 로그인 페이지와 같은 방식(RSA 암호화 로그인)으로 로그인한 세션으로 호출한다. 학교 공식 기능이 아니므로 KLAS가 바뀌면 깨질 수 있다. 본인 계정으로 개인적으로만 쓸 것.

## 도구

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
| `connect_other_devices` | 웹·폰 연결(읽기 전용이 아니라 Claude가 먼저 묻는다). 아래 "웹·폰에서 쓰기" |
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

## 설치 (Claude 데스크톱 확장)

1. 디스코드에서 '설치하기'를 누르면 확장 파일(`kw-campus.mcpb`)과 초대 코드를 받는다.
2. 파일을 더블클릭하면 Claude 데스크톱이 설치 창을 띄운다. 학번, 비밀번호, 초대 코드를 넣으면 끝이다.
3. 웹·폰에서도 쓰려면 Claude 데스크톱에서 "웹이랑 폰에서도 쓰게 연결해 줘"라고 한다(아래 "웹·폰에서 쓰기").

확장 목록에는 "KW CAMPUS (광운 캠퍼스)"로 보인다. 학번·비밀번호·초대 코드는 Claude가 OS 키체인에 보관하고, 실행할 때 `KLAS_ID` / `KLAS_PASSWORD` / `KW_CAMPUS_INVITE` 환경변수로 넘긴다(`KW_MCP_DISTRIBUTION=mcpb`도 함께). Python과 의존성은 Claude가 `uv`로 관리한다(`server.type = "uv"`, MCPB 0.4의 실험 기능이라 실제 설치 확인이 필요하다). 1.0.0에서 확장 ID가 `kw-klas`에서 `kw-campus`로 바뀌어서, 0.x("광운대 KLAS (읽기 전용)")를 설치한 PC에서는 새 확장이 따로 설치된다. 새 확장에 학번·비밀번호를 넣은 뒤 예전 확장을 제거한다(둘 다 켜 두면 같은 도구가 두 번 보인다).

배포용 파일은 아래 "릴리스"의 `scripts/release.sh`가 허용 목록에 있는 파일만 넣어 만들고 서명한다(`dist/release/kw-campus.mcpb`). 연결 서버도 같은 파일을 `/dist/kw-campus.mcpb`로 내려 준다.

로그인 정보는 `KLAS_ID` / `KLAS_PASSWORD` 환경변수가 있으면 그것을, 없으면 키체인(서비스 이름 `kw-mcp`)을 쓴다. 웹·폰 연결을 하면 확장 설정의 학번·비밀번호를 이 키체인 항목에도 저장한다(에이전트는 확장 설정 없이 로그인할 때 시작하므로).

로그인이 안 되는 경우:
- "개인번호 또는 비밀번호가 일치하지 않습니다"가 나오면 오류 문구에 실제로 로그인한 아이디가 가려진 채로(`2022******(10자리)`, 입학 연도와 길이만) 나온다. 학번이 아닌 값이 들어갔는지, 비밀번호에 한글이 섞였는지(한/영 전환)도 알려 준다. 고칠 곳은 Claude 데스크톱 설정 → 확장 프로그램 → KW CAMPUS (광운 캠퍼스) → 구성이고, 웹·폰 연결을 했다면 고친 뒤 "웹이랑 폰에서도 쓰게 연결해 줘"라고 다시 말하면 에이전트가 쓰는 키체인 항목도 바뀐다. 앞뒤 공백은 자동으로 지운다.
- KLAS가 비밀번호를 거부하면, 저장된 학번·비밀번호가 바뀔 때까지 같은 비밀번호를 다시 보내지 않는다. 다시 시작해도 마찬가지다(`~/.config/kw-mcp/login-state.json`에 학번·비밀번호의 솔트 PBKDF2 지문과 시각만 남기고, 원문은 남기지 않는다). 설정에서 비밀번호를 고치면 바로 다시 시도한다.
- 비밀번호를 3번 넘게 틀리면 KLAS가 캡차를 요구한다. 그래서 실패가 2번 쌓이면 비밀번호를 확인하는 단계(`LoginConfirm.do`) 전에 멈춘다. 브라우저에서 한 번 직접 로그인하면 풀린다. 실패 횟수는 10분마다 다시 확인하는데, 이때 KLAS 로그인 페이지와 같은 방식으로 학번·비밀번호를 암호화한 로그인 토큰을 `LoginCaptcha.do`에 보내 횟수만 묻고, `LoginConfirm.do`로는 넘어가지 않는다.
- 2차 인증이 켜진 계정은 자동 로그인을 할 수 없다. 2차 인증 요청이 학생에게 가므로 1시간에 한 번만 다시 시도한다. 임시 비밀번호 상태인 계정은 비밀번호를 바꿀 때까지 멈춘다.

## 웹·폰에서 쓰기 (PC 에이전트)

Claude 데스크톱에서 "웹이랑 폰에서도 쓰게 연결해 줘"라고 하면 Claude가 `connect_other_devices`를 부른다(읽기 전용 도구가 아니라 먼저 허락을 묻는다). 이 도구는 아무것도 묻지 않고 차례로:

1. 확장 설정의 초대 코드에서 연결 서버 주소를 읽는다. 없거나 읽을 수 없으면 디스코드에서 '설치하기'로 초대 코드를 받아 확장 설정의 '초대 코드' 칸에 넣으라고만 답하고 아무것도 하지 않는다. KW CAMPUS 연결 서버(`kw_mcp.release.BRIDGE_ORIGIN`, 한 곳에만 적음)가 아닌 주소의 초대 코드는 거절한다. 등록 응답과 저장된 연결의 WebSocket 주소도 `BRIDGE_WS_URL`이어야 한다(다르면 등록하지 않고, 에이전트는 접속하지 않는다). 공개 정보 토큰, 업데이트 확인, 에이전트 접속, 터미널의 `kw-mcp link`도 같다. 개발할 때만 `KW_CAMPUS_DEV_BRIDGE=http://localhost:<포트>`와 `KW_CAMPUS_DEV_BRIDGE_WS=ws://localhost:<포트>/<경로>`(또는 `127.0.0.1`)로 이 PC의 연결 서버를 대신 쓸 수 있다.
2. 확장 설정의 학번·비밀번호로 KLAS에 한 번 로그인해 본다. 안 되면 이유(비밀번호 거부, 보안문자·2차 인증 → 브라우저에서 KLAS에 한 번 로그인 등)를 답하고 멈춘다.
3. 학번·비밀번호를 키체인(`kw-mcp`)에 저장한다(없거나 다를 때만). 에이전트가 여기서 읽는다.
4. 이 PC를 연결 서버에 등록한다(기기 키를 만들어 개인키는 키체인, 공개키만 서버로). 이미 그 서버에 등록돼 있으면 기기와 거기 묶인 커넥터를 그대로 둔다. 초대가 철회된 기기는 설정의 초대 코드로 다시 등록한다. 서버가 기기 서명을 거부하면(키체인의 키가 다름) 새로 등록할지 묻고, 학생이 원할 때만 `relink=true`로 다시 등록한다.
5. 15분짜리 1회용 연결 코드를 받는다.
6. 로그인할 때 에이전트가 켜지게 등록하고 지금 띄운다(Mac: `~/Library/LaunchAgents/kr.kwcampus.agent.plist`, Windows: `HKCU\...\Run`). 명령은 확장 자신의 Python(`sys.executable`, 확장 폴더의 `.venv`)으로 `-m kw_mcp agent --from-extension`을 실행한다.
7. 브라우저에서 `<연결 서버>/connect#<연결 코드>`를 연다. 이 페이지가 쿠키를 남겨, 같은 브라우저에서 커넥터 승인 화면을 열면 "이 PC와 연결하기" 한 번으로 끝난다. 다른 기기에서는 승인 화면에 연결 코드를 넣는다.

결과는 `{"connected": true, "connect_url", "mcp_url", "browser_opened", "already_linked", "next": [학생에게 전할 단계], "note"?}`이다. 브라우저가 열리면 연결 코드는 브라우저와 데스크톱 알림("KW CAMPUS 연결 코드")으로만 가고 결과(모델이 읽는 것)에는 없다. 알림은 PC와 브라우저의 공인 IP가 달라(iCloud 비공개 릴레이, VPN) 연결 페이지가 자동 연결을 못 할 때 쓴다. 브라우저가 안 열렸거나 알림을 띄울 수 없는 PC에서만 `code`, `expires_in_minutes`, `caution`을 준다. 설정이 빠졌으면 `{"connected": false, "missing": "invite" | "credentials", "message", "next"}`, KLAS·초대 문제면 `"problem"`이 붙는다. 네트워크, PC 시계, 키체인, launchctl·레지스트리 실패는 도구 오류로 이유와 할 일을 돌려준다.

에이전트는 연결 서버와 WebSocket을 유지하다가(5분마다 핑, 끊기면 최대 60초 간격으로 다시 접속) 요청이 오면 KLAS에서 정해 둔 필드만 읽고(`SNAPSHOT_FIELDS`), 서버가 요청마다 보낸 AES-256 키로 암호화해 올린다. 결과를 올릴 주소가 연결한 서버가 아니면 무시한다. 한 사용자 계정에 에이전트는 하나만 돈다(사용자별 잠금 파일로 확인).

**업데이트**: 확장이 띄운 에이전트(`--from-extension`, 확장 안의 `KW_MCP_DISTRIBUTION=mcpb`)는 스스로 wheel을 설치하지 않는다. 그 환경은 Claude 데스크톱 것이고, 새 버전은 확장과 함께 온다(아래 "확장 업데이트"). 확장이 업데이트되면 돌던 에이전트는 옛 코드로 남으므로, 확장의 MCP 서버가 시작할 때 백그라운드에서 확인해 다시 띄운다: 자동 실행이 이 확장의 명령(`--from-extension` 포함) 그대로이고, 에이전트가 켜져 있고, 시작할 때 `~/.config/kw-campus/agent-state.json`에 남긴 버전이 확장 버전과 다를 때만, 그리고 버전마다 한 번만(`~/.config/kw-campus/extension-restarted`). 예전 방식으로 설치한 에이전트는 건드리지 않는다. 연결 상태는 `klas_status`의 `web_connection`에서 보고, 새 연결 알림이 오면 Claude 데스크톱에서 "연결된 앱 끊어 줘"라고 해 `disconnect_app`으로 끊는다.

예전 방식(터미널 설치 명령, `uv tool`)으로 설치한 에이전트는 전과 같이 스스로 업데이트한다. 에이전트는 시작 10분 뒤와 6시간마다(비정상 종료 뒤에는 30~60초 뒤) 연결 서버의 `/dist/latest.json`을 본다. 버전이 더 높고, Ed25519 서명이 `kw_mcp/release.py`의 공개키와 맞고, 받은 wheel과 의존성 고정 파일(constraints)이 서명된 SHA-256과 같을 때만 설치한다. 설치는 고정된 의존성 버전과 릴리스 시각 이전에 올라온 패키지만 쓰고(`--constraints`, `--exclude-newer`, `--no-build`), `uv tool install`은 고정 파일의 해시를 보지 않으므로 바로 이어서 모든 의존성을 `uv pip install --require-hashes`로 해시를 확인하며 다시 설치한다(그 전에는 새 의존성의 코드가 실행되지 않는다). 새 버전이 스스로 실행되는지(`--version` 자체 점검) 확인한 뒤에야 다시 시작한다(macOS는 launchd가, Windows는 에이전트가 끝난 뒤 별도 프로세스가 설치하고 띄움). 해시 확인이나 자체 점검에 실패하면 돌던 버전을 다시 설치해 그대로 쓴다. 바로 전 버전은 `~/.config/kw-campus/releases`에 남겨 두고, 새 버전이 연결 후 2분을 채우기 전에 두 번 멈추면(시작하다 예외가 나든, 강제로 꺼지든) 다음 시작 때 되돌리고 그 버전은 건너뛴다. 자체 점검에 실패한 버전도 다시 받지 않는다(Windows 포함). 서명 키는 릴리스하는 PC의 키체인에만 있어서, 서버만으로는 백그라운드 업데이트로 PC에 코드를 밀어 넣을 수 없다. 다만 서명은 백그라운드 업데이트만 보호한다. 예전 설치 명령과 연결 서버에서 받는 `.mcpb`는 연결 서버를 TLS로 믿는다.

**관리용 명령** (개발·문제 해결용. 학생 안내에는 쓰지 않는다): `kw-mcp link <초대코드>`(터미널에서 같은 연결), `code`(새 연결 코드), `connections`(연결한 앱과 ID), `revoke <ID>`(앱 하나만 끊기), `status`, `update`(uv tool 설치만), `setup`·`check`·`forget`(키체인 로그인), `unlink [--force]`(이 PC 연결 해제; 서버가 해제를 확인한 뒤에만 기기 키를 지움), `agent`(에이전트 본체).

**릴리스**:
1. `pyproject.toml`과 `manifest.json`의 version을 같은 값으로, 지난 릴리스보다 높게 올리고 kw-mcp와 kw-campus 양쪽에서 `uv lock`. 에이전트와 확장은 더 높은 버전만 받는다.
2. 커밋하고 `git tag v<버전>`.
3. (연습) `scripts/release.sh --dry-run`: 버리는 키로 서명해 `dist/release-dry-run/`에 만든다. 배포에는 못 쓴다.
4. `scripts/release.sh`: 작업 트리가 깨끗한지, 태그와 세 곳의 버전이 맞는지, 버전이 지난 릴리스(다른 커밋의 `v*` 태그, 지난 `dist/release/latest.json`, `--last-latest-json`으로 넘긴 연결 서버의 `latest.json`)보다 높은지 확인 → HEAD를 꺼내 허용 목록의 파일만 `.mcpb`(zip, `mcpb pack`과 같은 형식)로 묶고 해시를 적어 둠 → `uv lock --check`와 테스트 → wheel·constraints를 만들고 해시를 적어 둔 뒤 에이전트 업데이트와 같은 방식으로 시험 설치(해시 확인, 자체 점검 포함) → 세 파일이 적어 둔 해시 그대로인지 확인한 뒤에야 키체인의 키로 서명하고 검증해 `dist/release/`로 바꿔 넣는다(`python -m kw_mcp.release keygen`은 처음 한 번만). 서명하는 실행에서는 npm 코드를 돌리지 않는다(같은 사용자 권한이면 서명 키를 읽을 수 있다). `mcpb`의 매니페스트 검사와 풀기는 packaging 워크플로(CI)가 같은 방식으로 묶은 파일에 돌린다. 연결 서버 버전과 비교하려면 `curl -fsS https://<bridge>/dist/latest.json -o /tmp/latest.json` 뒤 `scripts/release.sh --last-latest-json /tmp/latest.json`.
5. 커밋과 태그를 push.
6. kw-campus에서 `scripts/build_lambda.sh`(검증된 `dist/release`만 복사, 없거나 검증에 실패하면 멈춤) → `cdk deploy`.

**확장 업데이트**: Claude 데스크톱은 파일로 설치한 확장을 스스로 업데이트하지 않는다. 그래서 확장이 초대 코드의 서버에서 `latest.json`의 `mcpb` 항목을 6시간마다 확인하고, 서명이 맞는 더 높은 버전이 있으면 `this_week`·`today_briefing`·`my_notices` 답에 `update_available`을 붙인다. `download_update` 도구(읽기 전용이 아니라 Claude가 사용자에게 먼저 묻는다)는 새 파일을 받아 서명된 SHA-256과 맞을 때만 다운로드 폴더에 저장한다. 확장은 `uv run --frozen --no-dev`로 의존성을 uv.lock에 고정된 버전·해시로만, 개발용 패키지 없이 설치한다. 다만 이 프로젝트 자체를 빌드하는 `uv_build`(빌드 백엔드)는 uv.lock에 들어가지 않는다. `pyproject.toml`에서 버전을 정확히 고정해 두었고, 같은 버전의 uv는 내장 백엔드를 쓰지만, 다른 버전의 uv는 그 버전을 PyPI에서 해시 확인 없이 받아 학번·비밀번호 환경변수가 있는 상태로 실행한다. 서명 단계는 `.mcpb` 안의 코드가 같은 버전 wheel과 다르면 거부한다(오래된 파일이 서명되는 것 방지).

## Claude Code에 등록

```bash
claude mcp add kw-campus --scope user -- uv run --directory <kw-mcp 경로> kw-mcp
```

Claude Desktop은 `claude_desktop_config.json`의 `mcpServers`에 같은 명령을 넣는다:

```json
{
  "mcpServers": {
    "kw-campus": {
      "command": "uv",
      "args": ["run", "--directory", "<kw-mcp 경로>", "kw-mcp"]
    }
  }
}
```

## 동작 방식

- 로그인: `LoginSecurity.do`에서 RSA 공개키를 받아 `{loginId, loginPwd, storeIdYn}`을 PKCS#1 v1.5로 암호화하고 `LoginCaptcha.do` → `LoginConfirm.do` 순서로 보낸다. 로그인 페이지의 JSEncrypt 코드와 같은 절차다.
- 세션이 만료되면 KLAS는 로그인 페이지로 302를 보내거나, AJAX 요청에는 `{"loginRequired": true}` JSON으로 답한다. 둘 다 한 번 다시 로그인하고 요청을 재시도한다. 여러 요청이 동시에 만료를 만나도 로그인은 한 번만 한다.
- 비밀번호가 거부되면 로그인 정보가 바뀔 때까지 다시 보내지 않는다(위 "로그인이 안 되는 경우"). 틀린 비밀번호로 반복 시도하다 캡차가 걸리는 것을 막기 위해서다.
- KLAS 점검·과부하(429·502·503·504, 점검 안내 페이지, 연결 오류)를 만나면 모든 요청이 30초 쉰다.
- 요청마다 `kw-mcp/<버전> (+https://github.com/kyowon1108/kw-mcp; contact kyowon1108@gmail.com)` User-Agent를 보낸다. 학교가 이 프로그램을 알아보고 연락할 수 있게 하기 위해서다. KLAS가 이 User-Agent를 거부하면(401·403·406) 브라우저인 척 다시 시도하지 않고 멈춘다.
- KLAS로 가는 요청은 동시에 최대 4개, 초당 약 8개(순간 16개)이고, 10분에 600개를 넘으면 멈추고 그렇다고 알린다. 학기·홈 정보는 2분, 과목별 조회 결과는 1분 동안 재사용하고, 동시에 들어온 같은 요청은 하나로 합친다.
- `get_deadlines`는 마감이 지났어도 지각 제출 기간 안이면 `late_submission: true`로 포함한다.

| 데이터 | 엔드포인트 |
|---|---|
| 학기·과목 목록 | `/std/cmn/frame/YearhakgiAtnlcSbjectList.do` |
| 홈(과목·시간표·과목 공지) | `/std/cmn/frame/StdHome.do` `{searchYearhakgi}` |
| 과제 / 온라인 강의 / 프로젝트 | `/std/lis/evltn/{TaskStdList,SelectOnlineCntntsStdList,PrjctStdList}.do` `{selectSubj, selectYearhakgi, selectChangeYn:"Y"}` |
| 성적 | `/std/cps/inqire/AtnlcScreSungjukInfo.do`, `AtnlcScreSungjukTot.do` |
| 과제 상세 / 첨부 이름 | `/std/lis/evltn/TaskStdView.do` `{selectSubj, selectYearhakgi, ordseq}`, `/common/file/UploadFileList.do` `{storageId, attachId}` |
| 강의계획서 | `/std/cps/atnlc/LectrePlanData.do` `{selectSubj}` |
| 과목 게시판 목록 / 글 | `/std/lis/sport/<게시판 id>/BoardStdList.do`, `BoardStdView.do` `{boardNo, masterNo}` |

첨부 파일은 `get_attachment_text`를 부를 때만 `/common/file/DownloadFile/…`로 받아(30MB까지) 이 PC에서 텍스트로 바꾼다. 원본 파일은 남기지 않는다. 다른 학생의 제출물이나 Q&A는 읽지 않는다.

| 학적·학점 합계 | `/std/cps/inqire/AtnlcScreHakjukInfo.do`(이름·학번·이메일·지도교수 필드는 버림) |

## 개발

```bash
uv sync
uv run kw-mcp setup   # 학번/비밀번호를 OS 키체인(macOS 키체인, Windows 자격 증명 관리자)에 저장 (비밀번호는 화면에 안 보임)
uv run kw-mcp check   # 로그인해서 과목·과제·강의 개수만 출력
uv run pytest -q
```

키체인의 로그인을 지우려면 `uv run kw-mcp forget`.

테스트는 KLAS를 흉내 낸 응답(respx)으로 돌고 실제 서버에 접속하지 않는다.
