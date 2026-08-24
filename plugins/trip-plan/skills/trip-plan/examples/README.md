# Worked example: Tokyo, 23–29 December 2026

One week, carried through all three phases, so you can see what the skill produces before running
it. The trip is invented — no traveller, no real bookings — and it is the file the screenshot in
the plugin README is of.

| File | Phase | What it is |
| --- | --- | --- |
| [`tokyo-2026-12.md`](./tokyo-2026-12.md) | create | The plan you read and edit. A section per day, each opening with the constraint that set its order. |
| [`tokyo-2026-12.json`](./tokyo-2026-12.json) | create / review | The same seven days as `route_check.py` input: coordinates, opening hours, closing days, dwell times, anchors. |
| [`tokyo-2026-12.html`](./tokyo-2026-12.html) | deliver | The single self-contained file. `build_pwa.py` turns this one into `dist/` and `dist.zip`. |

**Hours, ratings and prices in these files are illustrative.** They were written to be plausible,
not researched against a live source. Check every one before going — which is what the skill tells
you to do with any plan more than a few weeks old.

## Reproducing the checks

```bash
SK=".."          # plugins/trip-plan/skills/trip-plan
python3 "$SK/scripts/route_check.py" tokyo-2026-12.json
```

```
Checking tokyo-2026-12.json, 7 day(s)
Order holds: nothing shut, nothing late, no day over its hours.
```

```bash
python3 "$SK/scripts/build_pwa.py" --html tokyo-2026-12.html --out /tmp/tokyo-dist \
  --name "Tokyo, December 2026" --short-name "Tokyo" \
  --theme "#33418f" --bg "#faf6ec" --initials TY
```

The build runs `scrub_check.py` first and prints seven `check` findings — "door code",
"password", "booking", "Passport" — and no blocking ones. That's the intended end state: the
*fact* is in the plan ("the door code is in your password manager", "ref in email") and the *value* never is.

## What the example is meant to show

- **Closing days drive the calendar, not preference.** Nezu Museum shuts for the year on the 25th,
  so it can only be the 24th. The 28th is a Monday in year-end week, when the museums are closed
  twice over, so that day is built from streets, one garden that opens on Mondays, and a free
  observatory — whose north deck is closed on fourth Mondays, which the 28th is.
- **A day can be checked on the clock alone.** The Hakone day carries no coordinates: intercity
  legs are timetable numbers, not geometry, so every leg has a real `travel_min` and the distance
  estimator stays out of it. Opening hours, arrival times and the 30-minute train buffers are all
  still checked.
- **Anchors first, then everything bends.** Five timed things across the week — two observation
  decks, a museum with a timed entry, a reserved train, a Christmas Eve dinner — and each day is
  ordered around the one it contains.
- **The privacy rule as phrasing, not omission.** "Ref in email" and "the door code is in your
  password manager" say where to look, which is more useful than the code and safe to publish.

One honest note on the scanner: an earlier draft of the checklist read "Passport with you on the
29th", and `scrub_check.py` blocked it — "29th" is four characters with a digit in it sitting next
to the word passport, which is exactly the shape of an identity number. It matches shapes, not
meaning. The fix is the one the skill recommends: reword it. It now reads "Passport in the day bag
on the last morning".
