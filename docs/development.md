# 개발과 릴리스

[README](../README.md)로 돌아가기

## 개발

```bash
uv sync
uv run kw-mcp setup   # 학번/비밀번호를 OS 키체인(macOS 키체인, Windows 자격 증명 관리자)에 저장 (비밀번호는 화면에 안 보임)
uv run kw-mcp check   # 로그인해서 과목·과제·강의 개수만 출력
uv run pytest -q
```

키체인의 로그인을 지우려면 `uv run kw-mcp forget`.

테스트는 KLAS를 흉내 낸 응답(respx)으로 돌고 실제 서버에 접속하지 않는다.

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

## 관리용 명령

개발·문제 해결용. 학생 안내에는 쓰지 않는다.

`kw-mcp link <초대코드>`(터미널에서 같은 연결), `code`(새 연결 코드), `connections`(연결한 앱과 ID), `revoke <ID>`(앱 하나만 끊기), `status`, `update`(uv tool 설치만), `setup`·`check`·`forget`(키체인 로그인), `unlink [--force]`(이 PC 연결 해제; 서버가 해제를 확인한 뒤에만 기기 키를 지움), `agent`(에이전트 본체).

## 릴리스

1. `pyproject.toml`과 `manifest.json`의 version을 같은 값으로, 지난 릴리스보다 높게 올리고 kw-mcp와 kw-campus 양쪽에서 `uv lock`. 에이전트와 확장은 더 높은 버전만 받는다.
2. 커밋하고 `git tag v<버전>`.
3. (연습) `scripts/release.sh --dry-run`: 버리는 키로 서명해 `dist/release-dry-run/`에 만든다. 배포에는 못 쓴다.
4. `scripts/release.sh`: 작업 트리가 깨끗한지, 태그와 세 곳의 버전이 맞는지, 버전이 지난 릴리스(다른 커밋의 `v*` 태그, 지난 `dist/release/latest.json`, `--last-latest-json`으로 넘긴 연결 서버의 `latest.json`)보다 높은지 확인 → HEAD를 꺼내 허용 목록의 파일만 `.mcpb`(zip, `mcpb pack`과 같은 형식)로 묶고 해시를 적어 둠 → `uv lock --check`와 테스트 → wheel·constraints를 만들고 해시를 적어 둔 뒤 에이전트 업데이트와 같은 방식으로 시험 설치(해시 확인, 자체 점검 포함) → 세 파일이 적어 둔 해시 그대로인지 확인한 뒤에야 키체인의 키로 서명하고 검증해 `dist/release/`로 바꿔 넣는다(`python -m kw_mcp.release keygen`은 처음 한 번만). 서명하는 실행에서는 npm 코드를 돌리지 않는다(같은 사용자 권한이면 서명 키를 읽을 수 있다). `mcpb`의 매니페스트 검사와 풀기는 packaging 워크플로(CI)가 같은 방식으로 묶은 파일에 돌린다. 연결 서버 버전과 비교하려면 `curl -fsS https://<bridge>/dist/latest.json -o /tmp/latest.json` 뒤 `scripts/release.sh --last-latest-json /tmp/latest.json`.
5. 커밋과 태그를 push.
6. kw-campus에서 `scripts/build_lambda.sh`(검증된 `dist/release`만 복사, 없거나 검증에 실패하면 멈춤) → `cdk deploy`.

## 데이터만 바꿀 때 (`knowledge/`, `rules/`)

`scripts/release.sh data` → kw-campus `scripts/build_lambda.sh` → `cdk deploy`. 릴리스도 재설치도 필요 없다. `data`는 트리 버전이 마지막 릴리스(태그·`dist/release`)와 같고 깨끗할 때만, HEAD에서 데이터 파일을 꺼내 `test_knowledge`·`test_simulation`을 돌리고, 릴리스 키로 서명한 `data.json`(`data_version`, `app`(그 릴리스의 major.minor), `min_app`, 파일별 sha256·크기)과 함께 `dist/data/`에 둔다(`data --dry-run`은 버리는 키로 `dist/data-dry-run/`). 확장(초대 코드가 있을 때)과 PC 에이전트는 하루 한 번 서명, 같은 major.minor인지, `min_app`, 버전을 확인하고 바뀐 파일만 받아 `~/.config/kw-campus/data/`에 둔다(`kw_mcp/datasync.py`). 도구 호출 하나는 시작할 때의 자료 한 벌만 쓴다. 데이터 모양을 바꿔 옛 버전이 못 읽게 되면 `datasync.MIN_APP`을 올린다.

## 확장 업데이트

