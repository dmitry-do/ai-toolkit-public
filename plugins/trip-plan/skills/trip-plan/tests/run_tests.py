#!/usr/bin/env python3
"""
run_tests.py - fixtures for the two scripts that can fail quietly.

    python3 skills/trip-plan/tests/run_tests.py

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


@case("route: half-filled days are checked, not rejected")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "sparse.json"
        f.write_text('{"date": "2026-11-27", "stops": [{"name": "Somewhere"}]}')
        code, out = run("route_check.py", f)
        expect(code == 0, "a name-only stop should not fail:\n%s" % out)


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
