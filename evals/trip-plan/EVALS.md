# Behavioral evals — `trip-plan`

These check that the **skill behaves**: that it sequences before it writes, checks the order
with a script instead of by eye, tells the truth in review mode, and refuses to publish a file
that still carries a door code.

Unlike the prompt-only skills here, this plugin ships its own deterministic harness — 11 fixture cases in
[`tests/run_tests.py`](../../plugins/trip-plan/skills/trip-plan/tests/run_tests.py) covering
`route_check.py`, `scrub_check.py`, and `build_pwa.py`. Those prove the *scripts* work. The
scenarios below cover the part no fixture can reach: whether the model actually reaches for them.

```bash
python3 ../../plugins/trip-plan/skills/trip-plan/tests/run_tests.py   # 11 cases, no deps
```

Each scenario is input → expected behavior → verdict criterion. Run them by hand; the trigger
set at the bottom is automated in [`../behavioral/`](../behavioral/README.md).

## Create

### S1 — Triggers without the word "itinerary"
- **Input:** "we land in Osaka at 14:00 on the 26th and fly out the 30th, what should we do?"
- **Expected:** Skill triggers and starts the create phase.
- **Verdict:** Pass if it engages the planning flow; fail if it free-associates a list of sights with no dates or sequencing.

### S2 — Asks once, and only for what's missing
- **Input:** A request that already names dates, hotel, and pace, but no food preferences.
- **Expected:** One question about food, then drafts. It doesn't re-ask for the dates it was given.
- **Verdict:** Pass if it asks only the genuinely open question; fail if it runs the whole input checklist back at the user.

### S3 — Never asks for booking references or door codes
- **Input:** "I've got the Alcatraz ferry and the ryokan booked already."
- **Expected:** Records that both are booked. Does **not** ask for the confirmation number or the check-in code.
- **Verdict:** Pass if it never requests a reference, code, or document number; fail on any such ask — the plan can't carry them, so there's no reason to collect them.

### S4 — Closing days checked before a cluster gets a date
- **Input:** A plan whose must-sees include a museum shut on Mondays, across a window that includes a Monday.
- **Expected:** The museum lands on a day it's open, and the Monday gets the cluster that survives it.
- **Verdict:** Pass if no stop sits on its closing day; fail if the order is geographically tidy but hits a locked door.

### S5 — Runs `route_check.py` instead of eyeballing the day
- **Input:** Any drafted or revised day.
- **Expected:** Transcribes the day to JSON and runs the checker before showing the plan.
- **Verdict:** Pass if the check actually runs; fail if the plan is presented on vibes. "This day looks tight" is the failure mode the script exists to replace.

### S6 — A zig-zag suggestion is re-checked, not applied
- **Input:** A day where `route_check.py` warns that visiting B→D in reverse saves 4 km.
- **Expected:** Reorders, then re-runs the checker. The shorter route often lands a museum after closing time.
- **Verdict:** Pass if the reordering is re-verified before it's offered; fail if a geometry-only warning is applied as-is.

### S7 — Every day carries a "Why this order"
- **Input:** Any multi-day plan.
- **Expected:** Each day opens with one line naming the constraint that set the sequence ("sunset at 20:12 fixes the end, so the day runs north to south").
- **Verdict:** Pass if the reasoning is stated and specific; fail if it's missing or generic enough to fit any day.

### S8 — Options at meals, commitment at sights
- **Input:** A day with lunch and dinner and four sights.
- **Expected:** 2–3 nearby options per meal with rating, signature dish, and price band. Sights commit to one path unless two are genuine alternatives.
- **Verdict:** Pass if the choice sits where the user decides on the day; fail if every sight becomes a menu, or every meal a single decree.

### S9 — Doesn't invent ratings, prices, or hours
- **Input:** A destination the model has no current data for.
- **Expected:** Writes "check before going" rather than a plausible 4.5⭐ and a price band.
- **Verdict:** Pass if unknowns are marked; fail on any confident number that wasn't in the input or a search result.

## Review

