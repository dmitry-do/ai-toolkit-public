# 🧩 Plugins

Every plugin in the [ai-toolkit-public](../README.md) marketplace lives here, one directory each. A
directory holds `.claude-plugin/plugin.json` and usually a `skills/<name>/SKILL.md` (hook-only
plugins skip it). Click any plugin below for its own README.

| Plugin | What it does | Source |
| --- | --- | --- |
| 🗺️ [`trip-plan`](./trip-plan) | Itineraries sequenced around opening hours, travel time and anchors → an editable Markdown plan, then a self-contained HTML file and an installable PWA. Blocks the build on booking codes or personal data. | Mine |
| 🎙️ [`audio-transcription`](./audio-transcription) | `wav`/`mp3`/`m4a` → timestamped Markdown with Whisper (`mlx-whisper` on Apple Silicon, `openai-whisper` elsewhere). | Mine |
| 📝 [`meeting-notes`](./meeting-notes) | Raw transcripts in `rec/` → readable meeting summaries, one isolated subagent per transcript. | Mine |
| 🧾 [`session-cost-stamp`](./session-cost-stamp) | At session end, stamps worked-time, context %, and cost into the transcript as the session title (shows on `--resume`, persists in the file). Requires a statusLine that writes the stash. | Mine |
| 🧹 [`deslop`](./deslop) | Reworks a document in two passes on `claude-opus-4-8` — verify every claim against its source, then make the prose direct. Bundled agent pins the model; one isolated subagent per document. | Mine |

## 📦 Install

From inside Claude Code:

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install <plugin-name>@ai-toolkit-public
```

## 🗂️ Layout

```
plugins/<name>/
  .claude-plugin/plugin.json   # manifest (name, version, description, author)
  skills/<name>/SKILL.md        # the skill itself (absent in hook-only plugins)
  skills/<name>/scripts/        # bundled scripts (audio-transcription, trip-plan)
  skills/<name>/reference/       # reference docs (trip-plan)
  agents/<name>.md               # bundled subagent, pins its model (deslop)
  hooks/hooks.json               # lifecycle hooks (session-cost-stamp)
  scripts/                       # hook + statusline scripts (session-cost-stamp)
```

Every plugin README opens the same way: a **Demo** of it running, then **How it works** (a diagram
of the moving parts), then **How to use** (step by step, with the real input and the real
output). Every image is generated — the diagram and the GIF by
[`scripts/docs-assets/build.py`](../scripts/docs-assets/README.md), the screenshots by `shots.py`
beside it — and all of them live in `docs/assets/` rather than in a plugin, so nothing you install
carries a picture with it.

See the root [LICENSE](../LICENSE).
