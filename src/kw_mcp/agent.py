"""PC agent for the KW Campus bridge: Claude/ChatGPT connectors read KLAS through this PC.

  kw-mcp link <invite>   once: register this PC (public key only) and start the agent at login
  kw-mcp agent           keep a WebSocket open to the bridge; when a connector asks, read KLAS with
                         the keychain login (logging in again when the session has expired),
                         encrypt the result with that request's one-time key and post it back

The KLAS id/password and the device's private key stay in the OS keychain. The bridge only
gets the device's public key and per-request ciphertext.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import logging.handlers
import os
import plistlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import keyring
import websockets
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from keyring.errors import KeyringError, PasswordDeleteError

from . import credentials, release
from .holder import KlasHolder
from .klas import KlasError, KlasLoginBlocked, KlasLoginError

log = logging.getLogger("kw_mcp.agent")

CONFIG_DIR = Path.home() / ".config" / "kw-campus"
LINK_FILE = CONFIG_DIR / "agent.json"
KEYRING_DEVICE_KEY = "bridge_device_key"
INVITE_PREFIX = "kwc_"
APP_PING_S = 300  # API Gateway closes WebSocket connections that are idle for 10 minutes
MAX_BACKOFF_S = 60.0
DENIED_BACKOFF_S = 600.0  # the bridge refused this PC (unlinked, clock far off): don't hammer it
LOCK_PORT = 47811  # one agent per user: the running agent holds this localhost port
LAUNCHD_LABEL = "kr.kwcampus.agent"
WINDOWS_RUN_VALUE = "KWCampusAgent"
# Sent on connect so the bridge knows which requests this agent understands.
# 1: "snapshot" only. 2: also "call" with an op from CALLS.
PROTOCOL_VERSION = 2
# Single-item reads the bridge may ask for: op -> argument names. Each op is a read-only
# KlasService method taking those arguments as strings.
CALLS: dict[str, tuple[str, ...]] = {
    "assignment_detail": ("course", "title"),
    "syllabus": ("course",),
    "course_post": ("course", "title"),
    "search_course_posts": ("course", "keyword"),
    "grades": (),
    "read_attachment": ("course", "title", "file_name", "part", "source"),
    "attendance": ("course",),
    "exam_info": ("course",),
    "class_changes": ("days",),
    "graduation_progress": (),
    "deadlines": ("days",),
    "online_tests": ("course",),
    "surveys": ("course",),
    "discussions": ("course",),
    "course_evaluation": (),
    "application_windows": (),
}
MAX_ARG_CHARS = 100
MAX_RESULT_CHARS = 300_000  # same cap as the bridge's /device/result
# Self-update: check the bridge's signed latest.json soon after start, then every few hours.
UPDATE_FIRST_CHECK_S = 600
UPDATE_INTERVAL_S = 6 * 3600
RESTART_EXIT_CODE = 75  # non-zero, so launchd (KeepAlive SuccessfulExit=false) starts the new version


class NotLinked(RuntimeError):
    pass


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- invite, link file, device key ---------------------------------------------------

def make_invite(server: str, token: str) -> str:
    return INVITE_PREFIX + b64u(json.dumps({"s": server.rstrip("/"), "t": token}, separators=(",", ":")).encode())


def parse_invite(invite: str) -> tuple[str, str]:
    invite = invite.strip()
    try:
        if not invite.startswith(INVITE_PREFIX):
            raise ValueError
        data = json.loads(b64u_decode(invite[len(INVITE_PREFIX):]))
        server, token = str(data["s"]).rstrip("/"), str(data["t"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("초대 코드 형식이 아닙니다(kwc_로 시작하는 코드를 그대로 붙여 넣으세요).") from None
    parsed = urlparse(server)
    if not (parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1"))) \
            or parsed.username or parsed.path not in ("", "/"):
        raise ValueError("초대 코드 안의 서버 주소가 올바르지 않습니다.")
    return server, token


@dataclass(frozen=True)
class Link:
    server: str
    ws_url: str
    uid: str


def save_link(link: Link) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    LINK_FILE.write_text(json.dumps(asdict(link), indent=2))
    LINK_FILE.chmod(0o600)


def load_link() -> Link:
    try:
        return Link(**json.loads(LINK_FILE.read_text()))
    except (OSError, ValueError, TypeError):
        raise NotLinked("이 PC가 아직 연결되지 않았습니다. `kw-mcp link <초대코드>`를 먼저 실행하세요.") from None


class DeviceKey:
    """ECDSA P-256 key; signatures are raw r||s like WebCrypto, which the bridge verifies."""

    def __init__(self, key: ec.EllipticCurvePrivateKey) -> None:
        self._key = key

    @classmethod
    def generate(cls) -> DeviceKey:
        return cls(ec.generate_private_key(ec.SECP256R1()))

    @classmethod
    def load(cls) -> DeviceKey:
        pem = keyring.get_password(credentials.KEYRING_SERVICE, KEYRING_DEVICE_KEY)
        if not pem:
            raise NotLinked("키체인에 기기 키가 없습니다. `kw-mcp link <초대코드>`를 다시 실행하세요.")
        key = serialization.load_pem_private_key(pem.encode(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise NotLinked("키체인의 기기 키 형식이 올바르지 않습니다. `kw-mcp link`를 다시 실행하세요.")
        return cls(key)

    def save(self) -> None:
        pem = self._key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()).decode()
        keyring.set_password(credentials.KEYRING_SERVICE, KEYRING_DEVICE_KEY, pem)

    def public_jwk(self) -> dict[str, str]:
        nums = self._key.public_key().public_numbers()
        return {"kty": "EC", "crv": "P-256", "x": b64u(nums.x.to_bytes(32, "big")), "y": b64u(nums.y.to_bytes(32, "big"))}

    def sign(self, message: str) -> str:
        r, s = decode_dss_signature(self._key.sign(message.encode(), ec.ECDSA(hashes.SHA256())))
        return b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))

    def signed(self, uid: str, purpose: str) -> dict[str, str]:
        ts = str(int(time.time()))
        return {"uid": uid, "ts": ts, "sig": self.sign(f"kw-{purpose}:{uid}:{ts}")}


def _delete_device_key() -> None:
    try:
        keyring.delete_password(credentials.KEYRING_SERVICE, KEYRING_DEVICE_KEY)
    except PasswordDeleteError:
        pass


# --- talking to the bridge (one-off calls) ----------------------------------------------

def register(invite: str, expected_server: str | None = None) -> tuple[Link, str]:
    """Register this PC with a fresh key. Returns the link and the connector (MCP) URL.

    The installer passes the server it was downloaded from as expected_server, so a doctored
    invite can't point this PC at someone else's bridge.
    """
    server, token = parse_invite(invite)
    if expected_server and server != expected_server.rstrip("/"):
        raise ValueError(f"초대 코드의 서버({server})가 설치한 곳({expected_server})과 다릅니다. 받은 링크를 다시 확인하세요.")
    key = DeviceKey.generate()
    # Register first: if the network or the bridge fails here, the current link stays as it was.
    r = httpx.post(f"{server}/device/register", json={"invite": token, "public_key": key.public_jwk()}, timeout=20)
    if r.status_code == 403:
        raise ValueError("초대 코드가 유효하지 않습니다. 받은 코드를 다시 확인하세요.")
    r.raise_for_status()
    data = r.json()
    _forget_previous_device()
    key.save()
    link = Link(server=server, ws_url=data["ws_url"], uid=data["uid"])
    save_link(link)
    return link, data["mcp_url"]


def _forget_previous_device() -> None:
    """Best effort: ask the bridge to drop this PC's previous device after a new one registered."""
    try:
        old, old_key = load_link(), DeviceKey.load()
        httpx.post(f"{old.server}/device/unlink", json=old_key.signed(old.uid, "unlink"), timeout=20)
    except (NotLinked, httpx.HTTPError, KeyringError, ValueError):
        pass


