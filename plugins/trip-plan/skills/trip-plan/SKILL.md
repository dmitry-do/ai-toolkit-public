---
name: trip-plan
description: Build, review, or publish a travel itinerary. Use when the user asks to create a day trip or multi-day itinerary, wants an existing plan reviewed, reordered or updated, or wants a trip plan turned into an installable offline app for their phone. Trigger this whenever a request involves sequencing places to visit across days, planning stops around opening hours and travel time, or shipping an itinerary as a file or a published page, even if the user never says the word "itinerary". Always trigger this skill when a trip, travel or itinerary request mentions a PWA, Cloudflare Drop, an installable or offline app, a home-screen app, or publishing a plan to a link, because this skill owns that build and deploy path. Itineraries it produces carry locations, times and prices only, never booking references, access codes or personal data.
---

# /trip-plan

Plan or review a travel itinerary. Three phases: **create** (draft from scratch), **review** (audit an existing plan), **deliver** (ship the locked plan as a single HTML file, and as an installable PWA published on Cloudflare Drop).

## Inputs to gather

If anything below is missing from the request, ask once before drafting, and only for what's actually unclear. Don't ask if the file or message already contains it.

- **Dates** and **arrival/departure times** per day
- **Home base** (hotel / station) and how each day starts and ends
- **Locations to visit** (saved list, must-sees, or "suggest some")
- **Food preferences**, cuisines, dietary needs, budget per meal
- **Pace**, packed, balanced, or relaxed
- **Transport defaults**, walking first, transit when it saves real time, taxi only if called out
- **Hotel breakfast time** if applicable

Never ask for booking references, door codes or document numbers. They can't go in the plan (see below), so there's no reason to collect them.

## Sequencing: how stops get ordered

The order is most of the plan. The same stops in the wrong sequence cost two extra hours of travel and a closed door at 17:00. Work through these layers in order, because each one constrains the next.

**1. Place fixed anchors first.** Timed tickets, reservations, trains, sunset, last entry, tide windows, market days, and weekly closures. Many museums shut on Mondays, many Japanese gardens on Tuesdays. These can't move, so everything else bends around them. Check closing days per stop *before* assigning it to a date. It's the most common way an otherwise good plan breaks.

**2. Cluster by location, then assign clusters to dates.** Group stops by neighbourhood, valley, or coastal segment, and give each cluster one contiguous block of at least half a day. A day should read as one or two clusters. If a day touches four scattered areas, the clustering is wrong and no amount of clever transit will rescue it.

Which cluster lands on which date follows from:
- opening and closing days
- weather forecast: outdoor and viewpoint clusters on the clear day, indoor ones on the wet day
- arrival and departure times, so the first and last days carry a light cluster near the station or airport
- hotel changes, where the cluster nearest the new hotel goes on moving day
- jet lag or a late arrival, where day one stays close to home base
- market days, festivals, and anything else that only happens on one date

**3. Inside a cluster, order by walking distance.** Consecutive stops should be the shortest sensible link between them. The day should trace a line, not a star. If the route passes a place and comes back to it later, reorder until it doesn't.

**4. Give every stop an honest dwell time.** Ordering and dwell time are the same problem: a three-hour museum can't sit in a forty-minute gap, and a ten-minute viewpoint doesn't deserve the slot before dinner. Budget time *in* the area, not just travel *to* it. When a cluster's dwell plus travel exceeds the hours available, cut a stop instead of compressing everything by 20%.

**5. Use theme only where it costs nothing.** A themed run (temple morning, gallery afternoon, ramen crawl, whisky route, brutalist walk) makes a day easier to remember and easier to enjoy, because the stops build on each other instead of resetting. Group by theme when the themed stops already sit near each other. When theme and geography pull apart, geography wins, unless the theme is the reason for the trip. Two contrasting themes in one day beats four unrelated stops.

