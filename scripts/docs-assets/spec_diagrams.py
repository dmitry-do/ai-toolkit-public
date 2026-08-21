"""One function per plugin: builds its "how it works" diagram."""
from __future__ import annotations

from diagram import Canvas


def audio_transcription():
    c = Canvas(1240, 700, "audio-transcription",
               "one recording in, one timestamped Markdown file out")
    c.group(438, 112, 782, 400, "BUNDLED SCRIPT  ·  transcribe_audio.py")

    c.node("in", 40, 140, 320, 132, "Your recording", [
        "wav · mp3 · m4a",
        "mp4 · m4v · mov · mkv · webm",
        "(ffmpeg decodes the audio track)",
    ], kind="io")
    c.node("pre", 460, 140, 320, 132, "Preflight", [
        "Apple Silicon: mlx-whisper",
        "elsewhere: openai-whisper",
        "faster-whisper: opt-in, beam search",
    ], badge="--check")
    c.node("seg", 880, 140, 320, 132, "Segmenter", [
        "energy VAD drops silences > 2 s",
        "chunk plan, never below 45 s",
        "every cut snapped to a real pause",
    ])
    c.node("dec", 880, 350, 320, 132, "Decode loop", [
        "one chunk at a time",
        "!condition_on_previous_text: off",
        "rewrites the .md after every chunk",
    ])
    c.node("sec", 460, 350, 320, 132, "Second pass", [
        "re-transcribes voiced gaps",
        "drops hallucinated overlays",
        "retries low-confidence segments",
    ])
    c.node("out", 40, 350, 320, 132, "recording.md", [
        "Source: backend, model, language",
        "[00:31-00:39] one line per segment",
    ], kind="io", mono_title=True, title_size=15)
    c.node("side", 880, 552, 320, 96, "recording.md.progress.json", [
        "written after every chunk, deleted on success",
    ], kind="store", mono_title=True, title_size=14)

    c.edge("in:r", "pre:l", style="accent")
    c.edge("pre:r", "seg:l", style="accent")
    c.edge("seg:b", "dec:t", style="accent", label="chunks", label_dx=54, label_dy=-8)
    c.edge("dec:l", "sec:r", style="accent")
    c.edge("sec:l", "out:r", style="accent")
    c.edge("dec:b", "side:t", style="dashed", back=True, off_a=0.3, off_b=0.3,
           label="re-run to resume", label_dx=96, label_dy=-9)
    return c


def meeting_notes():
    c = Canvas(1240, 900, "meeting-notes",
               "a folder of transcripts in, one summary per meeting out")

    c.node("rec", 140, 118, 420, 96, "rec/*.txt", [
        "20260605 1400 Transcription [EN].txt",
    ], kind="io", mono_title=True, title_size=15)
    c.node("led", 680, 118, 420, 96, "RECORDINGS.md  +  archive/RECORDINGS.md", [
        "a row in either ledger counts as processed",
    ], kind="store", mono_title=True, title_size=13)

    c.node("s1", 340, 252, 560, 112, "Step 1 · find the delta", [
        "a bundled script diffs rec/ against both ledgers",
        "stdout is the unprocessed list, one filename per line",
        "the orchestrator never reads the tracker into context",
    ])

    c.group(100, 396, 760, 192,
            "STEP 2  ·  one isolated subagent per transcript, all launched in parallel")
    for i, (nid, name) in enumerate((("a1", "subagent"), ("a2", "subagent"), ("a3", "subagent"))):
        c.node(nid, 110 + i * 254, 442, 232, 124, name, [
            "reads one transcript",
            "writes its summary",
            "!never touches the tracker",
        ], title_size=15)

    c.node("sum", 900, 442, 240, 124, "summaries/…md", [
        "TLDR, discussion,",
        "decisions, and",
        "- [ ] task -- who, when",
    ], kind="io", mono_title=True, title_size=14)

    c.node("s25", 100, 626, 500, 112, "Step 2.5 · reconcile", [
        "every launched transcript must return a ROW: line",
        "every completed row's summary must exist on disk",
        "!a silent subagent is resumed, never marked done",
    ])
    c.node("s3", 640, 626, 500, 112, "Step 3 · tell check", [
        "grep the new summaries only: em dash, h1,",
        "bold-label bullets, Title Case drift",
        "hits escalate to humanizer, clean files are left alone",
    ])
    c.node("s4", 100, 770, 500, 100, "Step 4 · the orchestrator writes the tracker", [
        "one writer, so parallel rows can't race and drop",
    ])
    c.node("s45", 640, 770, 500, 100, "Step 4.5 · stow, row first", [
        "processed transcript and its row move to archive/ together",
    ])

    c.edge("rec:b", "s1:t", off_b=0.3, style="accent")
    c.edge("led:b", "s1:t", off_b=0.7, style="accent")
    for i, nid in enumerate(("a1", "a2", "a3")):
        c.edge("s1:b", nid + ":t", off_a=0.25 + i * 0.25, style="accent", bend=384)
    c.edge("a3:r", "sum:l", style="accent")
    c.edge("a2:b", "s25:t", style="accent", label="ROW: / TOPIC: / DICTIONARY:", label_dy=-9)
    c.edge("s25:r", "s3:l", style="accent")
    c.edge("s3:b", "s4:t", style="accent")
    c.edge("s4:r", "s45:l", style="accent")
    return c






