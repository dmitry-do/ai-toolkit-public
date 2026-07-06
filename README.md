# 🧰 ai-toolkit-public

A curated public subset of my Claude Code plugins: audio transcription, meeting notes, and a session-cost stamp — plus the eval harness behind the transcription work.

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
| 🧾 [`session-cost-stamp`](./plugins/session-cost-stamp) | At session end, stamps the session's worked-time, context %, and cost into the transcript as its title, so it shows on `--resume`. Needs a statusLine that writes the stash. | Mine |

Each plugin has its own `README.md`; [`plugins/`](./plugins) has an index.

## Evals

[`evals/`](./evals) holds the speed-vs-quality harness for `audio-transcription`, with reproducible WER numbers and a public-domain LibriVox *War & Peace* fixture, plus a behavioral trigger-rate harness for the skills (does the right phrasing fire them, do near-misses hold). See [`evals/README.md`](./evals/README.md).

## License

[MIT](./LICENSE) covers the marketplace wrapper and the plugins.
