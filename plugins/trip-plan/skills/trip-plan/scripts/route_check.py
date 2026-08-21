#!/usr/bin/env python3
"""
route_check.py - check a day's stop order before anyone reads the plan.

The privacy rule already has a script that blocks the build. Sequencing is the
harder half and had nothing, so a garden scheduled on its closing day or a day
that crosses the city three times only surfaced when a human noticed. This runs
the checks from the ordering self-check in SKILL.md against a small JSON file.

    python3 scripts/route_check.py day.json
    python3 scripts/route_check.py trip.json --walk 4.0 --buffer 20

Input: one day object, a list of them, or {"days": [...]}.

    {
      "date": "2026-11-27",
      "day_start": "08:30",
      "day_end": "22:00",
      "stops": [
        {"name": "Kissa Madura", "at": "09:30", "dwell": 45,
         "coords": [34.6684, 135.5019], "closed": ["Tue"],
         "hours": "08:00-17:00", "anchor": false, "travel_min": 12}
      ]
    }

Only `name` is required. Every check runs on the stops that carry the fields it
needs and stays quiet about the rest, so a half-filled day still gets whatever
can be checked. `travel_min` overrides the distance estimate when you have a real
number from Maps.

Exit codes: 0 clean or warnings only, 1 errors present.

It knows distances and clocks, not neighbourhoods. It can't tell you the day is
dull, that two temples in a row is one too many, or that the 08:30 start is
brutal after a night flight. The zig-zag suggestion is geometry alone: the order
it proposes may put a museum after closing time, so re-run the check on any
reordering rather than applying it as read.
"""

import argparse
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
STREET_FACTOR = 1.35   # straight-line km to actual pavement
TRANSIT_KMH = 18.0     # door to door, city rail or bus
TRANSIT_OVERHEAD = 7   # minutes of platform, ticket and waiting

TIME_RE = re.compile(r"^\s*~?\s*(\d{1,2}):(\d{2})\s*([AaPp])?\.?[Mm]?\.?\s*$")


def parse_time(value):
    """Minutes since midnight from '09:30', '9:30 AM' or '~9:45 pm'."""
    if value is None:
        return None
    m = TIME_RE.match(str(value))
    if not m:
        return None
    hh, mm, mer = int(m.group(1)), int(m.group(2)), m.group(3)
    if mer:
        mer = mer.lower()
        if hh == 12:
            hh = 0
        if mer == "p":
            hh += 12
    if hh > 23 or mm > 59:
        return None
    return hh * 60 + mm


def clock(minutes):
    return "%02d:%02d" % (minutes // 60 % 24, minutes % 60)


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))


def travel_minutes(km, walk_kmh):
    """Walk unless transit is worth it, which is the rule the skill already states."""
    street = km * STREET_FACTOR
    walk = street / walk_kmh * 60
    transit = TRANSIT_OVERHEAD + street / TRANSIT_KMH * 60
    if km > 2 and (walk - transit) > 15:
        return transit, "transit"
    return walk, "walk"


def parse_hours(spec):
    """'08:00-17:00' or '11:30-14:00, 17:30-21:00' or '24h' -> list of (open, close)."""
    if not spec:
        return None
    if str(spec).strip().lower() in ("24h", "24/7", "always"):
        return [(0, 24 * 60)]
    ranges = []
    for part in str(spec).split(","):
        bits = part.replace("\u2013", "-").split("-")
        if len(bits) != 2:
            continue
        a, b = parse_time(bits[0]), parse_time(bits[1])
        if a is None or b is None:
            continue
        ranges.append((a, b if b > a else b + 24 * 60))
    return ranges or None


def closed_weekdays(stop):
    out = set()
    for d in stop.get("closed") or []:
        key = str(d).strip()[:3].title()
        if key in WEEKDAYS:
            out.add(key)
    return out


def path_km(points):
    return sum(haversine(points[i], points[i + 1]) for i in range(len(points) - 1))


def two_opt(points, fixed_ends):
    """Best single segment reversal, returning (i, j, km_saved). Interior only."""
    lo = 1 if fixed_ends else 0
    hi = len(points) - 1 if fixed_ends else len(points)
    best = (None, None, 0.0)
    base = path_km(points)
    for i in range(lo, hi - 1):
        for j in range(i + 1, hi):
            trial = points[:i] + points[i:j + 1][::-1] + points[j + 1:]
            saved = base - path_km(trial)
            if saved > best[2]:
                best = (i, j, saved)
    return best