Claude 데스크톱은 파일로 설치한 확장을 스스로 업데이트하지 않는다. 그래서 확장이 초대 코드의 서버에서 `latest.json`의 `mcpb` 항목을 6시간마다 확인하고, 서명이 맞는 더 높은 버전이 있으면 `this_week`·`today_briefing`·`my_notices` 답에 `update_available`을 붙인다. 여기에는 그 버전의 바뀐 점(`release_notes.json`의 1~5줄, 파일과 따로 서명)이 `changes`로 들어가고, 서명이 맞지 않거나 너무 길면 바뀐 점만 빼고 알린다. `check_update`는 지금 버전의 바뀐 점도 `this_version_changes`로 준다. 릴리스는 그 버전 항목이 없으면 멈춘다. `download_update` 도구(읽기 전용이 아니라 Claude가 사용자에게 먼저 묻는다)는 새 파일을 받아 서명된 SHA-256과 맞을 때만 다운로드 폴더에 저장한다. 확장은 `uv run --frozen --no-dev`로 의존성을 uv.lock에 고정된 버전·해시로만, 개발용 패키지 없이 설치한다. 다만 이 프로젝트 자체를 빌드하는 `uv_build`(빌드 백엔드)는 uv.lock에 들어가지 않는다. `pyproject.toml`에서 버전을 정확히 고정해 두었고, 같은 버전의 uv는 내장 백엔드를 쓰지만, 다른 버전의 uv는 그 버전을 PyPI에서 해시 확인 없이 받아 학번·비밀번호 환경변수가 있는 상태로 실행한다. 서명 단계는 `.mcpb` 안의 코드가 같은 버전 wheel과 다르면 거부한다(오래된 파일이 서명되는 것 방지).

## 에이전트 업데이트

확장이 띄운 에이전트(`--from-extension`, 확장 안의 `KW_MCP_DISTRIBUTION=mcpb`)는 스스로 wheel을 설치하지 않는다. 그 환경은 Claude 데스크톱 것이고, 새 버전은 확장과 함께 온다(위 "확장 업데이트"). 확장이 업데이트되면 돌던 에이전트는 옛 코드로 남으므로, 확장의 MCP 서버가 시작할 때 백그라운드에서 확인해 다시 띄운다: 자동 실행이 이 확장의 명령(`--from-extension` 포함) 그대로이고, 에이전트가 켜져 있고, 시작할 때 `~/.config/kw-campus/agent-state.json`에 남긴 버전이 확장 버전과 다를 때만, 그리고 버전마다 한 번만(`~/.config/kw-campus/extension-restarted`). 예전 방식으로 설치한 에이전트는 건드리지 않는다. 연결 상태는 `klas_status`의 `web_connection`에서 보고, 새 연결 알림이 오면 Claude 데스크톱에서 "연결된 앱 끊어 줘"라고 해 `disconnect_app`으로 끊는다.

예전 방식(터미널 설치 명령, `uv tool`)으로 설치한 에이전트는 전과 같이 스스로 업데이트한다. 에이전트는 시작 10분 뒤와 6시간마다(비정상 종료 뒤에는 30~60초 뒤) 연결 서버의 `/dist/latest.json`을 본다. 버전이 더 높고, Ed25519 서명이 `kw_mcp/release.py`의 공개키와 맞고, 받은 wheel과 의존성 고정 파일(constraints)이 서명된 SHA-256과 같을 때만 설치한다. 설치는 고정된 의존성 버전과 릴리스 시각 이전에 올라온 패키지만 쓰고(`--constraints`, `--exclude-newer`, `--no-build`), `uv tool install`은 고정 파일의 해시를 보지 않으므로 바로 이어서 모든 의존성을 `uv pip install --require-hashes`로 해시를 확인하며 다시 설치한다(그 전에는 새 의존성의 코드가 실행되지 않는다). 새 버전이 스스로 실행되는지(`--version` 자체 점검) 확인한 뒤에야 다시 시작한다(macOS는 launchd가, Windows는 에이전트가 끝난 뒤 별도 프로세스가 설치하고 띄움). 해시 확인이나 자체 점검에 실패하면 돌던 버전을 다시 설치해 그대로 쓴다. 바로 전 버전은 `~/.config/kw-campus/releases`에 남겨 두고, 새 버전이 연결 후 2분을 채우기 전에 두 번 멈추면(시작하다 예외가 나든, 강제로 꺼지든) 다음 시작 때 되돌리고 그 버전은 건너뛴다. 자체 점검에 실패한 버전도 다시 받지 않는다(Windows 포함). 서명 키는 릴리스하는 PC의 키체인에만 있어서, 서버만으로는 백그라운드 업데이트로 PC에 코드를 밀어 넣을 수 없다. 다만 서명은 백그라운드 업데이트만 보호한다. 예전 설치 명령과 연결 서버에서 받는 `.mcpb`는 연결 서버를 TLS로 믿는다.
