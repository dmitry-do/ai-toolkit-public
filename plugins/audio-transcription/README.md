# 🎙️ audio-transcription

audio-transcription runs Whisper over your local audio and video files and hands back
timestamped Markdown you can read and grep, so the two minutes you need out of an hour of
recording become a search instead of a re-listen. It uses whichever Whisper build is
fastest on your hardware: `mlx-whisper` on Apple Silicon, `openai-whisper` everywhere else.
Audio formats are `wav`, `mp3` and `m4a`; video formats are `mp4`, `m4v`, `mov`, `mkv` and
`webm`, with ffmpeg pulling the audio track.

## 🎬 Demo

One real run from start to finish: the dependency check, a plain-language request, 87
seconds of audio transcribed in about 8, and the Markdown that came out. The same run is
broken down in [How to use](#how-to-use).

![audio-transcription demo](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/audio-transcription-demo.gif)

## ⚙️ How it works

![How audio-transcription works](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/audio-transcription-how-it-works.png)

Whisper fails in a handful of predictable ways, and each stage below exists to shut one of
them down:

- **Preflight** reads the platform and picks the backend from it instead of trusting the
  flag you passed. On Apple Silicon it refuses `--backend whisper` outright, because the
  Torch build is both slower and less accurate there.
- **Segmenter** keeps chunks at 45 seconds or longer, skips silences over about 2 seconds
  (Whisper likes to hallucinate "Thank you." into them), and moves each cut onto a real
  pause so no word is split down the middle. On `large-v3` at ~34s chunks, that snap alone
  moves WER from 8.8% to 3.7%.
- **Decode loop** runs with `condition_on_previous_text` off, which is what keeps Whisper
  out of its minutes-long repetition loops. It also does not feed the previous chunk's
  text across the cut; doing that silently dropped about 75 words in testing.
- **Second pass** checks the finished transcript back against the audio. It re-transcribes
  any voiced stretch no segment covers, removes hallucinated overlays, and re-runs the
  segments Whisper's own confidence signals flag. On clean recordings it does almost
  nothing.
- **The sidecar** is rewritten after each chunk and deleted once the run succeeds, which
  is what lets an interrupted job resume with no extra flag.

Every number here comes out of the harnesses in [`evals/`](../../evals), not from
intuition.

## 📦 Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install audio-transcription@ai-toolkit-public
```

## 🌐 Claude Web

Claude Code only, not claude.ai. It needs local `mlx-whisper`/`ffmpeg` and reads audio
files off your machine, and the claude.ai sandbox provides neither.

## 🧩 What it does

- Transcribes a single file or an entire folder into Markdown, with `[start-end] text`
  segments under a `Source` block that records the filename, backend, model and detected
  language.
- **Picks the backend for you.** `mlx-whisper` on Apple Silicon (required there),
  `openai-whisper` elsewhere, and an opt-in `faster-whisper` (beam search) for noisy,
  accented or far-mic audio.
- **Survives long jobs.** A chunked run rewrites the Markdown after every chunk and
  resumes from a sidecar if the run is interrupted, no flag needed.
- **Ships with the accuracy defaults on.** Silence skipping and boundary snapping are
  enabled out of the box, the second pass repairs Whisper's silent deletions and
  hallucinated overlays, and the repetition loops are disabled at the source
  (`condition_on_previous_text` off).

The value behind each default is measured, not asserted — see [`evals/`](../../evals) and
the "Tested with" stamp in the skill.

## 📖 How to use

`ROOT=${CLAUDE_PLUGIN_ROOT}/skills/audio-transcription` in the commands below.

### 1. Check the backend before committing to a long job

```bash
python3 "$ROOT/scripts/transcribe_audio.py" --check
```

```
ok       apple_silicon Darwin arm64
info     required     Apple Silicon must use mlx-whisper for this skill
info     mlx_model    mlx-community/whisper-large-v3-mlx
ok       ffmpeg       required for decoding supported audio formats
ok       mlx_whisper  required Apple Silicon backend
```

Anything missing is named on its own line. The skill asks first before it installs a
package or pulls model weights, since both go over the network.

### 2. Ask for the transcript

> "transcribe wap_v1_p1_ch1_clip.mp3, turbo is fine" · "what does this voice memo say?"

The skill reads the platform, uses the backend it's required to use there, and runs the
bundled script. You can also run it directly:

```bash
python3 "$ROOT/scripts/transcribe_audio.py" wap_v1_p1_ch1_clip.mp3 \
  --mlx-model mlx-community/whisper-large-v3-turbo
```

```
Transcribing wap_v1_p1_ch1_clip.mp3 with mlx-whisper...
Detected language: English
100%|██████████| 8701/8701 [00:03<00:00, 2226.09frames/s]
wap_v1_p1_ch1_clip.md
```

That run is real: 87 seconds of audio, 8 seconds of wall time end to end. Drop
`--mlx-model` to fall back to `large-v3`, the default and the more accurate of the two
(3.17% vs 3.33% weighted WER, at about 2.3× the time).

### 3. Read the output

The Markdown lands next to the audio under the same basename:

```markdown
# War and Peace — Ch. 1 (clip)

## Source
- Audio: `wap_v1_p1_ch1_clip.mp3`
- Backend: `mlx`
- Model: `mlx-community/whisper-large-v3-turbo`
- Detected language: `en`

## Transcript

[00:00-00:06] VOLUME I. PART I. CHAPTER I. OF WAR AND PEACE.

[00:06-00:11] This is a LibriVox recording. All LibriVox recordings are in the public domain.

[00:19-00:24] WAR AND PEACE. By Leo Tolstoy. Translated by Nathan Haskell Doyle.
```

The `Source` block records what produced the file, so it's never ambiguous which model
made a given transcript.

### 4. If the run dies, re-run the same command

No flag, no cleanup. A chunked run writes `<output>.progress.json` after every chunk, and
re-running the identical command picks up from the last completed one. Change the audio,
model, language or chunk plan and it starts over rather than stitching mismatched pieces
together.

```bash
python3 "$ROOT/scripts/transcribe_audio.py" long-interview.m4a     # crashed at chunk 6
python3 "$ROOT/scripts/transcribe_audio.py" long-interview.m4a     # resumes at chunk 7
```

### 5. Reach for the other backends only when the audio is hard

```bash
# noisy, accented, far-mic: beam search wins, at ~5.5× the wall time
python3 "$ROOT/scripts/transcribe_audio.py" panel.wav --backend faster --beam-size 5

# not Apple Silicon
python3 "$ROOT/scripts/transcribe_audio.py" panel.wav --backend whisper --whisper-model medium
```

## 🗂️ Structure

```
plugins/audio-transcription/
├── .claude-plugin/plugin.json   # marketplace manifest
├── README.md                    # this file
└── skills/audio-transcription/
    ├── SKILL.md                 # defaults, anti-patterns, "Tested with" stamp
    ├── scripts/transcribe_audio.py   # the transcription script
    └── examples/                # a real worked input → output

evals/audio-transcription/EVALS.md   # behavioral scenarios — NOT installed with the plugin
evals/                               # WER accuracy harness + fixtures — NOT installed
```

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
