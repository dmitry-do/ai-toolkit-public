#!/usr/bin/env python3
"""
run_tests.py - fixtures for the scripts that can fail quietly.

    python3 <this skill's folder>/tests/run_tests.py

Each case is a real incident rather than a synthetic one. The scrub_safe fixture
is the phrasing SKILL.md tells the model to write, which an earlier build of the
scanner blocked outright, so the only way forward was --allow-pii. The day_broken
fixture is a Monday museum with four late arrivals in a row. The build cases cover
--out pointing at the directory holding the itinerary, which used to delete it.

No dependencies, no framework. Exit 0 all passed, 1 otherwise.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT.parent / "scripts"
FIXTURES = ROOT / "fixtures"

CASES = []


def case(name):
    def wrap(fn):
        CASES.append((name, fn))
        return fn
    return wrap


def run(script, *args):
    r = subprocess.run([sys.executable, str(SCRIPTS / script)] + [str(a) for a in args],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def expect(condition, message):
    if not condition:
        raise AssertionError(message)


@case("scrub: the phrasing SKILL.md recommends does not block")
def _():
    code, out = run("scrub_check.py", FIXTURES / "scrub_safe.html")
    expect(code == 0, "safe fixture blocked the build:\n%s" % out)
    expect("BLOCK" not in out, "safe fixture produced a BLOCK:\n%s" % out)


@case("scrub: real codes and numbers still block")
def _():
    code, out = run("scrub_check.py", FIXTURES / "scrub_leaks.html")
    expect(code == 1, "leaky fixture passed:\n%s" % out)
    for wanted in ("access code or password", "identity number", "booking reference",
                   "payment card number", "email address"):
        expect(wanted in out, "missed %s:\n%s" % (wanted, out))


@case("scrub: the masked report never prints the value")
def _():
    _, out = run("scrub_check.py", FIXTURES / "scrub_leaks.html")
    for secret in ("4829", "hunter2trip", "X1234567", "X7K9PQ", "4111111111111111"):
        expect(secret not in out, "%s appeared unmasked in the report" % secret)


@case("scrub: --allow narrows one category without disarming the rest")
def _():
    code, out = run("scrub_check.py", FIXTURES / "scrub_leaks.html", "--allow", "email address")
    expect(code == 1, "--allow email address should not clear the card number")
    expect("allow" in out, "allowed category not marked in the report:\n%s" % out)
    code, _ = run("scrub_check.py", FIXTURES / "scrub_leaks.html", "--allow", "nonsense")
    expect(code != 0, "an unknown --allow category should be rejected")


@case("scrub: a .md file flags prose em dashes and semicolons, not URLs or code")
def _():
    code, out = run("scrub_check.py", FIXTURES / "style_plan.md")
    expect(code == 0, "style hits should not block:\n%s" % out)
    expect(out.count("em dash") == 1, "expected one em dash hit:\n%s" % out)
    expect(out.count("semicolon ") == 1, "expected one semicolon hit:\n%s" % out)
    code, out = run("scrub_check.py", FIXTURES / "style_plan.md", "--strict")
    expect(code == 1, "--strict should block on style hits:\n%s" % out)
    code, out = run("scrub_check.py", FIXTURES / "style_plan.md", "--no-style")
    expect("em dash" not in out, "--no-style still checked style:\n%s" % out)


@case("scrub: a .md file over 65,536 bytes blocks, one at the limit passes")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "plan.md"
        f.write_bytes(b"a" * 65536)
        code, out = run("scrub_check.py", f)
        expect(code == 0, "a file at exactly 65,536 bytes blocked:\n%s" % out)
        f.write_bytes(b"a" * 65537)
        code, out = run("scrub_check.py", f)
        expect(code == 1 and "file size" in out, "a 65,537-byte file passed:\n%s" % out)
        code, out = run("scrub_check.py", f, "--max-bytes", "0")
        expect(code == 0, "--max-bytes 0 should turn the limit off:\n%s" % out)
        h = Path(tmp) / "plan.html"
        h.write_bytes(b"a" * 70000)
        code, out = run("scrub_check.py", h)
        expect(code == 0, "HTML should have no default size limit:\n%s" % out)


@case("route: a day that holds up passes")
def _():
    code, out = run("route_check.py", FIXTURES / "day_clean.json")
    expect(code == 0, "clean day reported errors:\n%s" % out)
    expect("ERROR" not in out, "clean day produced an ERROR:\n%s" % out)


@case("route: closing day, late links, anchor buffer and overflow all caught")
def _():
    code, out = run("route_check.py", FIXTURES / "day_broken.json")
    expect(code == 1, "broken day passed:\n%s" % out)
    for wanted in ("closed", "tight link", "anchor buffer", "day overflow", "zig-zag"):
        expect(wanted in out, "missed %s:\n%s" % (wanted, out))
    expect("closed on Mon" in out, "missed the Monday closure:\n%s" % out)


@case("route: a day trip with real train times does not overflow")
def _():
    # The Osaka trip hit this on every intercity day: travel_min held the real
    # train time, but the day total re-estimated 75 km at city-transit speed.
    code, out = run("route_check.py", FIXTURES / "day_trip.json")
    expect(code == 0, "day trip with travel_min and return_min failed:\n%s" % out)
    expect("day overflow" not in out, "false overflow on a day trip:\n%s" % out)


@case("route: a long leg without travel_min warns instead of guessing")
def _():
    import json
    with tempfile.TemporaryDirectory() as tmp:
        day = json.loads((FIXTURES / "day_trip.json").read_text())
        day.pop("return_min")
        day["stops"][0].pop("travel_min")
        f = Path(tmp) / "no_legs.json"
        f.write_text(json.dumps(day))
        code, out = run("route_check.py", f)
        expect(code == 0, "missing travel_min should warn, not fail:\n%s" % out)
        expect(out.count("long leg") == 2, "expected two long-leg warnings:\n%s" % out)


@case("route: half-filled days are checked, not rejected")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "sparse.json"
        f.write_text('{"date": "2026-11-27", "stops": [{"name": "Somewhere"}]}')
        code, out = run("route_check.py", f)
        expect(code == 0, "a name-only stop should not fail:\n%s" % out)


@case("sun: Osaka times match the plan, polar night says none")
def _():
    # 06:43 and 16:47 are the times the Osaka plan carried for Nov 28 (astral).
    code, out = run("sun_times.py", "--tz", "Asia/Tokyo", "--date", "2026-11-28",
                    "--place", "Osaka", "34.6937", "135.5023")
    expect(code == 0 and "06:43" in out and "16:47" in out, "Osaka times wrong:\n%s" % out)
    code, out = run("sun_times.py", "--tz", "Europe/Oslo", "--date", "2026-12-21",
                    "--place", "Tromso", "69.65", "18.96")
    expect("none" in out, "polar night should print none:\n%s" % out)


PLAN = """# 🇯🇵 Japan (v37)

