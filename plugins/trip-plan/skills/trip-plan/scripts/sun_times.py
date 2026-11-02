#!/usr/bin/env python3
"""
sun_times.py - sunrise and sunset per place and date, for the 🌅 and 🌇 lines.

Earlier sessions installed the astral package each time for this. This uses the
NOAA solar calculator (refraction and the sun's radius included, sea level)
and the Python standard library only. The result is within about 1 minute of astral (1.2 min at 64° north),
which is the precision a plan shows.

    python3 scripts/sun_times.py --tz Asia/Tokyo --from 2026-11-27 --to 2026-12-08 \
        --place Osaka 34.6937 135.5023 --place Koyasan 34.2130 135.5856
    python3 scripts/sun_times.py --tz Europe/Amsterdam --date 2026-11-07 \
        --place Wolfsburg 52.4227 10.7865

Output is one line per place and date, ready to paste:

    2026-11-28  Osaka      🌅 06:43 · 🌇 16:47

Show the times as data. Do not add a sentence that explains them.
"""

import argparse
import math
import sys
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python 3.8
    ZoneInfo = None

J2000 = 2451545.0
ZENITH = 90.833  # refraction plus the sun's radius, at sea level


def _sun_position(jd):
    """Declination (degrees) and equation of time (minutes), NOAA solar calculator."""
    jc = (jd - J2000) / 36525.0
    l0 = (280.46646 + jc * (36000.76983 + 0.0003032 * jc)) % 360
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    mr = math.radians(m)
    c = (math.sin(mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * mr) * (0.019993 - 0.000101 * jc) + math.sin(3 * mr) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * jc)
    app_long = l0 + c - 0.00569 - 0.00478 * math.sin(omega)
    mean_obliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq = math.radians(mean_obliq + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(obliq) * math.sin(math.radians(app_long)))
    y = math.tan(obliq / 2) ** 2
    l0r = math.radians(l0)
    eot = 4 * math.degrees(y * math.sin(2 * l0r) - 2 * e * math.sin(mr)
                           + 4 * e * y * math.sin(mr) * math.cos(2 * l0r)
                           - 0.5 * y * y * math.sin(4 * l0r) - 1.25 * e * e * math.sin(2 * mr))
    return math.degrees(decl), eot


def _event(day, lat, lon, sign):
    """Minutes after 00:00 UTC of `day` for sunrise (sign -1) or sunset (+1), or None."""
    jd0 = day.toordinal() + 1721424.5  # Julian date at 00:00 UTC
    minutes = 720 - 4 * lon  # first guess: solar noon
    for _ in range(3):  # recompute the sun's position at the event time
        decl, eot = _sun_position(jd0 + minutes / 1440.0)
        phi, d = math.radians(lat), math.radians(decl)
        cos_h = (math.cos(math.radians(ZENITH)) / (math.cos(phi) * math.cos(d))
                 - math.tan(phi) * math.tan(d))
        if not -1 <= cos_h <= 1:
            return None
        ha = math.degrees(math.acos(cos_h))
        minutes = 720 - 4 * lon - eot + sign * 4 * ha
    return minutes


def sun_times(day, lat, lon, tz=timezone.utc):
    """(sunrise, sunset) as aware datetimes for the local date `day`.

    lon is east-positive. These are the sunrise and sunset around the solar noon of
    that date, so a summer sunset after midnight can fall on the next calendar day.
    Either value is None in polar day or polar night.
    """
    out = []
    for sign in (-1, 1):
        m = _event(day, lat, lon, sign)
        out.append(None if m is None else
                   (datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
                    + timedelta(minutes=m)).astimezone(tz))
    return tuple(out)


def _fmt(t, day):
    if t is None:
        return "none"
    shift = (t.date() - day).days
    return t.strftime("%H:%M") + ("" if shift == 0 else " (%+d day)" % shift)


def main():
    ap = argparse.ArgumentParser(description="Sunrise and sunset per place and date.")
    ap.add_argument("--place", nargs=3, action="append", required=True,
                    metavar=("NAME", "LAT", "LON"), help="repeatable. LON is east-positive")
    ap.add_argument("--tz", required=True, help="IANA zone of the destination, e.g. Asia/Tokyo")
    ap.add_argument("--date", help="one date, YYYY-MM-DD")
    ap.add_argument("--from", dest="start", help="first date, YYYY-MM-DD")
    ap.add_argument("--to", dest="end", help="last date, YYYY-MM-DD")
    args = ap.parse_args()

    if ZoneInfo is None:
        sys.exit("Needs Python 3.9 or later for time zones.")
    try:
        tz = ZoneInfo(args.tz)
    except Exception:
        sys.exit("Unknown time zone %r" % args.tz)
    if args.date:
        days = [date.fromisoformat(args.date)]
    elif args.start and args.end:
        a, b = date.fromisoformat(args.start), date.fromisoformat(args.end)
        days = [a + timedelta(d) for d in range((b - a).days + 1)]
    else:
        ap.error("give --date, or --from and --to")

    width = max(len(p[0]) for p in args.place)
    for d in days:
        for name, lat, lon in args.place:
            rise, set_ = sun_times(d, float(lat), float(lon), tz)
            print("%s  %-*s  🌅 %s · 🌇 %s" % (d, width, name, _fmt(rise, d), _fmt(set_, d)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