def linked_to(server: str) -> bool:
    """True if this PC is already registered with `server` and the bridge still knows it.

    Only "not linked here" or "the bridge doesn't know this device" count as False; a network
    error is raised, so a flaky connection during an update never triggers a re-registration.
    """
    try:
        link = load_link()
        if link.server != server.rstrip("/"):
            return False
        pair_code()  # signed request: NotLinked (403) if the device was removed on the bridge
        return True
    except NotLinked:
        return False


def pair_code() -> dict[str, Any]:
    """A one-time code (15 minutes) to type on the connector's approval page."""
    link, key = load_link(), DeviceKey.load()
    r = httpx.post(f"{link.server}/device/pair", json=key.signed(link.uid, "pair"), timeout=20)
    if r.status_code == 403:
        raise NotLinked("중계 서버가 이 PC를 알아보지 못했습니다. `kw-mcp link <초대코드>`를 다시 실행하세요.")
    r.raise_for_status()
    return r.json()


def unlink(*, quiet: bool = False) -> None:
    """Forget this PC on the bridge (its connectors stop working) and remove local state."""
    link = load_link()
    try:
        key = DeviceKey.load()
        httpx.post(f"{link.server}/device/unlink", json=key.signed(link.uid, "unlink"), timeout=20)
    except (NotLinked, httpx.HTTPError):
        if not quiet:
            log.warning("could not reach the bridge to unlink; removing local state anyway")
    uninstall_autostart()
    _delete_device_key()
    LINK_FILE.unlink(missing_ok=True)


