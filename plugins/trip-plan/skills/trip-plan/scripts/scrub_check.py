#!/usr/bin/env python3
"""
scrub_check.py - flag personal data, access codes and booking references in an itinerary.

A trip plan gets emailed, synced to a phone, opened on a train, and published to a
public URL. It should read like a guidebook page, not like a boarding pass. This
scans the HTML (or markdown) for things that shouldn't be in it and prints where
they are, with the matched value masked so the report itself stays safe to paste.

Usage:
    python3 scripts/scrub_check.py itinerary.html
    python3 scripts/scrub_check.py itinerary.html --strict   # warnings block too

Exit codes: 0 clean (warnings allowed), 1 blocking findings present.

It's a pattern matcher, so it catches shapes, not meaning. It won't spot a
traveller's full name or a home address. Read the plan as well as running this.
"""

import argparse
import re
import sys
from pathlib import Path

BOOKING_WORDS = (
    r"booking|confirmation|reservation|record\s*locator|PNR|ticket\s*(?:no|number|#)"
    r"|reference\s*(?:no|number|code|#)|order\s*(?:no|number|#)|voucher|e-?ticket"
    r"|frequent\s*flyer|loyalty|membership\s*(?:no|number|#)"
)
SECRET_WORDS = (
    r"PIN|passcode|pass\s*code|access\s*code|door\s*code|entry\s*code|key\s*?code"
    r"|lockbox|lock\s*box|key\s*safe|wi-?fi\s*password|password|gate\s*code"
)
IDENTITY_WORDS = (
    r"passport|driver'?s?\s*licen[cs]e|national\s*insurance|BSN|SSN"
    r"|date\s*of\s*birth|DOB|ID\s*number|insurance\s*policy|policy\s*(?:no|number|#)"
)

# A keyword on its own is a note, not a leak. "Bring passport for the tax refund"
# and "code in your password manager" are the phrasings SKILL.md asks for, and an
# earlier version of this file blocked both, which taught people to reach for
# --allow-pii. Blocking now needs a keyword *and* something value-shaped near it:
# 4+ alphanumerics carrying at least one digit. The keyword alone drops to review.
VALUE = r"(?:\b(?=[A-Za-z0-9]{4,}\b)(?=[A-Za-z0-9]*\d)[A-Za-z0-9]{4,}\b)"

