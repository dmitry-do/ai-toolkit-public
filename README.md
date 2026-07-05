# 🧰 ai-toolkit-public

A curated public subset of my Claude Code plugins: audio transcription and meeting notes — plus the eval harness behind the transcription work.

## Install

Inside Claude Code:

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install <plugin-name>@ai-toolkit-public
```

## What's inside

| Plugin | What it does | Source |
| --- | --- | --- |
| 🎙️ [`audio-transcription`](./plugins/audio-transcription) | Turns `wav`/`mp3`/`m4a` recordings into timestamped Markdown with Whisper. Uses `mlx-whisper` on Apple Silicon, `openai-whisper` everywhere else. | Mine |
| 📝 [`meeting-notes`](./plugins/meeting-notes) | Cleans raw transcripts in `rec/` into meeting summaries you can actually read. | Mine |

Each plugin has its own `README.md`; [`plugins/`](./plugins) has an index.

## Evals

[`evals/`](./evals) holds the speed-vs-quality harness for `audio-transcription`, with reproducible WER numbers and a public-domain LibriVox *War & Peace* fixture. See [`evals/README.md`](./evals/README.md).

## License

[MIT](./LICENSE) covers the marketplace wrapper and the plugins.
