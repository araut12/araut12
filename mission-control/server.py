"""Mission Control: a small dashboard for OpenClaw agents and the video poster.

Run on the same machine as OpenClaw:
    MC_TOKEN=choose-a-password python3 server.py
Open http://localhost:8787 and use Tailscale to reach it from anywhere (see README).
Uses only the Python standard library.
"""
import hmac
import json
import os
import shlex
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
PORT = int(os.getenv("MC_PORT", "8787"))
HOST = os.getenv("MC_HOST", "127.0.0.1")
TOKEN = os.getenv("MC_TOKEN", "")
POST_LOG = Path(os.getenv("MC_POST_LOG", HERE.parent / "openclaw-video-poster/output/posted.jsonl"))

# Panels: title -> command. Edit to add your own agents.
PANELS = {
    "Gateway status": "openclaw status",
    "Scheduled jobs": "openclaw cron list",
}


def run(cmd: str, timeout: int = 20) -> dict:
    try:
        p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "output": (p.stdout + p.stderr).strip()}
    except FileNotFoundError:
        return {"ok": False, "output": f"Command not found: {cmd.split()[0]}"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "output": f"Timed out after {timeout}s"}


def cron_jobs() -> list[dict]:
    """Job list from `openclaw cron list --json`, or [] if that isn't supported."""
    r = run("openclaw cron list --json")
    try:
        data = json.loads(r["output"])
    except (json.JSONDecodeError, TypeError):
        return []
    jobs = data.get("jobs", data) if isinstance(data, dict) else data
    return jobs if isinstance(jobs, list) else []


def recent_posts(n: int = 20) -> list[dict]:
    if not POST_LOG.exists():
        return []
    lines = POST_LOG.read_text().splitlines()[-n:]
    return [json.loads(l) for l in reversed(lines) if l.strip()]


class Handler(BaseHTTPRequestHandler):
    def authed(self) -> bool:
        if not TOKEN:
            return True
        cookie = self.headers.get("Cookie", "")
        given = dict(c.strip().split("=", 1) for c in cookie.split(";") if "=" in c).get("mc_token", "")
        return hmac.compare_digest(given, TOKEN)

    def send(self, code: int, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        if not self.authed():
            return self.send(401, {"error": "login required"})
        if path == "/api/state":
            return self.send(200, {
                "panels": {title: run(cmd) for title, cmd in PANELS.items()},
                "jobs": cron_jobs(),
                "posts": recent_posts(),
            })
        self.send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = parse_qs(self.rfile.read(length).decode()) if length else {}
        if path == "/api/login":
            if TOKEN and hmac.compare_digest(body.get("token", [""])[0], TOKEN):
                self.send_response(204)
                self.send_header("Set-Cookie", f"mc_token={TOKEN}; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000")
                return self.end_headers()
            return self.send(401, {"error": "wrong password"})
        if not self.authed():
            return self.send(401, {"error": "login required"})
        if path == "/api/run":
            job = body.get("job", [""])[0]
            if not job or job not in {j.get("name") for j in cron_jobs()} | {j.get("id") for j in cron_jobs()}:
                return self.send(400, {"error": "unknown job"})
            return self.send(200, run(f"openclaw cron run {shlex.quote(job)}", timeout=60))
        self.send(404, {"error": "not found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    if not TOKEN:
        print("WARNING: MC_TOKEN not set; anyone who can reach this port has full access.")
    print(f"Mission Control on http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