RULES = [
    ("email address", "block", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("IBAN", "block", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("identity number", "block",
     re.compile(r"(?i:\b(?:%s)\b)[^<\n]{0,20}?%s" % (IDENTITY_WORDS, VALUE))),
    ("access code or password", "block",
     re.compile(r"(?i:\b(?:%s)\b)[^<\n]{0,20}?%s" % (SECRET_WORDS, VALUE))),
    # The keyword is case-insensitive, the code that follows is not: real
    # references are upper case and usually carry a digit, so "reservation
    # required" stays quiet while "reservation X7K9PQ" does not.
    ("booking reference", "block",
     re.compile(r"(?i:\b(?:%s)\b)[^<\n]{0,30}?"
                r"(?:\b(?=[A-Z0-9]{5,}\b)(?=[A-Z0-9]*\d)[A-Z0-9]{5,}\b|\b[A-Z]{6,}\b)"
                % BOOKING_WORDS)),
    ("identity wording", "review", re.compile(r"(?i)\b(?:%s)\b" % IDENTITY_WORDS)),
    ("secret wording", "review", re.compile(r"(?i)\b(?:%s)\b" % SECRET_WORDS)),
    ("booking wording", "review", re.compile(r"(?i)\b(?:%s)\b" % BOOKING_WORDS)),
    ("long number", "review", re.compile(r"(?<![\d.,])\d{8,}(?![\d.,])")),
    ("phone number", "review", re.compile(r"\+\d[\d\s().-]{7,}\d|\(\d{3}\)\s?\d{3}[-\s]?\d{4}")),
    ("record locator shape", "review",
     re.compile(r"(?<![#\w])(?=[A-Z0-9]{6}(?![\w-]))(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]{6}")),
]

# Card numbers get their own pass so the Luhn check can confirm them.
CARD_RE = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")

FIXES = {
    "email address": 'drop it, or write "details in your email"',
    "IBAN": "drop it, payment details don't belong in an itinerary",
    "identity number": 'keep the fact, drop the number: "bring passport"',
    "access code or password": 'keep the fact, drop the code: "code in your password manager"',
    "booking reference": 'write "booked, ref in email" and leave the code out',
    "identity wording": "fine on its own, check no number follows it",
    "secret wording": "fine on its own, check no code follows it",
    "booking wording": "fine on its own, check no code follows it",
    "long number": "check this isn't a booking, ticket or document number",
    "phone number": "a venue's public number is fine, a traveller's is not",
    "record locator shape": "check this isn't a PNR or confirmation code",
    "payment card number": "drop it, card numbers never belong here",
}


def luhn(digits):
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


# Each blocking category and the keyword-only note it makes redundant.
PARENT = {
    "access code or password": "secret wording",
    "identity number": "identity wording",
    "booking reference": "booking wording",
}


def blunt(v):
    if len(v) <= 4:
        return v[0] + "*" * (len(v) - 1) if v else v
    return v[:2] + "*" * (len(v) - 4) + v[-2:]


# Keyword rules match a phrase, so masking the whole thing hides the one word that
# tells you what to go fix. Mask the value inside it and leave the words alone.
CONTEXT_RULES = ("identity number", "access code or password", "booking reference",
                 "identity wording", "secret wording", "booking wording")
VALUE_TOKEN = re.compile(r"\S*\d\S*|\b[A-Z0-9]{5,}\b")


def mask(category, value):
    v = " ".join(value.split())
    if category in CONTEXT_RULES:
        v = VALUE_TOKEN.sub(lambda m: blunt(m.group(0)), v)
        return v if len(v) <= 40 else v[:37] + "..."
    return blunt(v)


def scan_text(text):
    """Return a list of findings: (line_no, severity, category, masked_snippet)."""
    findings = []
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        for category, severity, rx in RULES:
            for m in rx.finditer(line):
                findings.append((i, severity, category, mask(category, m.group(0))))
        for m in CARD_RE.finditer(line):
            digits = re.sub(r"\D", "", m.group(0))
            if 13 <= len(digits) <= 19 and luhn(digits):
                findings.append((i, "block", "payment card number",
                                 mask("payment card number", m.group(0))))

    # Distinct values stay, repeats go. Keyed on the snippet as well as the line,
    # because a minified itinerary is one line and dropping to one finding per
    # category would hide everything after the first hit. Capped so a bad file
    # gives a readable report instead of a wall.
    seen, unique = set(), []
    for f in findings:
        key = (f[0], f[2], f[3])
        if key in seen:
            continue
        seen.add(key)
        if sum(1 for u in unique if u[0] == f[0] and u[2] == f[2]) >= 5:
            continue
        unique.append(f)

    # "check: secret wording" under "BLOCK: access code" says nothing new.
    blocked = {(f[0], PARENT.get(f[2])) for f in unique if f[1] == "block"}
    return [f for f in unique if (f[0], f[2]) not in blocked]


def report(findings, strict=False, allow=()):
    allow = {a.strip().lower() for a in allow}
    blocking = [f for f in findings
                if (f[1] == "block" or strict) and f[2].lower() not in allow]
    if not findings:
        print("Clean: no personal data, access codes or booking references found.")
        return 0

    for line_no, severity, category, snippet in sorted(findings):
        if category.lower() in allow:
            tag = "allow"
        else:
            tag = "BLOCK" if (severity == "block" or strict) else "check"
        print("  line %-5d %-6s %-24s %-28s %s"
              % (line_no, tag, category, snippet, FIXES.get(category, "")))

    if blocking:
        print("\n%d blocking finding(s). An itinerary carries locations, times, prices and"
              % len(blocking))
        print("notes. Booking codes, door codes and personal details live in the traveller's")
        print("email or password manager, not in a file that gets shared and published.")
        return 1
    print("\nNo blocking findings. Confirm the flagged items are public venue details.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Flag PII and secrets in an itinerary file.")
    ap.add_argument("path", help="HTML or markdown itinerary to scan")
    ap.add_argument("--strict", action="store_true", help="treat warnings as blocking too")
    ap.add_argument("--allow", action="append", default=[], metavar="CATEGORY",
                    help="stop one category from blocking, e.g. --allow 'phone number'. "
                         "Repeatable. Use after checking each hit, not instead of.")
    args = ap.parse_args()

    src = Path(args.path)
    if not src.is_file():
        sys.exit("No such file: %s" % src)
    known = {c.lower() for c, _, _ in RULES} | {"payment card number"}
    for a in args.allow:
        if a.strip().lower() not in known:
            sys.exit("Unknown category %r. Known: %s" % (a, ", ".join(sorted(known))))
    print("Scanning %s" % src)
    text = src.read_text(encoding="utf-8", errors="replace")
    sys.exit(report(scan_text(text), args.strict, args.allow))


if __name__ == "__main__":
    main()
