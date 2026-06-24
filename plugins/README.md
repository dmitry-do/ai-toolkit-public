# Plugins

Every plugin in the [ai-toolkit-public](../README.md) marketplace lives here, one directory each. A
directory holds `.claude-plugin/plugin.json`, a `skills/<name>/SKILL.md`, and — for the mirror —
a `NOTICE.md` with attribution. Click any plugin below for its own README.

| Plugin | What it does | Source |
| --- | --- | --- |
| 🎙️ [`audio-transcription`](./audio-transcription) | `wav`/`mp3`/`m4a` → timestamped Markdown with Whisper (`mlx-whisper` on Apple Silicon, `openai-whisper` elsewhere). | Mine |
| 📝 [`meeting-notes`](./meeting-notes) | Raw transcripts in `rec/` → readable meeting summaries, one isolated subagent per transcript. Runs `humanizer` as a final pass. | Mine |
| ✍️ [`humanizer`](./humanizer) | Strips the tells of AI writing: em-dash pileups, rule-of-three, stock vocabulary, and the rest. | Mirror of [blader/humanizer](https://github.com/blader/humanizer) (MIT) |

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
  NOTICE.md                      # attribution (mirror only)
```

The mirrored `humanizer` keeps its original author and version in `.claude-plugin/plugin.json`; its
`NOTICE.md` spells out the attribution. See the root [LICENSE](../LICENSE).
