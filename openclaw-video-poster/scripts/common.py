"""Shared helpers: project paths, .env loading, JSON token files, post log."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
POST_LOG = OUTPUT_DIR / "posted.jsonl"

load_dotenv(ROOT / ".env")


def env(name: str, default: str | None = None, required: bool = True) -> str:
    value = os.getenv(name, default)
    if required and not value:
        raise SystemExit(f"Missing required setting {name} (add it to .env)")
    return value


def resolve(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def read_json(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    path.chmod(0o600)


def log_post(entry: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(), **entry}
    with POST_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def already_posted_today() -> bool:
    if not POST_LOG.exists():
        return False
    today = datetime.now(timezone.utc).date().isoformat()
    for line in POST_LOG.read_text().splitlines():
        entry = json.loads(line)
        if entry.get("at", "").startswith(today) and entry.get("ok"):
            return True
    return False
