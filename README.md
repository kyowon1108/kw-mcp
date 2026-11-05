# kw-mcp

광운대학교 KLAS(klas.kw.ac.kr)의 내 데이터를 Claude 같은 MCP 클라이언트에서 조회하는 읽기 전용 MCP 서버.

쓰는 방법은 두 가지다.
- **Claude 데스크톱 확장 / Claude Code**: 이 PC에서 MCP 서버로 직접 돈다(아래 도구 표).
- **PC 에이전트**: kw-campus 연결 서버(bridge)에 붙어서, Claude 웹·모바일과 ChatGPT의 커넥터 요청에 이 PC가 답한다. 비밀번호는 PC 밖으로 나가지 않는다.

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
| `get_course_evaluation` | 수업평가: 평가 기간인지(중간/기말), 아직 평가하지 않은 과목 |
| `get_grades` | 학기별 과목 성적·학기 평점(계산값), KLAS 평량평균(학적부·성적증명서 기준), 전공·교양·기타 신청/취득/삭제 학점, 학과·학년·학적 상태, 학기별 석차·학사경고, 성적 조회 기간, 전공·전공 외·F 제외 평점과 재수강하지 않은 F(계산값). 이름·학번·이메일·지도교수는 뺌 |
| `get_assignment_detail` | 과제 하나의 상세: 무엇을 내야 하는지(본문), 제출 형식·용량, 첨부 이름, 지금 제출 가능한지, 내 제출·점수(공개된 경우)·교수 의견 |
| `get_syllabus` | 강의계획서: 개요·학습목표, 주차별 계획, 평가 비율, 교재, 교수 이메일·연구실 전화(휴대전화·조교 정보는 뺌) |
| `get_graduation_progress` | 졸업 이수 현황: 취득 학점(전공·교양·기타), 필수교양(광운인되기)·균형교양 8개 영역별 학점, 입학 연도별 교양 규칙 충족 여부 |
| `get_attendance` | 출석 현황(KLAS 전자출석): 과목별 출석·결석·지각·조퇴·공결 횟수와 회차별 기록 |
| `get_exam_info` | 과목별 강의계획서 시험 관련 주차·평가 비율 + 게시판의 '시험' 글 |
| `get_class_changes` | 전 과목 공지사항의 최근 휴강·보강 글 |
| `get_attachment_text` | 게시글·과제 첨부 파일 내용을 텍스트로(PDF·PPTX·DOCX·XLSX·HWP·HWPX·ipynb·코드, zip은 목록). 길면 part로 나눠 읽음 |
| `search_course_posts` | 한 과목의 공지사항·자료실 전체에서 키워드 검색(예: "시험"). `get_course_notices`는 홈 화면의 최근 글만 본다 |
| `get_course_post` | 강의 공지사항·자료실 글 하나의 본문과 첨부 이름(작성자 정보는 뺌, Q&A는 다른 학생 글이라 제외) |

**합친 도구** (KLAS 개인 데이터 + kw-campus 공개 정보를 이 PC에서 합침)

| 도구 | 내용 |
|---|---|
| `this_week` | 이번 주 할 일: 마감 목록 + 같은 기간 학사일정 |
| `today_briefing` | 오늘 수업(교시·강의실), 오늘·내일 마감, 오늘 학식, 최근 과목 게시판 글과 학교 공지 |
| `my_notices` | 최근 N일 내 과목 게시판 글 + 학교 학사·장학 공지 |
| `academic_deadlines` | 학사 기한 모음: KLAS가 알려 주는 장학 신청·취득학점포기·성적 조회·수업평가 기간 + 학사일정의 수강신청·정정·포기, 등록, 휴·복학, 성적·이의신청, 계절학기, 졸업 일정 |
| `school_notices`, `cafeteria_menu`, `academic_calendar` | 공개 정보만 (kw-campus 공개 API) |

공개 정보는 kw-campus 공개 API에서 가져온다. 주소는 `KW_CAMPUS_INVITE`(초대 코드, `.mcpb`가 넘김), `KW_CAMPUS_API_URL`, `~/.config/kw-campus/api-url` 첫 줄 순서로 찾는다. 이 API로는 날짜 범위와 분류 같은 일반 조건만 보내고 개인 정보는 보내지 않는다. 설정이 없으면 KLAS 기능만 동작한다.