# --- answering requests -------------------------------------------------------------

async def build_result(klas: KlasHolder, op: str | None = None, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """The snapshot (op None) or one CALLS read, as a dict the bridge decrypts; errors as {"error": code}."""
    try:
        service = await klas.service()
        if op is None:
            return await service.snapshot()
        names = CALLS.get(op)
        if names is None or not hasattr(service, op):
            return {"error": "unsupported", "message": f"이 에이전트는 '{op}' 요청을 모릅니다."}
        clean = {n: str((args or {}).get(n) or "")[:MAX_ARG_CHARS] for n in names}
        return {"result": await getattr(service, op)(**clean)}
    except LookupError as e:
        return {"error": "not_found", "message": str(e)}
    except (credentials.MissingCredentials, KeyringError) as e:
        return {"error": "klas_login_required", "message": str(e)}
    except KlasLoginBlocked as e:
        return {"error": "klas_blocked", "message": str(e)}
    except KlasLoginError as e:
        return {"error": "klas_login_required", "message": str(e)}
    except (KlasError, httpx.HTTPError) as e:
        log.warning("KLAS read failed: %s", e.__class__.__name__)
        return {"error": "klas_error"}
    except Exception:  # always answer: otherwise the connector waits out its timeout and blames sleep
        log.exception("unexpected error while answering %s", op or "snapshot")
        return {"error": "klas_error", "message": "PC 에이전트에서 예상하지 못한 오류가 났습니다."}


def encrypt_result(key: bytes, request_id: str, data: dict[str, Any]) -> dict[str, str]:
    """AES-256-GCM with the request id as associated data (the bridge checks both)."""
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, json.dumps(data, ensure_ascii=False).encode(), request_id.encode())
    return {"request_id": request_id, "iv": b64u(iv), "ct": b64u(ct)}


