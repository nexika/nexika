#!/usr/bin/env python3
"""lawha_server - the local, read-only learner dashboard for prof (stdlib only).

Commands:
  start [--open]   start the server in the background (or reuse a running one) and print its URL
  stop             stop the running server
  status           print the running server's URL, or "not running"
  serve            run in the foreground (used by start; also handy for development)

The server listens on 127.0.0.1 only, on a free port. Each run has a random token: the page gets it
in the URL fragment it is opened with (never sent over the network) and sends it back on every API
request (header X-Lawha-Token); /api/* requests without it are refused, and so is any request whose
Host header is not this server's (DNS rebinding). Nothing is ever written to prof's files.
State: ~/.claude/nexika/lawha/server.json.
"""
from __future__ import annotations

import datetime
import hmac
import json
import mimetypes
import os
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lawha_data  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent
DIST = PLUGIN / "web" / "dist"
DEMO = PLUGIN / "demo" / "prof"
DEMO_TODAY = datetime.date(2026, 10, 6)  # the demo data's dates are relative to this day
STATE = Path(os.environ.get("LAWHA_HOME") or Path.home() / ".claude" / "nexika" / "lawha")
SERVER_JSON = STATE / "server.json"
IDLE_SECONDS = int(os.environ.get("LAWHA_IDLE_SECONDS") or 2 * 3600)

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class App:
    """Everything a request needs: the token, the data folders, and a course-status cache."""

    def __init__(self, token: str, prof_home: Path, courses_home: Path, dist: Path = DIST):
        self.token = token
        self.prof_home = prof_home
        self.courses_home = courses_home
        self.dist = dist
        self.port = 0
        self.last_request = time.monotonic()
        self._course: dict | None = None
        self._lock = threading.Lock()

    def prof(self, demo: bool) -> lawha_data.Prof:
        return lawha_data.Prof(DEMO, DEMO_TODAY) if demo else lawha_data.Prof(self.prof_home)

    def course(self) -> dict:
        with self._lock:
            if self._course is None:
                self._course = lawha_data.course(self.courses_home)
            return self._course

    def api(self, path: str, demo: bool) -> tuple[int, object]:
        parts = [urllib.parse.unquote(p) for p in path.split("/") if p][1:]  # drop "api"
        prof = self.prof(demo)
        found: object | None = None
        if parts == ["summary"]:
            found = prof.summary() | {"demo": demo}
        elif parts == ["topics"]:
            found = prof.topics()
        elif len(parts) == 2 and parts[0] == "topics":
            found = prof.topic(parts[1])
        elif parts == ["sessions"]:
            found = prof.sessions()
        elif len(parts) == 2 and parts[0] == "sessions":
            found = prof.session(parts[1])
        elif parts == ["profile"]:
            found = prof.profile()
        elif parts == ["course"]:
            found = self.course()
        if found is None:
            return 404, {"error": "not found"}
        return 200, found


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "lawha"
        sys_version = ""

        def log_message(self, fmt, *args):  # quiet: no request log on the terminal
            pass

        def _send(self, status: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, data: object) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self._send(status, body, "application/json; charset=utf-8")

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in (f"127.0.0.1:{app.port}", f"localhost:{app.port}")

        def _refuse_method(self) -> None:
            self._json(405, {"error": "read-only"})

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _refuse_method

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            app.last_request = time.monotonic()
            if not self._host_ok():
                return self._json(403, {"error": "bad host"})
            url = urllib.parse.urlsplit(self.path)
            if url.path == "/api" or url.path.startswith("/api/"):
                given = self.headers.get("X-Lawha-Token") or ""
                if not hmac.compare_digest(given.encode(), app.token.encode()):
                    return self._json(403, {"error": "missing or wrong token"})
                demo = urllib.parse.parse_qs(url.query).get("demo") == ["1"]
                try:
                    status, data = app.api(url.path, demo)
                except Exception as error:  # a bad file must not take the server down
                    return self._json(500, {"error": type(error).__name__})
                return self._json(status, data)
            return self._static(url.path)

        def _static(self, path: str) -> None:
            root = app.dist.resolve()
            rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
            target = (root / rel).resolve()
            if root not in target.parents and target != root:
                return self._json(404, {"error": "not found"})
            if not target.is_file():
                if "." in Path(rel).name:  # a missing asset, not an app route
                    return self._json(404, {"error": "not found"})
                target = root / "index.html"  # app routes like /topics/git are the single page
            if not target.is_file():
                body = b"lawha: the frontend is not built (run npm run build in plugins/lawha/web)"
                return self._send(503, body, "text/plain; charset=utf-8")
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "image/svg+xml"):
                ctype += "; charset=utf-8"
            cache = "no-store" if target.name == "index.html" else "max-age=31536000, immutable"
            self._send(200, target.read_bytes(), ctype, cache)

    return Handler


# ---------------------------------------------------------------- process control

def _read_state() -> dict | None:
    try:
        return json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _alive(state: dict | None) -> bool:
    if not state:
        return False
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{state['port']}/api/summary",
                                     headers={"X-Lawha-Token": state["token"]})
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except (OSError, KeyError, ValueError):
        return False


def _url(state: dict) -> str:
    return f"http://127.0.0.1:{state['port']}/#t={state['token']}"


def serve() -> int:
    token = secrets.token_urlsafe(24)
    app = App(token, lawha_data.prof_home(), lawha_data.courses_home())
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    httpd.daemon_threads = True
    app.port = httpd.server_address[1]
    STATE.mkdir(parents=True, exist_ok=True)
    fd = os.open(SERVER_JSON, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump({"pid": os.getpid(), "port": app.port, "token": token}, fh)

    def watch_idle():
        while True:
            time.sleep(min(60, IDLE_SECONDS))
            if time.monotonic() - app.last_request > IDLE_SECONDS:
                httpd.shutdown()
                return

    threading.Thread(target=watch_idle, daemon=True).start()
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=httpd.shutdown).start())
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        state = _read_state()
        if state and state.get("pid") == os.getpid():
            SERVER_JSON.unlink(missing_ok=True)
    return 0


def start(open_browser: bool) -> int:
    state = _read_state()
    if not _alive(state):
        STATE.mkdir(parents=True, exist_ok=True)
        SERVER_JSON.unlink(missing_ok=True)
        with open(STATE / "server.log", "a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve"],
                             stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not _alive(state := _read_state()):
            time.sleep(0.1)
        if not _alive(state):
            print(f"lawha: the server did not start; see {STATE / 'server.log'}", file=sys.stderr)
            return 1
    url = _url(state)
    print(url)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    return 0


def stop() -> int:
    state = _read_state()
    if not state:
        print("lawha: not running")
        return 0
    try:
        os.kill(int(state["pid"]), signal.SIGTERM)
    except (OSError, KeyError, ValueError):
        pass
    SERVER_JSON.unlink(missing_ok=True)
    print("lawha: stopped")
    return 0


def status() -> int:
    state = _read_state()
    print(_url(state) if _alive(state) else "lawha: not running")
    return 0


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else "status"
    if command == "start":
        return start("--open" in argv[2:])
    if command == "stop":
        return stop()
    if command == "status":
        return status()
    if command == "serve":
        return serve()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