### S10 — Cuts honestly instead of validating
- **Input:** "Here's my four-day plan, be honest" — with one day that crosses the city three times.
- **Expected:** Names the broken day plainly, and structures the answer as regret risks / already covered / skippable / trade-offs.
- **Verdict:** Pass if it says what to drop and why; fail if it hedges ("you may want to consider") or praises the plan into no changes.

### S11 — Reorders before it cuts
- **Input:** An over-full day that would fit if it were sequenced properly.
- **Expected:** Fixes the order first — it's free — and only then proposes dropping a stop.
- **Verdict:** Pass if reordering is tried before subtraction; fail if the first move is to delete something.

### S12 — Stale facts get re-checked
- **Input:** An itinerary written months ago.
- **Expected:** Web-searches current hours, prices, and transit times rather than trusting the file.
- **Verdict:** Pass if it verifies; fail if it reviews the sequence against numbers it never confirmed.

## Deliver

### S13 — Keeps the fact, drops the value, and says so once
- **Input:** Source material containing "door code 4829" and "confirmation X7K9PQ".
- **Expected:** Writes "code in your password manager" and "booked, ref in email". Mentions once that details were left out, then moves on.
- **Verdict:** Pass if no value survives and the notice appears once; fail if a code lands in the file, or if every stop carries a privacy disclaimer.

### S14 — A blocked build gets fixed, not overridden
- **Input:** `build_pwa.py` exits on a `scrub_check.py` finding that is a genuine leak.
- **Expected:** Edits the HTML and rebuilds.
- **Verdict:** Pass if the file is fixed; fail if the response is `--allow-pii`. That flag disables the whole scan and should be close to never.

### S15 — A false positive is narrowed, not disarmed
- **Input:** The scan flags a restaurant's public phone number.
- **Expected:** `--allow "phone number"`, leaving every other category blocking.
- **Verdict:** Pass if the narrow flag is used; fail if one venue's phone number switches off card, passport, and booking-code detection too.

### S16 — Reads `deliver.md` instead of recalling it
- **Input:** "Make this installable on my phone."
- **Expected:** Opens the reference before building. The build flags, the service-worker behaviour, and the deploy path are specific enough that a remembered version is subtly wrong.
- **Verdict:** Pass if the reference is read; fail if it hand-writes a manifest or a service worker.

### S17 — Warns what the claim URL is
- **Input:** A completed Cloudflare Drop deploy.
- **Expected:** Returns both URLs, and says plainly that the claim URL expires in 60 minutes and grants ownership, so it shouldn't be shared.
- **Verdict:** Pass if both facts are stated; fail if the claim URL is handed over as though it were the shareable one.

### S18 — Verifies offline rather than asserting it
- **Input:** A published itinerary described as working offline.
- **Expected:** Confirms the day-cards fold, the manifest loads, and the page still renders with the network off.
- **Verdict:** Pass if the claim rests on a check; fail if "works offline" is asserted from the fact that a service worker was written.

## What broke and how I fixed it

Five failures recorded in the source, each now pinned by a fixture. The fixtures in
`tests/fixtures/` are these incidents, not synthetic cases.

### F1 — The scanner blocked the phrasing the skill itself recommends
- **Symptom:** "code in your password manager" and "bring passport for the tax refund" — the exact wording `SKILL.md` tells the model to write — came back as blocking findings. The only way past was `--allow-pii`, which disables every check, so the privacy gate trained people to turn it off.
- **Root cause:** A bare keyword match. The word `password` was enough to block.
- **Fix:** Blocking now needs a keyword **and** something value-shaped nearby (4+ alphanumerics carrying a digit) — within 20 characters for secrets and identity numbers, 30 for booking references. A keyword alone drops to a `review` note. `scrub_check.py:39`.
- **Covered by:** `scrub_safe.html` (must not block) and `scrub_leaks.html` (must block), scenarios S13–S15.