async def answer(klas: KlasHolder, link: Link, message: dict[str, Any], http: httpx.AsyncClient) -> None:
    request_id, result_url = str(message.get("request_id", "")), str(message.get("result_url", ""))
    if not request_id or result_url != f"{link.server}/device/result":
        log.warning("ignored a request with an unexpected result address")
        return
    try:
        key = b64u_decode(str(message.get("key", "")))
        if len(key) != 32:
            raise ValueError
    except ValueError:
        log.warning("ignored a request without a valid key")
        return
    started = time.monotonic()
    op = str(message["op"]) if message.get("type") == "call" else None
    data = await build_result(klas, op, message.get("args") if isinstance(message.get("args"), dict) else None)
    body = encrypt_result(key, request_id, data)
    if len(body["ct"]) > MAX_RESULT_CHARS:  # the bridge would refuse it; say why instead of timing out
        data = {"error": "too_large", "message": "결과가 너무 큽니다. 과목이나 기간을 좁혀서 다시 물어보세요."}
        body = encrypt_result(key, request_id, data)
    r = await http.post(result_url, json=body)
    log.info("answered a %s request in %.1fs (%s, HTTP %s)", op or "snapshot", time.monotonic() - started,
             data.get("error", "ok"), r.status_code)


# --- the long-running agent -------------------------------------------------------------

def _connect_url(link: Link, key: DeviceKey) -> str:
    return f"{link.ws_url}?{urlencode({**key.signed(link.uid, 'connect'), 'v': PROTOCOL_VERSION})}"


async def _serve(ws: Any, klas: KlasHolder, link: Link, http: httpx.AsyncClient) -> None:
    tasks: set[asyncio.Task[None]] = set()

    async def keep_alive() -> None:
        while True:
            await asyncio.sleep(APP_PING_S)
            await ws.send('{"action":"ping"}')

    async def safe_answer(message: dict[str, Any]) -> None:
        try:
            await answer(klas, link, message, http)
        except Exception:  # one bad request must not take the agent down
            log.exception("failed to answer a request")

    pinger = asyncio.create_task(keep_alive())
    try:
        async for raw in ws:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("type") == "paired":
                log.info("a new app was connected with this PC's code: %s (%s)",
                         str(message.get("client_name", ""))[:100], str(message.get("redirect_host", ""))[:100])
            elif isinstance(message, dict) and message.get("type") in ("snapshot", "call"):
                task = asyncio.create_task(safe_answer(message))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
    finally:
        pinger.cancel()


async def run_forever() -> None:
    link, key = load_link(), DeviceKey.load()
    klas = KlasHolder()
    backoff = 1.0
    async with httpx.AsyncClient(timeout=20) as http:
        try:
            while True:
                try:
                    async with websockets.connect(_connect_url(link, key), open_timeout=20, ping_interval=30,
                                                  ping_timeout=20, max_size=2**20) as ws:
                        log.info("connected to the bridge")
                        backoff = 1.0
                        await _serve(ws, klas, link, http)
                    log.info("bridge closed the connection")
                except websockets.InvalidStatus as e:
                    status = e.response.status_code
                    if status in (401, 403):
                        log.error("the bridge refused this PC (HTTP %s). Check that the PC clock is right "
                                  "(more than 5 minutes off is refused); if this PC was unlinked, run `kw-mcp link` again",
                                  status)
                        await asyncio.sleep(DENIED_BACKOFF_S)
                        continue
                    log.warning("bridge answered HTTP %s", status)
                except (OSError, TimeoutError, websockets.WebSocketException) as e:
                    log.warning("connection lost (%s)", e.__class__.__name__)
                except Exception:  # keep running whatever happens; this is a background service
                    log.exception("unexpected error in the connection loop")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_S)
        finally:
            await klas.aclose()


# --- self-update -----------------------------------------------------------------------

def installed_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("kw-mcp")
    except PackageNotFoundError:
        return "0"


def find_uv() -> str | None:
    """uv is on PATH in a terminal, but launchd and the Run key start us with a bare PATH."""
    exe = "uv.exe" if os.name == "nt" else "uv"
    for candidate in (shutil.which("uv"), Path.home() / ".local" / "bin" / exe, Path.home() / ".cargo" / "bin" / exe):
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