**6. Write the reason down.** Each day opens with a one-line **Why this order** note naming the constraint that drove it: "Sunset at Marshall Beach at 20:12 fixes the end, so the day runs north to south." That exposes the logic, so the user can argue with the reasoning instead of guessing at the output.

### Ordering self-check

Run this before showing any plan:

- Every stop's opening days and hours match the date and time it's been given
- No day crosses the city more than twice
- No stop gets passed and revisited
- Every anchor has buffer in front of it
- Each day ends near home base or the next morning's departure point
- Dwell plus travel per day fits inside the hours actually available, wake to sleep, with the meals already placed

Most of that is arithmetic, so don't do it by eye. Write the day out and run it:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-plan/scripts/route_check.py day.json
```

```json
{"date": "2026-11-27", "home_base": [34.7025, 135.4959],
 "day_start": "08:30", "day_end": "21:30",
 "stops": [{"name": "Nakanoshima Museum", "at": "10:15", "dwell": 90,
            "coords": [34.6923, 135.4917], "hours": "10:00-17:00",
            "closed": ["Mon"], "anchor": false}]}
```

Only `name` is required, and every check runs on the stops carrying the fields it
needs, so a day with half the coordinates still gets the closing days checked. Put
a real Maps number in `travel_min` when you have one and it overrides the estimate.

Errors mean the order is wrong: something is shut, an arrival is impossible, an
anchor has no buffer, or the day doesn't fit its own hours. Warnings are yours to
weigh. The zig-zag suggestion is geometry alone, so re-run the check on any
reordering before trusting it, since the shorter route often lands a museum after
closing time.

What it can't tell you is whether the day is worth doing. Two temples in a row
passes every check and still reads as one temple too many.

## Planning rules

**Timing**
- Account for real commute time between every stop (walk by default; subway/bus/tram only when it saves >15 min or distance is >2 km)
- Add buffer before any train/flight/show with a fixed start (30 min for trains, longer for flights)
- Match meal times to local norms, dinner 18:00–20:00, not 17:00

**Food spacing**
- Two big meals within 2 hours = bad. Space lunch and dinner by 4+ hours
- Coffee, cake, or a small snack before or after a meal is fine
- A morning coffee stop near the first attraction works well; don't force one right after hotel breakfast

**Choice at decision points**
- For coffee/lunch/dinner, list **2–3 options near that location** with rating, signature dish, and price band. Let the user pick on the day
- For sights, commit to one path unless two are genuine alternatives (then mark both and say "pick one")

**Bookings & timing-sensitive notes**
- Flag anything that needs advance booking (Alcatraz, popular onsen, kaiseki, certain shrines, etc.)
- Flag time-of-day constraints (sunset shots, last entry times, market closing)
- Flag seasonal/weather dependencies (snow roads, peak waterfall flow, cherry blossom windows)

## Output format

Markdown artifact for the draft and any revisions. Use emojis as section anchors (🏯 ☕ 🍱 🚄 🚶 ⏱️). Per day:

```
# 🏯 [City] — [Date]

**Duration:** HH:MM – HH:MM
**Home base:** [Hotel/Station]
**Why this order:** [the constraint that set the sequence, one line]

---

## ☕ HH:MM — [Activity name]

[One-line description of why this stop / what to expect.]

📍 Rating · review count (when known)
🚶 Walking time / 🚇 transit from previous stop
⏱️ Suggested time: X min

**Options (pick one):**
- **Place A** (4.6⭐): signature dish, price band
- **Place B** (4.5⭐): signature dish, price band

