#!/usr/bin/env python3
"""Screenshots for the plugin READMEs.

diagram.py and terminal.py draw. This one photographs: it renders real files in
headless Chrome and composes the captures with Pillow, so the picture of an
itinerary is the itinerary, not an illustration of one.

    python3 scripts/docs-assets/shots.py                # every shot
    python3 scripts/docs-assets/shots.py trip-plan      # just one

Output goes to docs/assets/, not into any plugin: a screenshot is documentation,
and a plugin directory is downloaded on install. The READMEs reference them by
their public raw.githubusercontent.com URL, so the same image renders from the
private repo, the public mirror, and anywhere else the README is read.

Needs Google Chrome. build.py doesn't, which is why this is a separate entry
point rather than another step inside it.

Two things are staged for the camera, both in a throwaway copy of the file:

- the clock is pinned, so the itinerary shows the state it has on the 27th
  rather than the state it has today, and
- Chrome inherits macOS dark mode from the system, so the light palette (the
  page's own first `:root` block) is re-appended to win the cascade.

Nothing else is touched, and the committed file is never modified.

The trip-plan sample lives in `samples/` beside this file and is gitignored: it
is docs input, not a plugin fixture or a shipped example. That makes
`docs/assets/trip-plan-itinerary.png` a committed artifact rather than a
reproducible one — regenerating it needs those files back, and the last version
of them is in git history (`git log -- scripts/docs-assets/samples`).
"""
from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import theme as T  # noqa: E402

SCALE = 3          # device pixel ratio: captures and canvas share it
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PLUGINS = ROOT / "plugins"
SAMPLES = HERE / "samples"   # generator input, deliberately outside the plugins
ASSETS = ROOT / "docs" / "assets"   # published images, also outside the plugins

INDIGO = "#33418F"   # the itinerary's own accent, so the pane matches the phone


def _s(v):
    if isinstance(v, (tuple, list)):
        return tuple(int(round(x * SCALE)) for x in v)
    return int(round(v * SCALE))


# --- headless Chrome -------------------------------------------------------

# Chrome's minimum window width on macOS is 500 CSS px, so a 402 px phone shot
# taken with --window-size=402 lays out at 500 and photographs the left 402 of
# it, which silently crops every line. The page goes in an iframe of exactly the
# width we want instead, and the capture is cropped to the iframe.
FRAME = """<!doctype html><meta charset="utf-8">
<style>html,body{margin:0;padding:0;background:#ffffff;overflow:hidden}
iframe{display:block;border:0;width:%dpx;height:%dpx}</style>
<iframe src="%s"></iframe>
"""


_PROFILE = None


def _profile_dir():
    """One throwaway Chrome profile for the whole run, never the user's."""
    global _PROFILE
    if _PROFILE is None:
        _PROFILE = tempfile.mkdtemp(prefix="docs-chrome-")
    return _PROFILE


def shoot(target, width, height, scale=SCALE, wait=40):
    """Render a local HTML file at an exact CSS size. Returns a PIL image."""
    if not os.path.exists(CHROME):
        sys.exit("Google Chrome not found at %s (shots.py needs it)" % CHROME)
    target = pathlib.Path(target).resolve()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="docs-shot-"))
    try:
        frame = tmp / "frame.html"
        frame.write_text(FRAME % (width, height, target.as_uri()), encoding="utf-8")
        out = tmp / "shot.png"
        cmd = [
            CHROME, "--headless", "--disable-gpu", "--hide-scrollbars",
            "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-sync", "--disable-extensions",
            "--user-data-dir=%s" % _profile_dir(),
            "--force-device-scale-factor=%d" % scale,
            "--window-size=%d,%d" % (max(width, 520), height + 2),
            "--virtual-time-budget=3000",
            "--screenshot=%s" % out, frame.as_uri(),
        ]
        # Headless Chrome writes the PNG and then sometimes doesn't exit, so
        # wait on the file rather than on the process, and kill it either way.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        size, stable = -1, 0
        for _ in range(int(wait / 0.25)):
            if out.exists():
                now = out.stat().st_size
                stable = stable + 1 if now == size and now else 0
                size = now
                if stable >= 2:
                    break
            if proc.poll() is not None and not out.exists():
                break
            time.sleep(0.25)
        proc.kill()
        proc.communicate()
        if not out.exists():
            sys.exit("Chrome wrote no screenshot for %s" % target)
        img = Image.open(out).convert("RGB")
        img.load()
        return img.crop((0, 0, width * scale, height * scale))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def stage_itinerary(src, when=(2026, 12, 27, 13, 20)):
    """A throwaway copy with the clock pinned and the light palette forced."""
    html = pathlib.Path(src).read_text(encoding="utf-8")
    light = re.search(r":root\s*\{.*?\}", html, re.S)
    if not light:
        sys.exit("%s has no :root block to force light with" % src)
    inject = """
<script>
(function () {
  var FIXED = new Date(%d, %d, %d, %d, %d, 0).getTime();
  var _D = Date;
  function D() {
    if (arguments.length === 0) { return new _D(FIXED); }
    return new (Function.prototype.bind.apply(
      _D, [null].concat([].slice.call(arguments))))();
  }
  D.now = function () { return FIXED; };
  D.parse = _D.parse; D.UTC = _D.UTC; D.prototype = _D.prototype;
  window.Date = D;
  // The page scrolls today's card into view on load. Old headless Chrome
  // doesn't repaint what the scroll uncovers, so the shot starts at the top.
  Element.prototype.scrollIntoView = function () {};
})();
</script>
<style>%s</style>
""" % (when[0], when[1] - 1, when[2], when[3], when[4], light.group(0))
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="docs-stage-")) / "staged.html"
    tmp.write_text(html.replace("</head>", inject + "</head>", 1), encoding="utf-8")
    return tmp