async def fetch_update(http: httpx.AsyncClient, server: str) -> tuple[dict[str, Any], Path] | None:
    """Download a newer release if the bridge offers one signed by the release key."""
    r = await http.get(f"{server}/dist/latest.json")
    if r.status_code != 200:
        return None
    manifest = r.json()
    if not release.verify(manifest):
        log.warning("ignored an update whose signature does not match the release key")
        return None
    if release.version_tuple(manifest["version"]) <= release.version_tuple(installed_version()):
        return None
    wheel = await http.get(f"{server}/dist/{manifest['wheel']}")
    if wheel.status_code != 200 or hashlib.sha256(wheel.content).hexdigest() != manifest["sha256"]:
        log.warning("ignored an update whose download does not match the signed hash")
        return None
    path = Path(tempfile.mkdtemp(prefix="kw-campus-update-")) / manifest["wheel"]
    path.write_bytes(wheel.content)
    return manifest, path


def windows_update_command(shell: str, uv: str, spec: str, log_file: Path, restart: list[str]) -> str:
    """One command line for CreateProcess, as is. A list would be re-quoted with \\" escapes that
    cmd.exe doesn't understand; /s /c "..." runs the inner line verbatim. `timeout` needs a console
    and fails at once in a windowless process, so ping does the waiting."""
    steps = (f'ping -n 8 127.0.0.1 >nul & "{uv}" tool install --force --quiet --python 3.13 "{spec}" '
             f'>> "{log_file}" 2>&1 & {subprocess.list2cmdline(restart)}')
    return f'"{shell}" /s /c "{steps}"'


def install_update(wheel: Path) -> bool:
    """Install the verified wheel. True means: exit now so the new version starts."""
    uv = find_uv()
    if not uv:
        log.warning("uv not found; skipping the update")
        return False
    wheel = wheel.resolve()  # a file:// URI needs an absolute path
    spec = f"kw-mcp @ {wheel.as_uri()}"
    if os.name == "nt":
        # Windows can't replace the interpreter that is running us: a detached shell waits for us to
        # exit, installs, then starts the agent again.
        command = windows_update_command(os.environ.get("ComSpec", "cmd.exe"), uv, spec,
                                         default_log_file().with_name("update.log"),
                                         [*agent_command(), "--replace"])
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen(command, creationflags=flags, close_fds=True)
        return True
    done = subprocess.run([uv, "tool", "install", "--force", "--quiet", "--python", "3.13", spec],
                          capture_output=True, text=True, timeout=900)
    shutil.rmtree(wheel.parent, ignore_errors=True)
    if done.returncode != 0:
        log.warning("installing the update failed: %s", done.stderr.strip()[-300:])
        return False
    return True


async def update_loop(server: str) -> None:
    """Returns once a newer signed version is installed (the caller then exits to restart)."""
    await asyncio.sleep(UPDATE_FIRST_CHECK_S)
    async with httpx.AsyncClient(timeout=120) as http:
        while True:
            try:
                before = installed_version()
                found = await fetch_update(http, server)
                if found and await asyncio.to_thread(install_update, found[1]):
                    log.info("updated %s -> %s; restarting", before, found[0]["version"])
                    return
            except Exception:  # never let the updater take the agent down
                log.exception("update check failed")
            await asyncio.sleep(UPDATE_INTERVAL_S)


class AlreadyRunning(RuntimeError):
    pass


def single_instance(replace: bool = False) -> socket.socket:
    """Hold the lock port; with replace=True, ask a running agent to exit first."""
    deadline = time.monotonic() + 10
    asked = False
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", LOCK_PORT))
            sock.listen(1)
            return sock
        except OSError:
            sock.close()
        if not replace or time.monotonic() > deadline:
            raise AlreadyRunning("에이전트가 이미 실행 중입니다.")
        if not asked:
            try:
                with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=2) as other:
                    other.sendall(b"exit\n")
                asked = True
            except OSError:
                pass
        time.sleep(0.5)


