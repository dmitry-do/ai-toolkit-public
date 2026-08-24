"""One function per plugin: builds its README demo GIF.

Where a plugin ships a script, the output below is copied from a real run of
it. The Claude turns around that output are the ones the README's "How to use"
section walks through.
"""
from __future__ import annotations

from terminal import Terminal

BAR = "█"


def _bar(frac, width=10):
    full = int(frac * width)
    part = " ▏▎▍▌▋▊▉█"[int((frac * width - full) * 8)] if full < width else ""
    return (BAR * full + part).ljust(width)


def audio_transcription():
    t = Terminal("audio-transcription")
    t.write("{d}# 1. check the backend before committing to a long job{/}")
    t.type('python3 "$SK/scripts/transcribe_audio.py" --check')
    t.outfast([
        "{g}ok{/}       apple_silicon Darwin arm64",
        "{d}info     required     Apple Silicon must use mlx-whisper for this skill{/}",
        "{d}info     mlx_model    mlx-community/whisper-large-v3-mlx{/}",
        "{g}ok{/}       ffmpeg       required for decoding supported audio formats",
        "{g}ok{/}       mlx_whisper  required Apple Silicon backend",
    ])
    t.blank()
    t.write("{d}# 2. just ask — the skill picks the backend and the flags{/}")
    t.ask("transcribe wap_v1_p1_ch1_clip.mp3, turbo is fine")
    t.say(["Apple Silicon with mlx-whisper present, so mlx is the backend.",
           "Turbo asked for, so I'll pass {y}--mlx-model{/} explicitly."])
    t.blank()
    t.type('python3 "$SK/scripts/transcribe_audio.py" wap_v1_p1_ch1_clip.mp3 '
           '--mlx-model mlx-community/whisper-large-v3-turbo', per_frame=5, ms=42)
    t.write("Transcribing wap_v1_p1_ch1_clip.mp3 with mlx-whisper...", 320)
    t.write("Detected language: {c}English{/}", 420)
    steps = [(0, 0, "00:00", "?"), (34, 3000, "00:01", "2566.62"),
             (65, 5652, "00:02", "2546.52"), (96, 8372, "00:03", "2632.93"),
             (100, 8701, "00:03", "2226.09")]
    for i, (pct, n, el, rate) in enumerate(steps):
        line = "{d}%3d%%|%s| %d/8701 [%s<00:00, %s frames/s]{/}" % (
            pct, _bar(pct / 100.0), n, el, rate)
        (t.write if i == 0 else t.rewrite)(line, 340)
    t.write("{g}wap_v1_p1_ch1_clip.md{/}", 1100)
    t.clear()
    t.write("{d}# 3. the result: a Source block and timestamped segments{/}")
    t.type("head -16 wap_v1_p1_ch1_clip.md")
    t.outfast([
        "{w}# War and Peace — Ch. 1 (clip){/}",
        "",
        "{w}## Source{/}",
        "- Audio: {y}`wap_v1_p1_ch1_clip.mp3`{/}",
        "- Backend: {y}`mlx`{/}",
        "- Model: {y}`mlx-community/whisper-large-v3-turbo`{/}",
        "- Detected language: {y}`en`{/}",
        "",
        "{w}## Transcript{/}",
        "",
        "{c}[00:00-00:06]{/} VOLUME I. PART I. CHAPTER I. OF WAR AND PEACE.",
        "",
        "{c}[00:06-00:11]{/} This is a LibriVox recording. All LibriVox recordings are in the "
        "public domain.",
        "",
        "{c}[00:19-00:24]{/} WAR AND PEACE. By Leo Tolstoy. Translated by Nathan Haskell Doyle.",
    ])
    return t