# --- text panes ------------------------------------------------------------

PANE_CSS = """
html,body{margin:0;padding:0;background:#fff}
body{padding:16px 18px;font:12.5px/1.66 Menlo,'SF Mono',monospace;color:%(ink)s}
pre{margin:0;white-space:pre-wrap;word-wrap:break-word;tab-size:2}
.h{color:%(accent)s;font-weight:700}
.s{color:%(accent)s}
.b{color:%(ink)s;font-weight:700}
.m{color:%(muted)s}
.c{color:%(green)s;font-weight:700}
.r{color:%(line)s}
"""

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _markdown_line(raw):
    line = _esc(raw)
    if raw.startswith("#"):
        return '<span class="h">%s</span>' % line
    if raw.startswith(">"):
        return '<span class="m">%s</span>' % line
    if raw.startswith("---"):
        return '<span class="r">%s</span>' % line
    if raw.lstrip().startswith("- [ ]"):
        line = line.replace("- [ ]", '<span class="c">- [ ]</span>', 1)
    elif raw.startswith(("\U0001F4CD", "\U0001F6B6", "⏱", "\U0001F687",
                         "\U0001F686", "\U0001F6A1", "\U0001F68C", "\U0001F6A2")):
        return '<span class="m">%s</span>' % line
    return _MD_BOLD.sub(lambda m: '<span class="b">%s</span>' % m.group(1), line)


_SPEAKER = re.compile(r"^(\[\d{1,2}:\d{2}(?::\d{2})?\]\s*)?([A-Z][\w .'-]{1,28}:)")


def _transcript_line(raw):
    m = _SPEAKER.match(raw)
    if not m:
        return _esc(raw)
    stamp, who = m.group(1) or "", m.group(2)
    return '<span class="m">%s</span><span class="s">%s</span>%s' % (
        _esc(stamp), _esc(who), _esc(raw[len(m.group(0)):]))


def text_pane(lines, width, height, kind="md", accent=T.ACCENT):
    """Screenshot a block of source text laid out as a page of code."""
    render = _markdown_line if kind == "md" else _transcript_line
    body = "\n".join(render(ln) for ln in lines)
    css = PANE_CSS % {"ink": T.INK, "muted": T.MUTED, "accent": accent,
                      "green": T.GREEN, "line": T.LINE}
    page = ('<!doctype html><meta charset="utf-8"><style>%s</style><pre>%s</pre>'
            % (css, body))
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="docs-pane-")) / "pane.html"
    tmp.write_text(page, encoding="utf-8")
    try:
        return shoot(tmp, width, height)
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)


def excerpt(path, first, last):
    """Verbatim lines from a real file, 1-indexed and inclusive."""
    lines = pathlib.Path(path).read_text(encoding="utf-8").split("\n")
    return lines[first - 1:last]


# --- composition -----------------------------------------------------------

