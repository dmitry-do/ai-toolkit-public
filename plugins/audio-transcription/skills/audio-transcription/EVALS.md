# Behavioral evals — `audio-transcription`

These check that the **skill behaves** — triggers on the right asks, picks the right backend,
refuses correctly, asks before installing, resumes cleanly. They are a different axis from the
WER harness under `evals/`, which proves the *script* is accurate. Accuracy numbers cited below
come from `evals/results.md` and `evals/librispeech/results.md`.

Each scenario is input → expected behavior → verdict criterion. Run them by hand, or wire the
trigger set at the bottom into `skill-creator`'s `scripts/run_loop.py`.

## Scenarios

### S1 — Triggers with no file type named
- **Input:** "Can you transcribe this voice memo for me?" (no extension, no path yet)
- **Expected:** Skill triggers. Asks for the file/path and the output location before running.
- **Verdict:** Pass if it engages transcription and gathers inputs; fail if it ignores the ask or guesses a path.

### S2 — Apple Silicon picks mlx, refuses the Torch backend
- **Input:** On an Apple Silicon Mac: "Transcribe meeting.m4a with `--backend whisper`."
- **Expected:** Refuses `--backend whisper` on Apple Silicon (the script exits) and uses `mlx-whisper` instead, explaining why.
- **Verdict:** Pass if it routes to `mlx-whisper`; fail if it runs the openai-whisper/Torch path on Apple Silicon.

### S3 — Unsupported format stops and names the supported set
- **Input:** "Transcribe interview.flac" (also covers `.ogg`, `.aac`)
- **Expected:** Stops, says supported formats are `wav`/`mp3`/`m4a`, and offers to convert first (`ffmpeg -i interview.flac interview.wav`).
- **Verdict:** Pass if it does not feed the unsupported file to the script; fail if it tries anyway.

### S4 — Asks before installing a missing dependency
- **Input:** "Transcribe call.mp3" when `--check` reports `mlx-whisper` missing.
- **Expected:** Reports exactly what's missing and asks permission before `pip install`. Does not install silently.
- **Verdict:** Pass if it pauses for consent; fail if it installs or downloads weights without asking.

### S5 — Resumes from the sidecar after an interruption
- **Input:** A long chunked run is killed (`Ctrl-C`) partway; user re-runs the identical command.
- **Expected:** Detects `<output>.progress.json`, resumes from the last completed chunk, does not restart from zero. (Identity must match: same audio, model, language, chunk plan.)
- **Verdict:** Pass if it continues; fail if it silently re-transcribes completed chunks or stitches a mismatched plan.

### S6 — Batch mode skips existing outputs unless regeneration is requested
- **Input:** "Transcribe every recording in ./calls" where some `.md` outputs already exist.
- **Expected:** Skips files whose `.md` already exists; only regenerates when the user explicitly asks.
- **Verdict:** Pass if existing transcripts are left intact by default; fail if it overwrites without being asked.

### S7 — Language auto-detect vs. pin
- **Input:** "Transcribe entrevista.mp3" (Spanish) with no `--language` given.
- **Expected:** Lets Whisper auto-detect and writes the detected language into the `Source` block; offers `--language es` if the user wants to pin it.
- **Verdict:** Pass if it doesn't hard-code `en`; fail if it forces a language the user didn't ask for.

### S8 — Default model is accuracy; switch to turbo on a speed ask
- **Input:** "I've got 30 hours of podcasts to get through tonight — transcribe them."
- **Expected:** Keeps `large-v3` as the default for one-off accuracy, but recommends `--mlx-model …whisper-large-v3-turbo` for a long batch (~2.3× faster, small accuracy cost).
- **Verdict:** Pass if it surfaces the turbo tradeoff for the batch; fail if it silently runs the slow default over 30 hours or silently downgrades a one-off.

### S9 — Hard, noisy audio → faster-whisper is offered, not auto-run
- **Input:** "This far-mic, accented recording came out garbled — can you do better?"
- **Expected:** Offers `--backend faster` (beam search, ~15% relatively better on test-other) while flagging it runs CPU-only at ~1.5× realtime on Apple Silicon. Does not auto-select it.
- **Verdict:** Pass if it presents the accuracy/speed tradeoff and asks; fail if it silently switches backends or never mentions the option.

## What broke and how I fixed it

Two real regressions from the design log (`evals/results.md`), kept as the worked failures.

### F1 — The cross-chunk prompt-carry boundary cliff
- **Symptom:** Small chunks fell off a cliff — large-v3 at n=16 (51s chunks) scored **15.0% WER**
  while n=1–6 held at 3.8–4.2%. The hypothesis lost ~200 words and 19 segments.
- **Root cause:** It looked like a chunk-size limit, but it was the code carrying the previous
  chunk's text in as a `prompt`. That conditioned the decoder across the cut and made Whisper
  silently drop the head of the next chunk (~75 words lost, measured).
- **Fix:** Stop carrying text across boundaries — each chunk gets only the user's `--prompt`. The
  same n=16 config then scored **4.7%**. The "deletion at boundaries" failure mode disappeared;
  boundary snapping (default-on) handles the residual mid-word cuts.
- **Covered by:** scenario S5 (resume integrity) and the boundary-deletion failure mode in SKILL.md.

### F2 — The `condition_on_previous_text` repetition loop
- **Symptom:** On long audio Whisper fell into a repetition loop — one phrase repeated for minutes —
  inflating output to **400% / ~99.9% WER** and dropping real speech.
- **Root cause:** `condition_on_previous_text=True` (Whisper's default) feeds prior text back into
  the decoder, which can spiral into a fixed point on long runs.
- **Fix:** Disable `condition_on_previous_text` by default. Single-shot and chunked runs are now
  clean (large-v3 4.0%, turbo 4.2% on the fixture). `--condition-previous` re-enables it for the
  rare short-clip case, with the loop risk called out.
- **Covered by:** the S8 default-model path and the repetition-loop anti-pattern in SKILL.md.

## Trigger-rate test set

For `skill-creator`'s `scripts/run_loop.py` (or any should-trigger / should-not harness). Goal:
high recall on the left, no false fires on the right. Tighten the SKILL.md `description` from
whichever side fails.

### Should trigger
1. "transcribe this voice memo"
2. "what does this recording say?"
3. "turn my interview.m4a into text"
4. "clean up this librivox rip into markdown"
5. "I've got a 2-hour podcast, get me a transcript"
6. "write out what's in meeting.mp3"
7. "make timestamped notes from this lecture audio"
8. "can you caption this wav file"
9. "get the words out of this phone call recording"
10. "transcribe the conference session"

### Should NOT trigger (near-misses)
1. "summarize this meeting" (input is already text)
2. "convert this mp3 to wav" (format conversion, not transcription)
3. "generate a voiceover for this script" (TTS, the reverse direction)
4. "diarize these speakers" (speaker separation — out of scope)
5. "what format is this audio file?" (metadata, not content)
6. "translate this English paragraph to Spanish" (text translation)
7. "remove background noise from this recording" (audio cleanup)
8. "trim the first 30 seconds off this mp3" (audio editing)
9. "write me a podcast intro" (content generation)
10. "play this song for me" (playback)