def meeting_notes():
    t = Terminal("meeting-notes")
    t.write("{d}# 1. what is actually unprocessed? a script answers, not a context read{/}")
    t.type('python3 "$SK/archive-old-recordings.py" --root . --list-unprocessed')
    t.outfast([
        "20260605 1400 Transcription [EN].txt",
        "20260606 1030 Transcription [EN].txt",
    ])
    t.blank()
    t.ask("/meeting-notes")
    t.say(["Two unprocessed transcripts. Launching one isolated subagent each, in parallel,",
           "so no meeting can leak attendees or decisions into the other."])
    t.blank(160)
    t.out([
        "   {d}↳ subagent 1{/}  20260605 1400 Transcription [EN].txt",
        "   {d}↳ subagent 2{/}  20260606 1030 Transcription [EN].txt",
    ], 900)
    t.blank()
    t.out([
        "   {g}✓{/} subagent 1  {d}ROW:{/} | 20260605 … | {c}2026-06-05_onboarding-redesign-sync.md{/}"
        " | Completed |",
        "   {g}✓{/} subagent 2  {d}ROW:{/} | 20260606 … | {c}2026-06-06_pricing-page-review.md{/}"
        " | Completed |",
    ], 950)
    t.clear()
    t.write("{d}# 2. reconcile, then check the writing mechanically{/}")
    t.say(["Both returned a ROW: line and both summary files exist on disk."])
    t.blank()
    t.type("grep -nE '—|^# |^- \\*\\*[^:*]+:\\*\\*' summaries/2026-06-05_onboarding-redesign-sync.md")
    t.write("{d}(no output, exit 1){/}", 700)
    t.say(["Clean, so {y}humanizer{/} is not invoked. Only files with hits get escalated."])
    t.blank()
    t.write("{d}# 3. write the rows first, then stow the transcripts{/}")
    t.type('python3 "$SK/archive-old-recordings.py" --root . --stow-processed')
    t.outfast([
        "Processed transcripts in rec/ : 2",
        "Unprocessed (left in place)   : 0",
        "Live rows to retire to archive: 2",
        "Moved 2 transcript(s) to archive/rec/ and 2 row(s) to archive/RECORDINGS.md.",
        "{g}OK: rec/ and RECORDINGS.md now cover exactly the unprocessed backlog.{/}",
    ])
    t.clear()
    t.write("{d}# 4. the summary{/}")
    t.type("head -18 summaries/2026-06-05_onboarding-redesign-sync.md")
    t.outfast([
        "{w}## Onboarding Redesign Sync{/}",
        "",
        "{w}### TLDR{/}",
        "The team is cutting signup from five screens to three: signup goes email-only, and phone",
        "verification moves to a soft prompt after the first session. Phone verification is the",
        "biggest leak — about 40% of users drop between screens two and three.",
        "",
        "{w}### Decisions made{/}",
        "- Signup goes email-only; phone verification is deferred to a soft prompt.",
        "- Welcome-screen copy will be decided by an A/B test, not internal debate.",
        "",
        "{w}### Action items{/}",
        "{c}- [ ]{/} Draft the spec for email-only signup {d}--{/} Marcus, by end of next week",
        "{c}- [ ]{/} Set up the welcome-copy A/B test, once the spec lands {d}--{/} Dana, after the spec",
        "{c}- [ ]{/} Check with legal and the fraud team {d}--{/} Priya, before launch",
    ])
    return t