---
```

End each day with a short **Notes** block: bookings required, what to skip if running late, weather backup.

A finished week in this format — the Markdown, the `route_check.py` JSON for every day, and the
built HTML — is in `${CLAUDE_PLUGIN_ROOT}/skills/trip-plan/examples/`. Read it rather than guessing
at the shape of the output.

## Review mode

When the user shares an existing itinerary and asks for a review:

1. **Web-search current info** for opening hours, transit times, prices. Itineraries written months ago go stale fast.
2. **Check the sequence against the rules above.** Reordering is usually the highest-value edit, and it's free. Transcribe each day into the JSON above and run `route_check.py` first: it takes a minute and it's the difference between "this day looks tight" and "you arrive at Sumiyoshi Taisha 27 minutes after you're due at dinner". Then say plainly when a day zig-zags, when a stop sits on its closing day, or when the cluster belongs on a different date.
3. **Honest cut**, not validation. Use this structure:
   - **Strong regret risks**, irreplaceable things they'd miss (seasonal, unrepeatable, hard-to-book)
   - **Already covered well**, confirm what's solid
   - **Skippable if time runs short**, nice but generic stops
   - **Trade-offs to consider**, explicit "drop X to free time for Y" suggestions
4. Call out timing problems directly: tight transfers, meals too close together, sights that close before the planned arrival
5. Don't soften with hedging. "This won't work because the road opens late May, check nps.gov two days before" beats "you may want to consider checking"

## What to avoid

- Generic descriptions that read like a guidebook ("vibrant", "rich cultural heritage", "must-visit", "nestled in")
- Listing every possible thing, curate
- Making up ratings, prices, or hours when they're not in the input. Say "check before going" instead
- Padding with safety filler ("be sure to stay hydrated", "wear comfortable shoes")

## What never goes in the plan

The plan carries locations, times, durations, prices, ratings, and notes. It doesn't carry anything that identifies the traveller or unlocks something on their behalf. Keep out:

- Booking, confirmation, reservation and order references, PNRs, record locators, e-ticket and flight numbers tied to a person
- Door codes, lockbox codes, key safe codes, wifi passwords, any PIN or access code
- Passport, ID, licence and insurance policy numbers, dates of birth, payment card numbers, IBANs
- Personal phone numbers, email addresses, home address, hotel room numbers, seat assignments
- Full traveller names in the file's visible text

The reason is what happens to the file. It gets emailed, synced to a phone, left open on a train table, handed to whoever is driving, and published to a URL anyone can load. A trip plan should read like a guidebook page for that specific week, not like a boarding pass.

A venue's own public details are fine: the restaurant's phone number, the hotel's street address, the park's booking page. The distinction is whose data it is.

When the user's source material contains this stuff, keep the fact and drop the value. That's more useful anyway, because it says where to look:

- "Alcatraz ferry, booked, ref in email" instead of the reference
- "Ryokan check-in, code in your password manager" instead of the code
- "Bring passport for the tax refund" instead of the number

Say once that you've left the details out, then move on. Don't repeat it per stop.

The build enforces this rather than trusting it. `scrub_check.py` blocks on a keyword next to something value-shaped: "code in your password manager" passes, "door code 4829" doesn't. A keyword on its own comes back as a note to read, not a block. When a finding turns out to be a venue's public phone number, narrow it with `--allow "phone number"` rather than reaching for `--allow-pii`, which switches off the whole scan.

## Calendar integration

If the user asks to add events, use whatever calendar tool the runtime exposes rather than a name from memory. Connector tools get renamed, and a hardcoded one fails silently as a missing capability.

- Local timezone of the destination, not the traveller's home timezone
- Location strings precise enough for Maps to resolve, so the event doubles as navigation
- Anchors get a timed event. Flexible stops stay in the itinerary and out of the calendar, otherwise a three-day trip buries every real commitment under forty blocks
- Whichever calendar the user has told you to default to, ask once if they haven't

## Delivering the plan

When the user wants the plan as a file, an offline app, or a public URL, read `${CLAUDE_PLUGIN_ROOT}/skills/trip-plan/reference/deliver.md` and work from it. Visual direction is in `reference/style.md` beside it.

Both are worth opening rather than recalling. The build flags, the service worker behaviour and the deploy path are specific enough that a remembered version will be subtly wrong.
