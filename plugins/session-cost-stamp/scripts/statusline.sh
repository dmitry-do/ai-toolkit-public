#!/bin/sh
# session-cost-stamp — statusLine command (REQUIRED companion to the hook).
#
# Renders "<dir>  <branch>  •  N% context  •  $X.XX" AND writes the per-session
# stash that the SessionEnd hook (stamp-session-cost.sh) reads. The statusLine
# is the only Claude Code surface that receives cost/context, so this stash is
# the bridge that makes the hook work.
#
# Greenfield setup — copy this file to ~/.claude/ and point your statusLine at it
# in ~/.claude/settings.json:
#   "statusLine": { "type": "command", "command": "bash ~/.claude/statusline.sh" }
#
# Already have a statusLine? Don't replace it — copy the "STASH" block below
# into your own script instead (that's the only part this plugin needs).

input=$(cat)

# --- Working directory (basename; ~ for home) ------------------------------
cwd=$(printf '%s' "$input" | jq -r '.workspace.current_dir // .cwd // ""')
if [ "$cwd" = "$HOME" ]; then short="~"; else short=$(basename "$cwd"); fi

# --- Git branch (works inside worktrees) -----------------------------------
branch=""
[ -n "$cwd" ] && branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null \
  || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)

# --- Pre-calculated fields from the statusLine payload ---------------------
used_pct=$(printf '%s' "$input" | jq -r '.context_window.used_percentage // empty')
cost_raw=$(printf '%s' "$input" | jq -r '.cost.total_cost_usd // empty')

# --- STASH (required by session-cost-stamp's SessionEnd hook) --------------
# Writes ~/.claude/session-stats/<session_id> = used_pct / cost / duration_ms.
sid=$(printf '%s' "$input" | jq -r '.session_id // empty')
dur_ms=$(printf '%s' "$input" | jq -r '.cost.total_duration_ms // empty')
if [ -n "$sid" ]; then
  mkdir -p "$HOME/.claude/session-stats" 2>/dev/null
  printf '%s\n%s\n%s\n' "${used_pct:-}" "${cost_raw:-}" "${dur_ms:-}" \
    > "$HOME/.claude/session-stats/$sid" 2>/dev/null
fi
# --- end STASH -------------------------------------------------------------

# --- Render ----------------------------------------------------------------
out="$short"
[ -n "$branch" ] && out="$out  $branch"
[ -n "$used_pct" ] && out="$out  •  $(printf '%.0f' "$used_pct")% context"
[ -n "$cost_raw" ] && out="$out  •  \$$(printf '%.2f' "$cost_raw")"
printf '%s' "$out"
