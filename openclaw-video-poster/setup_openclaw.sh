#!/usr/bin/env bash
# Install the daily-video-post skill into OpenClaw and schedule it daily.
# Usage: ./setup_openclaw.sh [HH:MM] [Timezone]   e.g. ./setup_openclaw.sh 18:00 America/New_York
set -euo pipefail

TIME="${1:-18:00}"
TZ_NAME="${2:-$(cat /etc/timezone 2>/dev/null || echo UTC)}"
HOUR="${TIME%%:*}"; MIN="${TIME##*:}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$HOME/.openclaw/workspace/skills}"

command -v openclaw >/dev/null || {
  echo "OpenClaw not found. Install it first:"
  echo "  npm install -g openclaw@latest && openclaw onboard --install-daemon"
  exit 1
}

echo "==> Python environment"
python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/pip" install -q -r "$PROJECT_DIR/requirements.txt"
[ -f "$PROJECT_DIR/.env" ] || cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"

echo "==> Installing skill into $SKILLS_DIR/daily-video-post"
mkdir -p "$SKILLS_DIR/daily-video-post"
sed "s|{{PROJECT_DIR}}|$PROJECT_DIR|g" "$PROJECT_DIR/skills/daily-video-post/SKILL.md" \
  > "$SKILLS_DIR/daily-video-post/SKILL.md"

echo "==> Scheduling daily job at $TIME ($TZ_NAME)"
openclaw cron remove "Daily video post" >/dev/null 2>&1 || true
openclaw cron add \
  --name "Daily video post" \
  --cron "$((10#$MIN)) $((10#$HOUR)) * * *" \
  --tz "$TZ_NAME" \
  --session isolated \
  --message "Use the daily-video-post skill to make and post today's video."

openclaw cron list
cat <<MSG

Done. Remaining one-time steps:
  1. Fill in $PROJECT_DIR/.env
  2. .venv/bin/python -c 'import sys; sys.path.insert(0,"scripts"); import youtube_upload as y; y.credentials()'   (Google sign-in)
  3. .venv/bin/python scripts/tiktok_upload.py --login
  4. Test now:  openclaw cron run "Daily video post"
MSG
