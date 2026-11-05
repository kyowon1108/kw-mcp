# kw-mcp

광운대학교 KLAS(klas.kw.ac.kr)의 내 데이터를 Claude 같은 MCP 클라이언트에서 조회하는 읽기 전용 MCP 서버.

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
| `get_deadlines` | N일 안에 마감되는 미제출 과제·퀴즈·팀플 + 미완료 온라인 강의 |
| `get_grades` | 학기별 성적과 학점 합계 |

**합친 도구** (KLAS 개인 데이터 + kw-campus 공개 정보를 이 PC에서 합침)

| 도구 | 내용 |
|---|---|
| `this_week` | 이번 주 할 일: 마감 목록 + 같은 기간 학사일정 |
| `today_briefing` | 오늘 수업(교시·강의실), 오늘·내일 마감, 오늘 학식, 최근 과목 게시판 글과 학교 공지 |
| `my_notices` | 최근 N일 내 과목 게시판 글 + 학교 학사·장학 공지 |
| `school_notices`, `cafeteria_menu`, `academic_calendar` | 공개 정보만 (kw-campus 공개 API) |

공개 정보는 `KW_CAMPUS_API_URL`(또는 `~/.config/kw-campus/api-url` 첫 줄)에 적힌 kw-campus 공개 API에서 가져온다. 이 API로는 날짜 범위와 분류 같은 일반 조건만 보내고 개인 정보는 보내지 않는다. 설정이 없으면 KLAS 기능만 동작한다.

`course`는 과목명 일부("데이터")로 거르고, `semester`는 `"2026,2"` 형식이며 생략하면 현재 학기다. 과제 제출, 출석 처리 같은 쓰기 기능은 일부러 넣지 않았다.

## 설치와 로그인 설정

```bash
uv sync
uv run kw-mcp setup   # 학번/비밀번호를 macOS 키체인에 저장 (비밀번호는 화면에 안 보임)
uv run kw-mcp check   # 로그인해서 과목·과제·강의 개수만 출력
```

로그인 정보는 `KLAS_ID` / `KLAS_PASSWORD` 환경변수가 있으면 그것을, 없으면 키체인(서비스 이름 `kw-mcp`)을 쓴다. 지우려면 `uv run kw-mcp forget`.

로그인이 안 되는 경우:
- 비밀번호를 3번 넘게 틀리면 KLAS가 캡차를 요구한다. 브라우저에서 한 번 직접 로그인하면 풀린다.
- 2차 인증이 켜진 계정, 임시 비밀번호 상태인 계정은 자동 로그인을 할 수 없다.

## Claude 데스크톱에 클릭 한 번으로 설치 (.mcpb)

```bash
npx -y @anthropic-ai/mcpb pack . dist/kw-klas.mcpb   # 또는 로컬에 설치한 mcpb
```

`dist/kw-klas.mcpb`를 더블클릭하면 Claude 데스크톱이 설치 화면을 띄운다. 학번, 비밀번호, kw-campus 공개 API 주소(선택)를 넣으면 끝이다. 비밀번호와 API 주소는 Claude가 OS 키체인에 보관하고, 실행할 때 환경변수로 넘긴다. Python과 의존성은 Claude가 `uv`로 관리한다(`server.type = "uv"`).

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

## 개발

```bash
uv run pytest -q
```

테스트는 KLAS를 흉내 낸 응답(respx)으로 돌고 실제 서버에 접속하지 않는다.

## 다음 단계: AWS 서버리스

같은 코드를 Lambda(서울 리전)에 올리려면 `mcp.run("streamable-http")`을 stateless 모드로 쓰고, 로그인 정보는 Secrets Manager, 세션 쿠키는 DynamoDB(TTL)에 두면 된다. 먼저 확인할 것:
1. AWS IP에서 KLAS 접속이 막히지 않는지
2. 서버가 로그인하면 폰·PC의 KLAS 세션이 끊기는지
