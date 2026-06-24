#!/usr/bin/env bash
#
# package-skill.sh — zip a plugin's skill folder for upload to Claude Web.
#
# A Claude Web skill is just the skills/<name>/ folder with SKILL.md at the zip
# root. This produces dist/<name>-skill.zip ready for:
#   claude.ai -> Customize -> Skills -> Add -> Create skill -> Upload a skill
#
# Usage: scripts/package-skill.sh <plugin-name>
set -euo pipefail

NAME="${1:?usage: package-skill.sh <plugin-name>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILL_DIR="$ROOT/plugins/$NAME/skills/$NAME"

if [ ! -f "$SKILL_DIR/SKILL.md" ]; then
  echo "error: no SKILL.md at plugins/$NAME/skills/$NAME — is '$NAME' a plugin?" >&2
  exit 1
fi

mkdir -p "$ROOT/dist"
OUT="$ROOT/dist/$NAME-skill.zip"
rm -f "$OUT"
# zip from skills/ so the archive contains <name>/SKILL.md (SKILL.md at folder root).
( cd "$ROOT/plugins/$NAME/skills" && zip -rq "$OUT" "$NAME" -x '*/.DS_Store' '*/__pycache__/*' '*.pyc' )
echo "wrote ${OUT#"$ROOT"/}"
echo "upload it at: claude.ai -> Customize -> Skills -> Add -> Create skill -> Upload a skill"
