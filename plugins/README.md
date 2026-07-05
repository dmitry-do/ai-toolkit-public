# Plugins

Every plugin in the [ai-toolkit-public](../README.md) marketplace lives here, one directory each. A
directory holds `.claude-plugin/plugin.json` and a `skills/<name>/SKILL.md`. Click any plugin below
for its own README.

| Plugin | What it does | Source |
| --- | --- | --- |
| 🎙️ [`audio-transcription`](./audio-transcription) | `wav`/`mp3`/`m4a` → timestamped Markdown with Whisper (`mlx-whisper` on Apple Silicon, `openai-whisper` elsewhere). | Mine |
| 📝 [`meeting-notes`](./meeting-notes) | Raw transcripts in `rec/` → readable meeting summaries, one isolated subagent per transcript. | Mine |

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
  skills/<name>/SKILL.md        # the skill itself
  skills/<name>/scripts/        # bundled scripts (audio-transcription)
```

See the root [LICENSE](../LICENSE).
