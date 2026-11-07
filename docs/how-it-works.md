# 동작 방식

[README](../README.md)로 돌아가기

## 설치 (Claude 데스크톱 확장)

1. 디스코드에서 '설치하기'를 누르면 확장 파일(`kw-campus.mcpb`)과 초대 코드를 받는다.
2. 파일을 더블클릭하면 Claude 데스크톱이 설치 창을 띄운다. 학번, 비밀번호, 초대 코드를 넣으면 끝이다.
3. 웹·폰에서도 쓰려면 Claude 데스크톱에서 "웹이랑 폰에서도 쓰게 연결해 줘"라고 한다(아래 "웹·폰에서 쓰기").

확장 목록에는 "KW CAMPUS (광운 캠퍼스)"로 보인다. 학번·비밀번호·초대 코드는 Claude가 OS 키체인에 보관하고, 실행할 때 `KLAS_ID` / `KLAS_PASSWORD` / `KW_CAMPUS_INVITE` 환경변수로 넘긴다(`KW_MCP_DISTRIBUTION=mcpb`도 함께). Python과 의존성은 Claude가 `uv`로 관리한다(`server.type = "uv"`, MCPB 0.4의 실험 기능이라 실제 설치 확인이 필요하다). 1.0.0에서 확장 ID가 `kw-klas`에서 `kw-campus`로 바뀌어서, 0.x("광운대 KLAS (읽기 전용)")를 설치한 PC에서는 새 확장이 따로 설치된다. 새 확장에 학번·비밀번호를 넣은 뒤 예전 확장을 제거한다(둘 다 켜 두면 같은 도구가 두 번 보인다).

배포용 파일은 [development.md](development.md)의 "릴리스"에 있는 `scripts/release.sh`가 허용 목록에 있는 파일만 넣어 만들고 서명한다(`dist/release/kw-campus.mcpb`). 연결 서버도 같은 파일을 `/dist/kw-campus.mcpb`로 내려 준다.

로그인 정보는 `KLAS_ID` / `KLAS_PASSWORD` 환경변수가 있으면 그것을, 없으면 키체인(서비스 이름 `kw-mcp`)을 쓴다. 웹·폰 연결을 하면 확장 설정의 학번·비밀번호를 이 키체인 항목에도 저장한다(에이전트는 확장 설정 없이 로그인할 때 시작하므로).

## 로그인이 안 되는 경우

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

## KLAS 요청

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
| 학적·학점 합계 | `/std/cps/inqire/AtnlcScreHakjukInfo.do`(이름·학번·이메일·지도교수 필드는 버림) |
| 과목 게시판 목록 / 글 | `/std/lis/sport/<게시판 id>/BoardStdList.do`, `BoardStdView.do` `{boardNo, masterNo}` |

첨부 파일은 `get_attachment_text`를 부를 때만 `/common/file/DownloadFile/…`로 받아(30MB까지) 이 PC에서 텍스트로 바꾼다. 원본 파일은 남기지 않는다. 다른 학생의 제출물이나 Q&A는 읽지 않는다.