def session_cost_stamp():
    c = Canvas(1240, 590, "session-cost-stamp",
               "the numbers only the statusLine can see, parked where the hook can read them")

    c.group(40, 112, 570, 216, "EVERY STATUSLINE RENDER")
    c.group(650, 112, 550, 216, "ONCE, AT SESSION END")

    c.node("sl", 60, 156, 260, 150, "statusLine", [
        "the only Claude Code surface",
        "handed cost, context % and",
        "duration, already computed",
    ])
    c.node("stash", 340, 156, 250, 150, "session-stats/<id>", [
        "three lines:",
        "used % / cost / duration_ms",
        "rewritten on every render",
    ], kind="store", mono_title=True, title_size=14)
    c.node("hook", 670, 156, 250, 150, "SessionEnd hook", [
        "receives only session_id,",
        "transcript_path, cwd, reason",
        "!no stash, nothing stamped",
    ])
    c.node("app", 940, 156, 240, 150, "append ai-title", [
        "the same entry type Claude",
        "Code writes itself, so the",
        "JSONL cannot be corrupted",
    ])
    c.node("out", 300, 396, 640, 118, "the session transcript .jsonl", [
        "Remove AI blocks on .NET pages (worked 4m 26s, context: 40%, cost: $26.24)",
        "the loader takes the last ai-title as the title, so this becomes the name",
        "shown in the sessions list and on --resume. Re-stamps replace the bracket.",
    ], kind="io")

    c.edge("sl:r", "stash:l", style="accent")
    c.edge("stash:r", "hook:l", style="accent", label="the bridge", label_dy=-32)
    c.edge("hook:r", "app:l", style="accent")
    c.edge("app:b", "out:t", style="accent", off_b=0.78)
    c.edge("out:t", "hook:b", style="dashed", off_a=0.22, off_b=0.35,
           label="reads the current title", label_dx=-2, label_dy=-9, arrow=True)
    return c


def trip_plan():
    c = Canvas(1240, 730, "trip-plan",
               "three phases; the skill picks the one the request actually asks for")

    c.group(40, 112, 370, 570, "1  ·  CREATE")
    c.group(435, 112, 370, 570, "2  ·  REVIEW")
    c.group(830, 112, 370, 570, "3  ·  DELIVER")

    c.node("ci", 60, 156, 330, 106, "Dates, home base, must-sees, pace", [
        "asked for once, only where unclear",
    ], kind="io", title_size=15)
    c.node("cs", 60, 296, 330, 186, "Sequencing", [
        "1  anchors first: tickets, trains,",
        "    sunset, weekly closing days",
        "2  cluster by neighbourhood",
        "3  inside a cluster, walking order",
        "4  an honest dwell time per stop",
        "5  one line saying why this order",
    ])
    c.node("cr", 60, 512, 330, 148, "route_check.py", [
        "closing days · late arrivals",
        "anchor buffers · day overflow",
        "detours and zig-zags",
        "!re-run it after every reorder",
    ], kind="guard", mono_title=True, title_size=15)

    c.node("ri", 455, 156, 330, 106, "A plan you already have", [
        "yours, or someone else's",
    ], kind="io", title_size=15)
    c.node("ra", 455, 296, 330, 186, "Audit", [
        "web-search the hours, transit",
        "and prices: plans go stale fast",
        "transcribe each day to JSON and",
        "run the same route_check.py",
        "reordering is free, so try it",
        "before dropping anything",
    ])
    c.node("ro", 455, 512, 330, 148, "An honest cut", [
        "strong regret risks",
        "already covered well",
        "skippable if time runs short",
        "drop X to free time for Y",
    ], kind="io")

    c.node("dh", 850, 156, 330, 106, "itinerary.html", [
        "one self-contained file, opens offline",
    ], kind="io", mono_title=True, title_size=15)
    c.node("ds", 850, 296, 330, 186, "scrub_check.py", [
        "blocks on a keyword sitting next",
        "to something value-shaped:",
        "\"code in your password manager\"",
        "passes, \"door code 4829\" does not",
        "!it runs first, inside the build",
    ], kind="guard", mono_title=True, title_size=15)
    c.node("db", 850, 512, 330, 148, "build_pwa.py", [
        "manifest, service worker, icons",
        "dist/ and dist.zip, index.html at",
        "the root, as Cloudflare Drop expects",
    ], mono_title=True, title_size=15)

    c.edge("ci:b", "cs:t", style="accent")
    c.edge("cs:b", "cr:t", style="accent")
    c.edge("ri:b", "ra:t", style="accent")
    c.edge("ra:b", "ro:t", style="accent")
    c.edge("dh:b", "ds:t", style="accent")
    c.edge("ds:b", "db:t", style="accent", label="clean", label_dy=-9)
    return c


BUILDERS = {
    "audio-transcription": audio_transcription,
    "meeting-notes": meeting_notes,
    "session-cost-stamp": session_cost_stamp,
    "trip-plan": trip_plan,
}