class Sheet:
    def __init__(self, width, height, title=None, subtitle=None):
        self.w, self.h = width, height
        self.img = Image.new("RGB", (_s(width), _s(height)), T.BG)
        self.d = ImageDraw.Draw(self.img)
        if title:
            self.d.text(_s((40, 28)), title, font=T.mono(_s(19), bold=True), fill=T.INK)
        if subtitle:
            self.d.text(_s((40, 55)), subtitle, font=T.sans(_s(15)), fill=T.MUTED)

    def shadow(self, box, radius, blur=7, alpha=42, dy=3):
        x0, y0, x1, y1 = _s(box)
        pad = _s(blur) * 3
        layer = Image.new("L", (self.img.width, self.img.height), 0)
        ImageDraw.Draw(layer).rounded_rectangle(
            (x0, y0 + _s(dy), x1, y1 + _s(dy)), radius=_s(radius), fill=alpha)
        layer = layer.filter(ImageFilter.GaussianBlur(_s(blur)))
        self.img.paste(Image.new("RGB", self.img.size, "#2A2318"), (0, 0), layer)
        del pad

    def paste(self, shot, x, y, radius=0, border=None):
        """Paste a capture, optionally with rounded corners and a hairline."""
        box = _s((x, y))
        if radius:
            mask = Image.new("L", shot.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (0, 0, shot.size[0] - 1, shot.size[1] - 1), radius=_s(radius), fill=255)
            self.img.paste(shot, box, mask)
        else:
            self.img.paste(shot, box)
        if border:
            w, h = shot.size[0] / SCALE, shot.size[1] / SCALE
            self.d.rounded_rectangle(_s((x, y, x + w - .5, y + h - .5)),
                                     radius=_s(radius), outline=border, width=_s(1))

    def card(self, box, radius=10, fill=T.SURFACE, outline=T.LINE, shadow=True):
        if shadow:
            self.shadow(box, radius)
        self.d.rounded_rectangle(_s(box), radius=_s(radius), fill=fill,
                                 outline=outline, width=_s(1))

    def label(self, x, y, text, size=13, colour=None, mono=False, bold=False):
        f = T.mono(_s(size), bold=bold) if mono else T.sans(_s(size), bold=bold)
        self.d.text(_s((x, y)), text, font=f, fill=colour or T.MUTED)
        return self.d.textlength(text, font=f) / SCALE

    def lines(self, x, y, rows, size=12.5, step=17, colour=None, mono=False):
        for row in rows:
            col = colour or T.MUTED
            if row.startswith("!"):
                row, col = row[1:], T.ACCENT
            self.label(x, y, row, size=size, colour=col, mono=mono)
            y += step
        return y

    def arrow(self, x0, y0, x1, colour=None):
        colour = colour or T.ACCENT
        self.d.line(_s((x0, y0, x1 - 7, y0)), fill=colour, width=_s(1.6))
        self.d.polygon([_s((x1, y0)), _s((x1 - 8, y0 - 4.5)), _s((x1 - 8, y0 + 4.5))],
                       fill=colour)

    def save(self, path):
        pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Kept at SCALE, not resized down: every capture in here is taken at the
        # same device pixel ratio, so downsampling would blur browser-rendered
        # text that is already antialiased. GitHub scales it to the column width
        # and the extra pixels are what stay crisp on a retina screen.
        self.img.save(path, optimize=True)
        return path


# --- the shots -------------------------------------------------------------