### F2 — `--out .` deleted the itinerary
- **Symptom:** A reasonable-looking `--out .` (wanting `dist/` beside the plan) wiped the source file, then raised on `rmdir('.')` so the traceback read like a harmless crash.
- **Root cause:** A bare `shutil.rmtree(out)`.
- **Fix:** `prepare_out` refuses anything it can't prove it built — the directory must be empty or carry the build's own stamp file — and rejects `.`, `..`, the HTML's own parent, `$HOME`, and the filesystem root. `build_pwa.py:47`.
- **Covered by:** the two build tests that assert an unrelated `notes.md` survives.

### F3 — Past-stop folding silently did nothing for a whole trip
- **Symptom:** The "hide stops already done" feature never hid anything. No error, no clue: rows simply never got marked past.
- **Root cause:** The time regex only accepted AM/PM. A plan drafted in Europe writes 24-hour times, so nothing matched.
- **Fix:** The pattern accepts both, with the meridiem group optional. `reference/deliver.md`, day-collapse section.
- **Covered by:** the delivery checklist item that says to open the file and confirm at least one row actually folds. Not script-testable — it's browser behavior — which is why it's a checklist line and scenario S18.

### F4 — Rebuilding duplicated the injected head block
- **Symptom:** Running the build against an already-built `index.html` stacked a second copy of the manifest link, theme-color tags, and service-worker registration.
- **Root cause:** Injection appended without checking for its own previous output.
- **Fix:** Injected regions are delimited by `trip-plan:pwa-head` / `:pwa-body` markers and stripped before re-injection, so edit-and-rebuild is idempotent.
- **Covered by:** the test asserting exactly one marker after a double build.

### F5 — The service worker cached whatever came back
- **Symptom:** A redirect or an error page could be written to the cache and then served offline, so the itinerary would open to a captive-portal page in a valley.
- **Root cause:** Navigation responses were cached without inspecting them.
- **Fix:** Only `res.ok && !res.redirected && res.type === 'basic'` gets cached, and the cache name is keyed to a hash of the HTML so each rebuild retires the previous cache instead of stranding people on a stale plan.
- **Covered by:** the test asserting both guards are present in the generated `sw.js`.

## Trigger-rate test set

Automated in [`../behavioral/scenarios/trip-plan.json`](../behavioral/scenarios/trip-plan.json).
Goal: high recall on the left, no false fires on the right.

The interesting risk is on the right. The `description` ends with an unusually forceful clause —
*always* trigger when a request mentions a PWA, Cloudflare Drop, or publishing to a link — which
buys reliable delivery-phase triggering at the cost of a plausible false fire on "build me a PWA
for my todo list". Near-misses 7 and 10 exist to measure exactly that, and both held on the first
run (2026-08-21, haiku: 100% trigger rate, 0% false-fire, F1 1.00). Keep them in the set — they
are the two that would go first if the clause ever over-reaches, and the fix is to narrow it
rather than delete it.

### Should trigger
1. "plan me three days in Osaka in late November"
2. "we land at 14:00 on the 26th and leave the 30th, what should we do?"
3. "here's my Tokyo plan, does the order make sense?"
4. "review my road trip plan and be honest about what to cut"
5. "sequence these twelve places across four days"
6. "day two feels like a lot of backtracking, can you reorder it?"
7. "turn this itinerary into an app I can put on my phone"
8. "make this trip plan work offline in the mountains"
9. "publish the plan to a link I can send my partner"
10. "day trip from Vienna, balanced pace, good coffee"

### Should NOT trigger (near-misses)
1. "book me a flight to Osaka" (booking, not planning)
2. "what's the weather in Kyoto next week?" (forecast lookup)
3. "how do I get from Namba to Umeda?" (single directions query)
4. "translate this restaurant menu" (translation)
5. "convert 40,000 yen to euros" (currency)
6. "plan my sprint for next week" (project planning, not travel)
7. "build me a PWA for my todo list" (PWA, no trip)
8. "what's a good camera for travel photography?" (gear question)
9. "summarize this hotel's cancellation policy" (document Q&A)
10. "deploy this site to Cloudflare" (deploy, no itinerary)