`course`는 과목명 일부("데이터")로 거르고, `semester`는 `"2026,2"` 형식이며 생략하면 현재 학기다. 과제 제출, 출석 처리 같은 쓰기 기능은 일부러 넣지 않았다.

## 설치와 로그인 설정

```bash
uv sync
uv run kw-mcp setup   # 학번/비밀번호를 macOS 키체인에 저장 (비밀번호는 화면에 안 보임)
uv run kw-mcp check   # 로그인해서 과목·과제·강의 개수만 출력
```

로그인 정보는 `KLAS_ID` / `KLAS_PASSWORD` 환경변수가 있으면 그것을, 없으면 키체인(서비스 이름 `kw-mcp`)을 쓴다. 지우려면 `uv run kw-mcp forget`.

로그인이 안 되는 경우:
- "개인번호 또는 비밀번호가 일치하지 않습니다"가 나오면 오류 문구에 실제로 로그인한 아이디가 가려진 채로(`2022****80(10자리)`) 나온다. 학번이 아닌 값이 들어갔는지, 비밀번호에 한글이 섞였는지(한/영 전환)도 알려 주고, 고칠 곳을 설치 방식에 맞게 안내한다. `.mcpb`로 설치했다면 Claude 데스크톱 설정 → 확장 프로그램 → 광운대 KLAS → 구성, 그 밖에는 `kw-mcp setup`. 앞뒤 공백은 자동으로 지운다.
- 비밀번호를 3번 넘게 틀리면 KLAS가 캡차를 요구한다. 브라우저에서 한 번 직접 로그인하면 풀린다.
- 2차 인증이 켜진 계정, 임시 비밀번호 상태인 계정은 자동 로그인을 할 수 없다.

## Claude 데스크톱에 클릭 한 번으로 설치 (.mcpb)

```bash
npx -y @anthropic-ai/mcpb pack . dist/kw-klas.mcpb   # 또는 로컬에 설치한 mcpb
```

`dist/kw-klas.mcpb`를 더블클릭하면 Claude 데스크톱이 설치 화면을 띄운다. 학번, 비밀번호, 초대 코드(선택)를 넣으면 끝이다. 비밀번호와 초대 코드는 Claude가 OS 키체인에 보관하고, 실행할 때 환경변수로 넘긴다. Python과 의존성은 Claude가 `uv`로 관리한다(`server.type = "uv"`, MCPB 0.4의 실험 기능이라 실제 설치 확인이 필요하다). 연결 서버도 같은 파일을 `/dist/kw-klas.mcpb`로 내려 준다.

## PC 에이전트 (Claude 웹·모바일, ChatGPT용)

친구에게는 연결 서버의 안내 페이지 `https://<bridge>/setup#<초대코드>`를 보내면 된다. 거기 나오는 명령 한 줄이 uv 설치 → 이 패키지 설치 → `kw-mcp link`를 차례로 한다.

| 명령 | 하는 일 |
|---|---|
| `kw-mcp link <초대코드>` | 처음 한 번. 학번·비밀번호를 키체인에 저장(없으면 물어봄) → KLAS 로그인 확인 → 기기 키 생성(개인키는 키체인, 공개키만 서버로) → 로그인 시 자동 실행 등록 → 커넥터 URL과 연결 코드 출력 |
| `kw-mcp code` | 커넥터 승인 페이지에 넣을 새 연결 코드 (15분, 1회용). 앱을 하나 더 연결할 때 |
| `kw-mcp status` | 연결·자동 실행·실행 중 여부, 로그 위치 |
| `kw-mcp setup` | 비밀번호를 바꿨을 때. 에이전트는 다음 요청부터 새 값을 쓴다 |
| `kw-mcp unlink` | 이 PC 연결 해제 (커넥터도 더는 동작하지 않음) |
| `kw-mcp agent` | 에이전트 본체. 자동 실행이 띄운다 (Mac: `~/Library/LaunchAgents/kr.kwcampus.agent.plist`, Windows: `HKCU\...\Run`) |