def session_cost_stamp():
    t = Terminal("session-cost-stamp")
    t.write("{d}# 1. the statusLine is the only surface handed cost and context{/}")
    t.type("bash ~/.claude/statusline.sh <<< \"$STATUSLINE_JSON\"")
    t.write("ai-toolkit  main  {d}•{/}  40% context  {d}•{/}  {g}$26.24{/}", 800)
    t.blank()
    t.write("{d}# 2. so it parks them where a SessionEnd hook can reach them{/}")
    t.type("cat ~/.claude/session-stats/$SESSION_ID")
    t.outfast([
        "40.2       {d}# context used, %{/}",
        "26.2431    {d}# total cost, USD{/}",
        "266000     {d}# duration, ms{/}",
    ])
    t.blank()
    t.write("{d}# 3. the session ends. the hook fires with no cost data of its own{/}")
    t.type("jq -rc 'select(.type==\"ai-title\").aiTitle' \"$TRANSCRIPT\" | tail -1")
    t.write("Remove AI blocks on .NET pages", 900)
    t.clear()
    t.write("{d}# the hook reads the stash, appends a native ai-title entry, deletes the stash{/}")
    t.type('bash "$PLUGIN/scripts/stamp-session-cost.sh" <<< "$SESSION_END_JSON"')
    t.blank(500)
    t.type("tail -1 \"$TRANSCRIPT\"")
    t.write('{d}{"type":"ai-title","aiTitle":"{/}Remove AI blocks on .NET pages {g}(worked 4m 26s, '
            'context: 40%, cost: $26.24){/}{d}",…}{/}', 1000)
    t.blank()
    t.type("ls ~/.claude/session-stats/$SESSION_ID")
    t.write("{r}ls: No such file or directory{/}  {d}← consumed, so it cannot be double-counted{/}", 900)
    t.blank()
    t.say(["That title is what the sessions list and {y}claude --resume{/} now show, and it stays",
           "in the transcript file. A re-stamp replaces the bracket rather than compounding it."])
    return t


def trip_plan():
    t = Terminal("trip-plan")
    t.write("{d}# 1. the day looks fine on paper. run it before showing it to anyone{/}")
    t.type('python3 "$SK/scripts/route_check.py" day.json')
    t.outfast([
        "Checking day.json, 1 day(s)",
        "  2026-11-30  {r}ERROR{/}  closed         Nakanoshima Museum is closed on Mon",
        "  2026-11-30  {r}ERROR{/}  tight link     Nakanoshima Museum to Tsutenkaku: leaving 11:30, "
        "28 min transit, arrives 11:57, 18 min late",
        "  2026-11-30  {r}ERROR{/}  tight link     Amerikamura to Sumiyoshi Taisha: leaving 14:35, "
        "37 min transit, arrives 15:11, 27 min late",
        "  2026-11-30  {r}ERROR{/}  anchor buffer  Kaiseki booking is an anchor with 1 min of slack, "
        "30 wanted",
        "  2026-11-30  {r}ERROR{/}  day overflow   670 min of stops and travel in a 660 min day, cut "
        "about 10 min",
        "  2026-11-30  {y}warn{/}   detour         Sumiyoshi Taisha adds 11.6 km between Amerikamura "
        "and Kuromon Ichiba",
        "",
        "{r}7 problem(s) in the order.{/} Reordering is free and usually fixes more than",
        "cutting stops does, so try the sequence before dropping anything.",
    ])
    t.clear()
    t.write("{d}# 2. reorder north to south, drop the outlier, re-run{/}")
    t.type('python3 "$SK/scripts/route_check.py" day.json')
    t.outfast([
        "Checking day.json, 1 day(s)",
        "  2026-11-27  {y}warn{/}   tight link     Mel Coffee Roasters to Nakanoshima Museum leaves "
        "9 min of slack",
        "  2026-11-27  {y}warn{/}   zig-zag        2.7 km of 14.4 km comes back on itself, check "
        "hours before applying",
        "{g}Order holds: nothing shut, nothing late, no day over its hours.{/}",
    ])
    t.blank()
    t.write("{d}# 3. ship it. the privacy scan runs first, inside the build{/}")
    t.type('python3 "$SK/scripts/build_pwa.py" --html itinerary.html --out dist '
           '--name "Osaka, November 2026"', per_frame=5, ms=42)
    t.outfast([
        "  line 2     {r}BLOCK{/}  access code or password  Door code 4***      keep the fact, drop "
        "the code",
        "  line 5     {r}BLOCK{/}  booking reference        Confirmation X7**PQ  write \"booked, ref "
        "in email\"",
        "",
        "{r}6 blocking finding(s).{/} An itinerary carries locations, times, prices and notes.",
        "{r}Nothing was built.{/}",
    ])
    t.blank()
    t.say(["It refuses to build a leaky file, and it never prints the value it found.",
           "Keeping the fact and dropping the value is more useful anyway."])
    t.clear()
    t.write("{d}# 4. codes replaced with where to find them, then build again{/}")
    t.type('python3 "$SK/scripts/build_pwa.py" --html itinerary.html --out dist '
           '--name "Osaka, November 2026"', per_frame=6, ms=40)
    t.outfast([
        "  line 4     {y}check{/}  secret wording   password    fine on its own, check no code "
        "follows it",
        "{g}No blocking findings.{/} Confirm the flagged items are public venue details.",
        "Built dist (build 1c2eec50f9)",
        "  {d}icons/apple-touch-icon.png            1836 bytes{/}",
        "  {d}icons/icon-192.png                    1928 bytes{/}",
        "  {d}icons/icon-maskable-512.png           2658 bytes{/}",
        "  {c}index.html{/}                            2995 bytes",
        "  {d}manifest.webmanifest                   849 bytes{/}",
        "  {d}sw.js                                 2243 bytes{/}",
        "{g}Zipped: dist.zip (11388 bytes, files at zip root){/}",
        "Deploy this directory or the zip. index.html sits at the root, as Drop expects.",
    ])
    return t