def check_day(day, walk_kmh, buffer_min):
    """Return a list of (severity, check, message)."""
    out = []
    label = day.get("date") or day.get("title") or "day"
    stops = day.get("stops") or []
    if not stops:
        return [("error", "empty", "%s has no stops" % label)]

    weekday = None
    if day.get("date"):
        try:
            weekday = WEEKDAYS[date.fromisoformat(str(day["date"])).weekday()]
        except ValueError:
            out.append(("warn", "date", "%s is not an ISO date, closing days unchecked" % day["date"]))

    # 1. Open on the day, and open long enough to be worth the stop.
    for s in stops:
        name = s.get("name", "unnamed stop")
        if weekday and weekday in closed_weekdays(s):
            out.append(("error", "closed", "%s is closed on %s" % (name, weekday)))
        ranges, at = parse_hours(s.get("hours")), parse_time(s.get("at"))
        if ranges and at is not None:
            window = next((r for r in ranges if r[0] <= at < r[1]), None)
            if window is None:
                out.append(("error", "closed",
                            "%s at %s is outside opening hours (%s)"
                            % (name, clock(at), s.get("hours"))))
            else:
                leave = at + int(s.get("dwell") or 0)
                if leave > window[1]:
                    out.append(("error", "closed",
                                "%s closes at %s, %d min before the planned %d min are up"
                                % (name, clock(window[1]), leave - window[1],
                                   int(s.get("dwell") or 0))))

    # 2. Does the clock hold, and do anchors keep their buffer.
    prev = None
    for s in stops:
        at, dwell = parse_time(s.get("at")), int(s.get("dwell") or 0)
        name = s.get("name", "unnamed stop")
        if prev and at is not None:
            leave, km = prev[1], None
            if s.get("travel_min") is not None:
                move, mode = float(s["travel_min"]), "given"
            elif s.get("coords") and prev[2]:
                km = haversine(prev[2], s["coords"])
                move, mode = travel_minutes(km, walk_kmh)
            else:
                move, mode = None, None
            if move is not None and leave is not None:
                arrive = leave + move
                slack = at - arrive
                need = buffer_min * 2 if s.get("anchor") else 0
                if slack < 0:
                    out.append(("error", "tight link",
                                "%s to %s: leaving %s, %d min %s, arrives %s, %d min late"
                                % (prev[0], name, clock(int(leave)), round(move), mode,
                                   clock(int(arrive)), round(-slack))))
                elif slack < need:
                    out.append(("error", "anchor buffer",
                                "%s is an anchor with %d min of slack, %d wanted"
                                % (name, round(slack), need)))
                elif slack < buffer_min and km is not None and km > 0.4:
                    out.append(("warn", "tight link",
                                "%s to %s leaves %d min of slack"
                                % (prev[0], name, round(slack))))
        if at is not None:
            prev = (name, at + dwell, s.get("coords"))
        elif prev:
            prev = (name, None, s.get("coords"))

    # 3. Dwell plus travel against the hours actually available.
    coords = [s["coords"] for s in stops if s.get("coords")]
    home = day.get("home_base")
    dwell_total = sum(int(s.get("dwell") or 0) for s in stops)
    move_total = 0.0
    if len(coords) > 1:
        legs = [home] + coords + [home] if home else coords
        for i in range(len(legs) - 1):
            move_total += travel_minutes(haversine(legs[i], legs[i + 1]), walk_kmh)[0]
    start = parse_time(day.get("day_start")) or parse_time(stops[0].get("at"))
    end = parse_time(day.get("day_end"))
    if end is None and parse_time(stops[-1].get("at")) is not None:
        end = parse_time(stops[-1]["at"]) + int(stops[-1].get("dwell") or 0)
    if start is not None and end is not None and (dwell_total or move_total):
        available = end - start
        used = dwell_total + move_total
        if used > available:
            out.append(("error", "day overflow",
                        "%d min of stops and travel in a %d min day, cut about %d min"
                        % (round(used), available, round(used - available))))
        elif used > available * 0.9:
            out.append(("warn", "day overflow",
                        "%d of %d min booked, nothing left for a queue or a coffee"
                        % (round(used), available)))

    # 4. Zig-zag: name the detour, then the reversal that fixes it.
    if len(coords) >= 3:
        legs = [home] + coords + [home] if home else coords
        names = [s.get("name", "?") for s in stops if s.get("coords")]
        for i in range(1, len(coords) - 1):
            detour = (haversine(coords[i - 1], coords[i]) + haversine(coords[i], coords[i + 1])
                      - haversine(coords[i - 1], coords[i + 1]))
            if detour > 3.0:
                out.append(("warn", "detour",
                            "%s adds %.1f km between %s and %s, move it or drop it"
                            % (names[i], detour, names[i - 1], names[i + 1])))
        i, j, saved = two_opt(legs, fixed_ends=bool(home))
        total = path_km(legs)
        if i is not None and saved > 1.5 and total and saved / total > 0.15:
            lo = i - 1 if home else i
            hi = j - 1 if home else j
            out.append(("warn", "zig-zag",
                        "%.1f km of %.1f km comes back on itself, visiting %s to %s in "
                        "reverse saves %.1f km, check hours before applying"
                        % (saved, total, names[max(lo, 0)], names[min(hi, len(names) - 1)], saved)))
    return out


def main():
    ap = argparse.ArgumentParser(description="Check stop order, opening days and day length.")
    ap.add_argument("path", help="JSON file: one day, a list of days, or {\"days\": [...]}")
    ap.add_argument("--walk", type=float, default=4.5, help="Walking speed km/h (default 4.5)")
    ap.add_argument("--buffer", type=int, default=15,
                    help="Minutes of slack a link should keep; anchors want double")
    ap.add_argument("--strict", action="store_true", help="Warnings count as errors too")
    args = ap.parse_args()

    src = Path(args.path)
    if not src.is_file():
        sys.exit("No such file: %s" % src)
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        sys.exit("%s is not valid JSON: %s" % (src, e))

    days = data.get("days") if isinstance(data, dict) and "days" in data else data
    if isinstance(days, dict):
        days = [days]
    if not isinstance(days, list):
        sys.exit("Expected a day object, a list of days, or {\"days\": [...]}")

    print("Checking %s, %d day(s)" % (src, len(days)))
    errors = 0
    for day in days:
        label = str(day.get("date") or day.get("title") or "day")
        for severity, check, message in check_day(day, args.walk, args.buffer):
            if severity == "error" or args.strict:
                errors += 1
            tag = "ERROR" if (severity == "error" or args.strict) else "warn"
            print("  %-11s %-6s %-14s %s" % (label, tag, check, message))

    if errors:
        print("\n%d problem(s) in the order. Reordering is free and usually fixes more"
              " than\ncutting stops does, so try the sequence before dropping anything."
              % errors)
        return 1
    print("Order holds: nothing shut, nothing late, no day over its hours.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
