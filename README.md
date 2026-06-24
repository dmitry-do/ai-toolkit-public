# 🧰 ai-toolkit-public

A curated public subset of my Claude Code plugins: audio transcription, meeting notes, and a writing humanizer — plus the eval harness behind the transcription work. Some I wrote; one is a mirror of someone else's good work, with attribution.

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
| 📝 [`meeting-notes`](./plugins/meeting-notes) | Cleans raw transcripts in `rec/` into meeting summaries you can actually read. Runs `humanizer` as a final pass. | Mine |
| ✍️ [`humanizer`](./plugins/humanizer) | Strips the tells of AI writing: em-dash pileups, rule-of-three, stock vocabulary, and the rest. | Mirror of [blader/humanizer](https://github.com/blader/humanizer) (MIT) |

`humanizer` ships here because `meeting-notes` depends on it for its final cleanup pass.

Each plugin has its own `README.md`; [`plugins/`](./plugins) has an index.

## Evals

[`evals/`](./evals) holds the speed-vs-quality harness for `audio-transcription`, with reproducible WER numbers and a public-domain LibriVox *War & Peace* fixture. See [`evals/README.md`](./evals/README.md).

## License

[MIT](./LICENSE) covers the marketplace wrapper, the plugins I wrote, and the `NOTICE.md` files. The mirrored `humanizer` keeps its original MIT license and attribution in [`plugins/humanizer/NOTICE.md`](./plugins/humanizer/NOTICE.md).