def deslop():
    t = Terminal("deslop")
    t.ask("/deslop widgetcache/README.md")
    t.say(["Its source of truth is cache.py. Dispatching a claude-opus-4-8 subagent to check",
           "every claim against it, then make the prose direct — accuracy first."])
    t.blank()
    t.type("sed -n '3p' widgetcache/cache.py")
    t.outfast([
        "{w}DEFAULT_TTL = 300{/}  {d}# seconds; override per call with ttl=, or globally --ttl{/}",
    ])
    t.blank()
    t.write("{d}# Pass 1 - accuracy{/}")
    t.out([
        "   {y}CORRECTIONS{/}",
        "     \"cached for ten minutes by default\"  {c}->{/}  source default is 300 s = 5 min (cache.py:3)",
        "     \"turn caching off per call\"          {c}->{/}  the source names it: no_cache=True (cache.py:7)",
        "   {y}FLAGGED{/}",
        "     \"a hundred times a minute\"  {c}->{/}  no such figure in the source; cut",
    ], 420)
    t.blank(1300)
    t.clear()
    t.write("{d}# Pass 2 - style: lead with the subject, drop the teaser and the promo{/}")
    t.blank()
    t.outfast([
        "{r}-Ever notice how the same request hammers your API a hundred times a minute?{/}",
        "{r}-widgetcache is here to change all that. It wraps your calls in a blazing-fast,{/}",
        "{r}-rock-solid, drop-in cache — so your app stays fast, your costs stay low...{/}",
        "{r}-Responses are cached for ten minutes by default...{/}",
        "{g}+widgetcache memoises a function call in memory, keyed by a `key` you supply:{/}",
        "{g}+within the TTL a repeated call returns the stored value instead of re-running.{/}",
        "{g}+{/}",
        "{g}+Values are cached for five minutes by default (`DEFAULT_TTL = 300`); pass `ttl=`{/}",
        "{g}+to change it, or `no_cache=True` to skip the cache for one call.{/}",
    ])
    t.blank()
    t.say(["Two facts corrected against cache.py, one made-up figure cut, the teaser gone.",
           "humanizer is installed — want me to run it over the result for any AI tells?"])
    return t

BUILDERS = {
    "audio-transcription": audio_transcription,
    "deslop": deslop,
    "meeting-notes": meeting_notes,
    "session-cost-stamp": session_cost_stamp,
    "trip-plan": trip_plan,
}
