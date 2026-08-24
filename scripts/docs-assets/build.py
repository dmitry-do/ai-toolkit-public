#!/usr/bin/env python3
"""Regenerate the README assets for every plugin.

    python3 scripts/docs-assets/build.py            # all plugins
    python3 scripts/docs-assets/build.py trip-plan  # just one

Writes docs/assets/<name>-how-it-works.png and docs/assets/<name>-demo.gif.

They live there, and not in plugins/<name>/docs/, because a plugin directory is
downloaded on install and an image nothing at runtime reads has no business in
it. The READMEs reference them by public URL.
"""
from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw  # noqa: E402

import spec_demos  # noqa: E402
import spec_diagrams  # noqa: E402
import theme  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ASSETS = ROOT / "docs" / "assets"


def _tofu_chars(font, chars):
    """Characters this font renders as an empty/undefined box."""
    def px(ch):
        img = Image.new("L", (40, 40), 0)
        ImageDraw.Draw(img).text((5, 5), ch, font=font, fill=255)
        return bytes(img.getdata())
    blank = px("")
    return sorted(c for c in chars if px(c) == blank)


def check_glyphs():
    """Both fonts are patchy outside ASCII; a tofu box in a committed PNG is
    invisible here and obvious on GitHub, so fail the build instead."""
    bad = False
    for module, font, label in (
        (spec_demos, theme.mono(16), "demos (Menlo)"),
        (spec_diagrams, theme.sans(16), "diagrams (Helvetica)"),
    ):
        src = pathlib.Path(module.__file__).read_text(encoding="utf-8")
        chars = {c for c in src if ord(c) > 127}
        missing = _tofu_chars(font, chars)
        if missing:
            bad = True
            print("  tofu in %s: %s" % (label, " ".join(repr(c) for c in missing)))
    return not bad


def build(names):
    ASSETS.mkdir(parents=True, exist_ok=True)
    for name in names:
        png = spec_diagrams.BUILDERS[name]().save(str(ASSETS / ("%s-how-it-works.png" % name)))
        term = spec_demos.BUILDERS[name]()
        gif = term.save(str(ASSETS / ("%s-demo.gif" % name)))
        print("  %-20s %4d KB png   %4d KB gif (%d frames)" % (
            name, os.path.getsize(png) // 1024, os.path.getsize(gif) // 1024,
            len(term.frames)))


if __name__ == "__main__":
    wanted = sys.argv[1:] or list(spec_diagrams.BUILDERS)
    unknown = [n for n in wanted if n not in spec_diagrams.BUILDERS]
    if unknown:
        sys.exit("unknown plugin(s): %s" % ", ".join(unknown))
    print("checking glyph coverage...")
    if not check_glyphs():
        sys.exit("fix the characters above before building")
    print("  ok")
    build(wanted)