## Nov 29
- [Mikimoto](https://www.google.com/maps/search/?api=1&query=Mikimoto%20Pearl%20Island%20Toba%20Mie&query_place_id=ChIJabc) 08:30-17:00
- [Minato Shokudo](https://www.google.com/maps/search/?api=1&query=Minato%20Shokudo&query_place_id=ChIJdef) lunch
- Dinner near [Mikimoto](https://www.google.com/maps/search/?api=1&query=Mikimoto%20Pearl%20Island%20Toba%20Mie&query_place_id=ChIJabc)
"""


@case("edit: writes v38, bumps the title, reports a lost repeat link")
def _():
    import json
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "Japan_v37_Telegram.md"
        src.write_text(PLAN)
        edits = Path(tmp) / "edits.json"
        edits.write_text(json.dumps([
            {"old": "08:30-17:00", "new": "08:30-17:00, ¥1,650"},
            {"old": "Dinner near [Mikimoto](https://www.google.com/maps/search/?api=1"
                    "&query=Mikimoto%20Pearl%20Island%20Toba%20Mie&query_place_id=ChIJabc)",
             "new": "Dinner near Mikimoto"},
        ]))
        code, out = run("edit_plan.py", src, edits)
        dst = Path(tmp) / "Japan_v38_Telegram.md"
        expect(code == 0 and dst.is_file(), "v38 not written:\n%s" % out)
        text = dst.read_text()
        expect(text.startswith("# 🇯🇵 Japan (v38)"), "title not bumped:\n%s" % text[:40])
        expect("¥1,650" in text, "edit not applied")
        expect("repeat lost a copy" in out, "lost repeat link not reported:\n%s" % out)
        expect(src.read_text() == PLAN, "the source version was changed")


@case("edit: an edit that does not match exactly once writes nothing")
def _():
    import json
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "plan_v3.md"
        src.write_text(PLAN)
        edits = Path(tmp) / "edits.json"
        edits.write_text(json.dumps([{"old": "Mikimoto](", "new": "X]("}]))
        code, out = run("edit_plan.py", src, edits)
        expect(code == 1, "an ambiguous edit was applied:\n%s" % out)
        expect(not (Path(tmp) / "plan_v4.md").exists(), "a file was written anyway")


@case("edit: --compact-links shrinks Maps links and keeps every place ID")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "plan_v1.md"
        src.write_text(PLAN)
        code, out = run("edit_plan.py", src, "--compact-links")
        text = (Path(tmp) / "plan_v2.md").read_text()
        expect(code == 0, "compaction failed:\n%s" % out)
        expect("%20" not in text and "query=Mikimoto+Pearl+Island&" in text,
               "query not shortened:\n%s" % text)
        expect(text.count("query_place_id=ChIJabc") == 2, "a place ID was lost")
        expect(len(text.encode()) < len(PLAN.encode()), "nothing was saved")
        expect("removed" not in out, "compaction was reported as removed links:\n%s" % out)


@case("build: --out cannot delete the directory holding the itinerary")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        proj.mkdir()
        html = proj / "itinerary.html"
        shutil.copy(FIXTURES / "scrub_safe.html", html)
        (proj / "notes.md").write_text("keep me")
        for target in (".", ".."):
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_pwa.py"),
                                "--html", "itinerary.html", "--out", target],
                               capture_output=True, text=True, cwd=proj)
            expect(r.returncode != 0, "--out %s was allowed" % target)
        expect(html.is_file(), "the itinerary was deleted")
        expect((proj / "notes.md").is_file(), "an unrelated file was deleted")


@case("build: a foreign non-empty directory is refused, its own output is reused")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        (proj / "other").mkdir(parents=True)
        (proj / "other" / "x.txt").write_text("mine")
        shutil.copy(FIXTURES / "scrub_safe.html", proj / "itinerary.html")
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_pwa.py"),
                            "--html", "itinerary.html", "--out", "other"],
                           capture_output=True, text=True, cwd=proj)
        expect(r.returncode != 0, "a directory we did not build was cleared")
        expect((proj / "other" / "x.txt").is_file(), "someone else's file was deleted")
        for attempt in range(2):
            r = subprocess.run([sys.executable, str(SCRIPTS / "build_pwa.py"),
                                "--html", "itinerary.html", "--out", "dist"],
                               capture_output=True, text=True, cwd=proj)
            expect(r.returncode == 0, "build %d failed:\n%s" % (attempt, r.stdout + r.stderr))
        for f in ("index.html", "manifest.webmanifest", "sw.js",
                  "icons/icon-192.png", "icons/icon-maskable-512.png"):
            expect((proj / "dist" / f).is_file(), "missing %s" % f)
        expect((proj / "dist.zip").is_file(), "no zip written")


@case("build: injection is idempotent and the worker guards what it caches")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        proj.mkdir()
        shutil.copy(FIXTURES / "scrub_safe.html", proj / "itinerary.html")
        subprocess.run([sys.executable, str(SCRIPTS / "build_pwa.py"),
                        "--html", "itinerary.html", "--out", "dist"],
                       capture_output=True, text=True, cwd=proj)
        subprocess.run([sys.executable, str(SCRIPTS / "build_pwa.py"),
                        "--html", "dist/index.html", "--out", "dist2"],
                       capture_output=True, text=True, cwd=proj)
        rebuilt = (proj / "dist2" / "index.html").read_text()
        expect(rebuilt.count("trip-plan:pwa-head:start") == 1,
               "rebuilding duplicated the injected head block")
        sw = (proj / "dist" / "sw.js").read_text()
        expect("res.ok" in sw and "res.redirected" in sw,
               "the worker caches navigation responses without checking them")


@case("build: a leaky itinerary stops the build before anything is written")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "proj"
        proj.mkdir()
        shutil.copy(FIXTURES / "scrub_leaks.html", proj / "itinerary.html")
        r = subprocess.run([sys.executable, str(SCRIPTS / "build_pwa.py"),
                            "--html", "itinerary.html", "--out", "dist"],
                           capture_output=True, text=True, cwd=proj)
        expect(r.returncode != 0, "a leaky file built anyway")
        expect(not (proj / "dist").exists(), "dist was created despite the block")


def main():
    failed = []
    for name, fn in CASES:
        try:
            fn()
            print("  pass  %s" % name)
        except AssertionError as e:
            failed.append(name)
            print("  FAIL  %s\n        %s" % (name, str(e).replace("\n", "\n        ")))
    print("\n%d passed, %d failed" % (len(CASES) - len(failed), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
