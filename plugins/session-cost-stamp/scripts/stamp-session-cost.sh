#!/bin/sh
# session-cost-stamp — SessionEnd hook.
#
# Stamps the session's final stats (worked / context% / cost) into the
# transcript as a native `ai-title` entry — the same {type,aiTitle,sessionId}
# shape Claude Code itself appends, so it can't confuse the JSONL parser and
# becomes the session's effective title (visible on resume, kept in the file).
#
# SessionEnd's own stdin carries NO cost/context — those live only in the
# statusLine payload. So this consumes a per-session stash written by the
# statusLine (see scripts/statusline.sh or the README snippet). No stash =>
# nothing to stamp => this exits quietly. The statusLine wiring is required.

input=$(cat)

sid=$(printf '%s' "$input" | jq -r '.session_id // empty')
transcript=$(printf '%s' "$input" | jq -r '.transcript_path // empty')

[ -n "$sid" ] || exit 0
[ -n "$transcript" ] || exit 0
[ -f "$transcript" ] || exit 0

stash="$HOME/.claude/session-stats/$sid"
[ -f "$stash" ] || exit 0

# stash = three lines: used_percentage, total_cost_usd, total_duration_ms
{ read -r used_pct; read -r cost_raw; read -r dur_ms; } < "$stash"

# --- Format each piece, skipping any that are missing ---------------------
worked=""
case "$dur_ms" in
  ''|*[!0-9]*) ;;                      # empty or non-numeric -> skip
  *)
    total_s=$(( dur_ms / 1000 ))
    mm=$(( total_s / 60 ))
    ss=$(( total_s % 60 ))
    if [ "$mm" -gt 0 ]; then worked="worked ${mm}m ${ss}s"; else worked="worked ${ss}s"; fi
    ;;
esac

ctx=""
[ -n "$used_pct" ] && ctx=$(printf 'context: %.0f%%' "$used_pct" 2>/dev/null)

cost=""
[ -n "$cost_raw" ] && cost=$(printf 'cost: $%.2f' "$cost_raw" 2>/dev/null)

parts=""
for p in "$worked" "$ctx" "$cost"; do
  [ -n "$p" ] || continue
  if [ -z "$parts" ]; then parts="$p"; else parts="$parts, $p"; fi
done

# Nothing to stamp -> clean up and bail.
[ -n "$parts" ] || { rm -f "$stash"; exit 0; }

# --- Build the new title from the current one -----------------------------
last_title=$(jq -rc 'select(.type=="ai-title") | .aiTitle' "$transcript" 2>/dev/null | tail -1)
# Strip a prior stamp so re-runs replace it instead of compounding.
base_title=$(printf '%s' "$last_title" | sed -E 's/[[:space:]]*\((worked|context:|cost:)[^)]*\)$//')

if [ -n "$base_title" ]; then
  new_title="${base_title} (${parts})"
else
  new_title="(${parts})"
fi

# Append a native ai-title entry (jq handles JSON string escaping).
jq -cn --arg t "$new_title" --arg sid "$sid" \
  '{type:"ai-title", aiTitle:$t, sessionId:$sid}' >> "$transcript"

rm -f "$stash"