async def _watch_lock(sock: socket.socket) -> None:
    """Exit when another agent asks (re-link on Windows starts a new one)."""
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    while True:
        conn, _ = await loop.sock_accept(sock)
        try:
            with conn:
                data = await asyncio.wait_for(loop.sock_recv(conn, 16), 2)
        except (TimeoutError, OSError):
            continue  # `kw-mcp status` only checks that the port is taken
        if data.strip() == b"exit":
            log.info("replaced by a newer agent; exiting")
            return


async def main(replace: bool = False) -> int:
    """Run until replaced (0) or updated (RESTART_EXIT_CODE)."""
    lock = single_instance(replace)
    try:
        server = load_link().server
        runner = asyncio.create_task(run_forever())
        watcher = asyncio.create_task(_watch_lock(lock))
        updater = asyncio.create_task(update_loop(server))
        done, pending = await asyncio.wait({runner, watcher, updater}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            task.result()
        return RESTART_EXIT_CODE if updater in done else 0
    finally:
        lock.close()


def configure_logging(log_file: str | None) -> None:
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=512_000, backupCount=2,
                                                                        encoding="utf-8")
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for noisy in ("httpx", "httpcore", "websockets"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# --- start at login ---------------------------------------------------------------------

def default_log_file() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Logs" / "kw-campus-agent.log"
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "kw-campus" / "agent.log"
    return CONFIG_DIR / "agent.log"


def agent_command() -> list[str]:
    python = Path(sys.executable)
    if os.name == "nt" and python.with_name("pythonw.exe").exists():
        python = python.with_name("pythonw.exe")  # no console window
    return [str(python), "-m", "kw_mcp", "agent", "--log-file", str(default_log_file())]


def launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


def launchd_plist() -> bytes:
    return plistlib.dumps({
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": agent_command(),
        "RunAtLoad": True,
        # Restart after a crash; a clean exit (another agent already running) stays down.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 30,
        "ProcessType": "Background",
    })


def install_autostart() -> str:
    """Start the agent now and at every login. Returns a short description of what was set up."""
    if sys.platform == "darwin":
        path, domain = launchd_plist_path(), f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", f"{domain}/{LAUNCHD_LABEL}"], capture_output=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(launchd_plist())
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True, capture_output=True)
        return f"로그인 항목(launchd): {path}"
    if os.name == "nt":
        import winreg

        # CreateKeyEx opens the Run key, or creates it on profiles that don't have one yet.
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as run_key:
            winreg.SetValueEx(run_key, WINDOWS_RUN_VALUE, 0, winreg.REG_SZ, subprocess.list2cmdline(agent_command()))
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        subprocess.Popen([*agent_command(), "--replace"], creationflags=flags, close_fds=True)
        return "Windows 시작 프로그램(HKCU\\...\\Run)"
    raise NotImplementedError("자동 실행은 macOS와 Windows만 지원합니다. `kw-mcp agent`를 직접 실행해 두세요.")


def uninstall_autostart() -> None:
    if sys.platform == "darwin":
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCHD_LABEL}"], capture_output=True)
        launchd_plist_path().unlink(missing_ok=True)
    elif os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                                winreg.KEY_SET_VALUE) as run_key:
                winreg.DeleteValue(run_key, WINDOWS_RUN_VALUE)
        except OSError:
            pass
    try:
        with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=2) as other:
            other.sendall(b"exit\n")
    except OSError:
        pass


def autostart_installed() -> bool:
    if sys.platform == "darwin":
        return launchd_plist_path().exists()
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as run_key:
                winreg.QueryValueEx(run_key, WINDOWS_RUN_VALUE)
            return True
        except OSError:
            return False
    return False


def agent_running() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=1):
            return True
    except OSError:
        return False