에이전트는 연결 서버와 WebSocket을 유지하다가(5분마다 핑, 끊기면 최대 60초 간격으로 다시 접속) 요청이 오면 KLAS에서 정해 둔 필드만 읽고(`SNAPSHOT_FIELDS`), 서버가 요청마다 보낸 AES-256 키로 암호화해 올린다. 결과를 올릴 주소가 연결한 서버가 아니면 무시한다. 한 PC에 에이전트는 하나만 돈다(localhost 47811 포트로 확인).

**자동 업데이트**: 에이전트는 시작 10분 뒤와 6시간마다 연결 서버의 `/dist/latest.json`을 본다. 버전이 더 높고, Ed25519 서명이 `kw_mcp/release.py`의 공개키와 맞고, 받은 파일이 서명된 SHA-256과 같을 때만 설치하고 다시 시작한다(macOS는 launchd가, Windows는 에이전트가 끝난 뒤 별도 프로세스가 설치하고 띄움). 서명 키는 릴리스하는 PC의 키체인에만 있어서, 서버만으로는 PC에 코드를 밀어 넣을 수 없다. 처음 설치한 명령을 다시 실행해도 업데이트되고, 이때 기기 등록과 커넥터 연결은 그대로다.

**릴리스**: `pyproject.toml`과 `manifest.json`의 version을 같은 값으로 올리고, `mcpb pack . dist/kw-klas.mcpb` → kw-campus의 `scripts/build_lambda.sh` → `cdk deploy`. 빌드가 키체인의 키로 wheel과 `.mcpb`를 함께 서명한다(`python -m kw_mcp.release keygen`은 처음 한 번만).

**확장 업데이트**: Claude 데스크톱은 파일로 설치한 확장을 스스로 업데이트하지 않는다. 그래서 확장이 초대 코드의 서버에서 `latest.json`의 `mcpb` 항목을 6시간마다 확인하고, 서명이 맞는 더 높은 버전이 있으면 `this_week`·`today_briefing`·`my_notices` 답에 `update_available`을 붙인다. `download_update` 도구(읽기 전용이 아니라 Claude가 사용자에게 먼저 묻는다)는 새 파일을 받아 서명된 SHA-256과 맞을 때만 다운로드 폴더에 저장한다. 확장은 `uv run --frozen --no-dev`로 uv.lock에 고정된 버전·해시만, 개발용 패키지 없이 설치한다. 서명 단계는 `.mcpb` 안의 코드가 같은 버전 wheel과 다르면 거부한다(오래된 파일이 서명되는 것 방지).

## Claude Code에 등록

```bash
claude mcp add kw-klas --scope user -- uv run --directory /Users/kapr/Projects/University/kw-mcp kw-mcp
```

Claude Desktop은 `claude_desktop_config.json`의 `mcpServers`에 같은 명령을 넣는다:

```json
{
  "mcpServers": {
    "kw-klas": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/kapr/Projects/University/kw-mcp", "kw-mcp"]
    }
  }
}
```

## 동작 방식

- 로그인: `LoginSecurity.do`에서 RSA 공개키를 받아 `{loginId, loginPwd, storeIdYn}`을 PKCS#1 v1.5로 암호화하고 `LoginCaptcha.do` → `LoginConfirm.do` 순서로 보낸다. 로그인 페이지의 JSEncrypt 코드와 같은 절차다.
- 세션이 만료되면 KLAS는 로그인 페이지로 302를 보낸다. 이때 한 번 다시 로그인하고 요청을 재시도한다. 여러 요청이 동시에 만료를 만나도 로그인은 한 번만 한다.
- 로그인이 거부되면(비밀번호 오류, 캡차, 2차 인증) 10분 동안 다시 시도하지 않는다. 틀린 비밀번호로 반복 시도하다 캡차가 걸리는 것을 막기 위해서다.
- KLAS로 가는 요청은 동시에 최대 4개다. 학기·홈 정보는 2분, 과목별 조회 결과는 1분 동안 재사용하고, 동시에 들어온 같은 요청은 하나로 합친다.
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
uv run pytest -q
```

테스트는 KLAS를 흉내 낸 응답(respx)으로 돌고 실제 서버에 접속하지 않는다.