def trip_plan():
    """The Markdown plan beside the app that gets built out of it."""
    ex = SAMPLES
    missing = [f for f in ("tokyo-2026-12.md", "tokyo-2026-12.html") if not (ex / f).exists()]
    if missing:
        sys.exit(
            "trip-plan's sample week is not in this checkout: %s missing from %s.\n"
            "It's gitignored on purpose, so the committed screenshot can't be rebuilt\n"
            "from a clean clone. Recover it with:\n"
            "  git log --diff-filter=D -- scripts/docs-assets/samples\n"
            "  git checkout <that commit>^ -- scripts/docs-assets/samples"
            % (", ".join(missing), ex))
    # Midday on the 24th: three stops already done, so the shot carries the
    # TODAY tag, the folded past rows and the marker on the next stop at once.
    staged = stage_itinerary(ex / "tokyo-2026-12.html", when=(2026, 12, 24, 12, 0))
    try:
        phone = shoot(staged, 402, 820)
    finally:
        shutil.rmtree(staged.parent, ignore_errors=True)

    md = text_pane(excerpt(ex / "tokyo-2026-12.md", 79, 98), 460, 560,
                   kind="md", accent=INDIGO)

    s = Sheet(1000, 1000, "trip-plan",
              "one week, two artifacts: the Markdown you edit and the app you carry")

    s.label(40, 92, "tokyo-2026-12.md", size=13, colour=INDIGO, mono=True, bold=True)
    s.label(178, 93, "what the create phase hands you", size=12.5)
    s.card((40, 118, 500, 678))
    s.paste(md, 40, 118, radius=10)
    s.d.rounded_rectangle(_s((40, 118, 499.5, 677.5)), radius=_s(10),
                          outline=T.LINE, width=_s(1))

    s.card((40, 710, 500, 952))
    s.label(60, 728, "DELIVER", size=10.5, colour=INDIGO, bold=True)
    steps = [
        ("itinerary.html", T.INK,
         ["one self-contained file, everything inlined.",
          "Opens offline from Files, with no server."]),
        ("scrub_check.py", T.ACCENT,
         ["runs first, inside the build, and refuses to ship",
          "!booking codes, door codes or personal data"]),
        ("build_pwa.py", T.INK,
         ["manifest, service worker, icons, and dist.zip",
          "with index.html at the zip root"]),
        ("dist.zip", INDIGO,
         ["drop it on Cloudflare Drop and the plan installs",
          "to a home screen, offline-capable"]),
    ]
    y = 752
    for name, colour, body in steps:
        s.label(60, y, name, size=13, colour=colour, mono=True, bold=True)
        s.lines(60, y + 20, body, size=11.5, step=15)
        y += 50

    s.label(548, 92, "dist.zip, installed", size=13, colour=INDIGO, mono=True, bold=True)
    s.label(710, 93, "the same plan, on the phone", size=12.5)
    bezel = (542, 118, 968, 952)
    s.shadow(bezel, 30)
    s.d.rounded_rectangle(_s(bezel), radius=_s(30), fill="#2C2F36")
    s.paste(phone, 554, 124, radius=20)
    s.arrow(506, 392, 536)

    return s.save(str(ASSETS / "trip-plan-itinerary.png"))


def meeting_notes():
    """A transcript on the left, the summary it turns into on the right."""
    ex = PLUGINS / "meeting-notes" / "skills" / "meeting-notes" / "examples"
    src = ex / "rec" / "20260605 1400 Transcription [EN].txt"
    out_md = ex / "summaries" / "2026-06-05_onboarding-redesign-sync.md"

    left = text_pane(excerpt(src, 1, 10), 452, 620, kind="txt", accent=T.ACCENT)
    right = text_pane(excerpt(out_md, 1, 4) + ["", "\u2026", ""]
                      + excerpt(out_md, 12, 19), 452, 620, kind="md", accent=T.ACCENT)

    s = Sheet(1000, 800, "meeting-notes",
              "one transcript in, one summary out, in its own subagent")

    s.label(40, 92, "rec/20260605 1400 Transcription [EN].txt",
            size=12.5, colour=T.ACCENT, mono=True, bold=True)
    s.card((40, 118, 492, 738))
    s.paste(left, 40, 118, radius=10)
    s.d.rounded_rectangle(_s((40, 118, 491.5, 737.5)), radius=_s(10),
                          outline=T.LINE, width=_s(1))

    s.label(508, 92, "summaries/2026-06-05_onboarding-redesign-sync.md",
            size=12.5, colour=T.ACCENT, mono=True, bold=True)
    s.card((508, 118, 960, 738))
    s.paste(right, 508, 118, radius=10)
    s.d.rounded_rectangle(_s((508, 118, 959.5, 737.5)), radius=_s(10),
                          outline=T.LINE, width=_s(1))

    s.label(40, 754, "Timestamped, named speakers, and nothing in it worth pasting anywhere.",
            size=13)
    s.label(508, 754, "TLDR, decisions, and action items with a name and a date on each one.",
            size=13)

    return s.save(str(ASSETS / "meeting-notes-summary.png"))


BUILDERS = {
    "trip-plan": trip_plan,
    "meeting-notes": meeting_notes,
}


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(BUILDERS)
    unknown = [n for n in wanted if n not in BUILDERS]
    if unknown:
        sys.exit("no shot defined for: %s" % ", ".join(unknown))
    for name in wanted:
        path = BUILDERS[name]()
        print("  %-16s %4d KB  %s" % (name, os.path.getsize(path) // 1024,
                                      os.path.relpath(path, ROOT)))
