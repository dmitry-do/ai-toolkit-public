# Plugins

Every plugin in the [ai-toolkit-public](../README.md) marketplace lives here, one directory each. A
directory holds `.claude-plugin/plugin.json` and usually a `skills/<name>/SKILL.md` (hook-only
plugins like `session-cost-stamp` skip it). Click any plugin below for its own README.

| Plugin | What it does | Source |
| --- | --- | --- |
| 🎙️ [`audio-transcription`](./audio-transcription) | `wav`/`mp3`/`m4a` → timestamped Markdown with Whisper (`mlx-whisper` on Apple Silicon, `openai-whisper` elsewhere). | Mine |
| 📝 [`meeting-notes`](./meeting-notes) | Raw transcripts in `rec/` → readable meeting summaries, one isolated subagent per transcript. | Mine |
| 🧾 [`session-cost-stamp`](./session-cost-stamp) | At session end, stamps worked-time, context %, and cost into the transcript as the session title (shows on `--resume`, persists in the file). Requires a statusLine that writes the stash. | Mine |
| 🗺️ [`trip-plan`](./trip-plan) | Itineraries sequenced around opening hours, travel time and anchors → self-contained HTML + installable PWA. Blocks the build on booking codes or personal data. | Mine |

## Install

From inside Claude Code:

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install <plugin-name>@ai-toolkit-public
```

## Layout

```
plugins/<name>/
  .claude-plugin/plugin.json   # manifest (name, version, description, author)
  skills/<name>/SKILL.md        # the skill itself (absent in hook-only plugins)
  skills/<name>/scripts/        # bundled scripts (audio-transcription, trip-plan)
  skills/<name>/reference/       # reference docs (trip-plan)
  hooks/hooks.json               # lifecycle hooks (session-cost-stamp)
  scripts/                       # hook + statusline scripts (session-cost-stamp)
```

See the root [LICENSE](../LICENSE).
