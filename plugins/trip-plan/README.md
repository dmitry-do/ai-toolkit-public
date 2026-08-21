# trip-plan

Plan a trip, review one someone already wrote, then ship it as a file you can open on a plane and
an app that sits on the home screen.

## Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install trip-plan@ai-toolkit-public
```

## Claude Web

The planning and review phases work anywhere. The delivery phase — building the PWA and publishing
it — needs a shell, so it's Claude Code only.

## What it does

Three phases, and the skill picks the one the request asks for:

- **Create** — drafts a day-by-day itinerary. Anchors first (timed tickets, trains, sunset, weekly
  closures), then stops clustered by neighbourhood, then ordered by walking distance inside each
  cluster, with an honest dwell time on every stop. Each day opens with a one-line *why this order*
  so the reasoning is arguable, not just the output.
- **Review** — audits an existing plan against the same rules and says plainly what's broken: a
  stop sitting on its closing day, a day that crosses the city four times, a dinner you arrive at
  27 minutes late. Cuts are ranked by regret rather than softened.
- **Deliver** — one self-contained HTML file (opens offline from Files, no server), then the same
  file wrapped as an installable PWA with a manifest, service worker, and icons, zipped for
  Cloudflare Drop. Today's day-card opens on load; stops already past fold away.

## Privacy is a build step, not a promise

The plan carries locations, times, prices, and ratings. It never carries booking references, door
codes, passport numbers, card numbers, or personal contact details — because the file gets emailed,
synced, left open on a train table, and published to a URL anyone with the link can read.

The rule is enforced rather than trusted: `build_pwa.py` runs `scrub_check.py` first and refuses to
build a leaky file. The scanner blocks on a keyword next to something value-shaped, so
`code in your password manager` passes and `door code 4829` doesn't.

## Scripts

All three are stdlib-only Python 3 and run standalone.

```bash
SK="${CLAUDE_PLUGIN_ROOT}/skills/trip-plan"

# Does the day actually work? Closing days, arrival times, anchor buffers, overflow, zig-zags.
python3 "$SK/scripts/route_check.py" day.json

# Would this file leak something? Runs automatically inside the build too.
python3 "$SK/scripts/scrub_check.py" itinerary.html

# Wrap the HTML as an installable PWA + dist.zip.
python3 "$SK/scripts/build_pwa.py" --html itinerary.html --out dist \
  --name "California Coast, May 2026" --short-name "CA Coast" \
  --theme "#b5533c" --bg "#faf6ef" --initials CA

# Fixtures for both checkers.
python3 "$SK/tests/run_tests.py"
```

`route_check.py` takes a day as JSON; only `name` is required per stop, and each check runs on
whatever fields are present, so a half-filled day still gets its closing days checked.

## Structure

```
plugins/trip-plan/
├── .claude-plugin/plugin.json      # marketplace manifest
├── README.md                       # this file
└── skills/trip-plan/
    ├── SKILL.md                    # sequencing rules, review mode, the privacy rule
    ├── reference/
    │   ├── deliver.md              # HTML build, PWA packaging, Cloudflare Drop deploy
    │   └── style.md                # visual direction for the itinerary page
    ├── scripts/
    │   ├── route_check.py          # day feasibility checker
    │   ├── scrub_check.py          # PII / booking-code scanner
    │   └── build_pwa.py            # HTML → installable PWA + zip
    └── tests/
        ├── run_tests.py            # 11 fixture cases, no framework
        └── fixtures/               # a clean day, a broken day, a safe page, a leaky page
```
