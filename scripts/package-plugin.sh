#!/usr/bin/env bash
#
# package-plugin.sh — zip a plugin for upload to claude.ai.
#
# The zip is the whole plugins/<name>/ folder with .claude-plugin/plugin.json at
# the zip root, so claude.ai gets the same plugin that Claude Code installs from
# the marketplace. Each plugin's skills degrade on their own where claude.ai
# lacks something (no local files, no subagents, an MCP server that isn't
# connected), so nothing is stripped here. Writes dist/<name>-<version>.zip for:
#   claude.ai -> Customize -> Plugins -> Upload a plugin
#
# Usage: scripts/package-plugin.sh <plugin-name>...
#        scripts/package-plugin.sh --all
set -euo pipefail

# Plugins that only do anything inside Claude Code on the user's machine.
LOCAL_ONLY="chop-chop session-cost-stamp"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ $# -gt 0 ] || { echo "usage: package-plugin.sh <plugin-name>... | --all" >&2; exit 1; }

if [ "$1" = "--all" ]; then
  set --
  for d in "$ROOT"/plugins/*/; do
    n="$(basename "$d")"
    case " $LOCAL_ONLY " in *" $n "*) continue ;; esac
    [ -f "$d/.claude-plugin/plugin.json" ] && set -- "$@" "$n"
  done
fi

mkdir -p "$ROOT/dist"
for NAME in "$@"; do
  DIR="$ROOT/plugins/$NAME"
  case " $LOCAL_ONLY " in
    *" $NAME "*) echo "error: $NAME is Claude Code only, there is nothing for it to do on claude.ai" >&2; exit 1 ;;
  esac
  if [ ! -f "$DIR/.claude-plugin/plugin.json" ]; then
    echo "error: no plugins/$NAME/.claude-plugin/plugin.json — is '$NAME' a plugin?" >&2
    exit 1
  fi
  if command -v claude >/dev/null 2>&1; then
    claude plugin validate "$DIR" >/dev/null || { echo "error: $NAME failed 'claude plugin validate'" >&2; exit 1; }
  fi
  VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$DIR/.claude-plugin/plugin.json")"
  OUT="$ROOT/dist/$NAME-$VERSION.zip"
  rm -f "$OUT"
  ( cd "$DIR" && zip -rq "$OUT" . -x '.DS_Store' '*/.DS_Store' '*/__pycache__/*' '*.pyc' )
  echo "wrote ${OUT#"$ROOT"/}"
done
echo "upload at: claude.ai -> Customize -> Plugins -> Upload a plugin"
