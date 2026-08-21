"""Shared palette and fonts for the generated README assets.

macOS system fonts only, Pillow only, Python 3.9 compatible.
"""
from __future__ import annotations

from PIL import ImageFont

# --- paper palette (diagrams) ---------------------------------------------
BG = "#F5F2EC"
SURFACE = "#FFFFFF"
INK = "#22262B"
MUTED = "#7A818C"
LINE = "#C9C3B8"
ACCENT = "#C2553D"   # terracotta: the plugin's own moving parts
ACCENT2 = "#2E7180"  # teal: things outside the plugin (models, servers, Claude)
GOLD = "#A8801F"
GREEN = "#4C7A4A"
GROUP_BG = "#EDE8DE"

# --- terminal palette (demos) ---------------------------------------------
T_BG = "#15181D"
T_CHROME = "#232830"
T_BORDER = "#2E343E"
T_FG = "#D6DBE3"
T_DIM = "#79828F"
T_GREEN = "#8CC08A"
T_RED = "#E0796F"
T_YELLOW = "#DCA95C"
T_CYAN = "#63B4C4"
T_MAGENTA = "#C08ACB"
T_BLUE = "#7FA6E0"

_SANS = "/System/Library/Fonts/Helvetica.ttc"
_MONO = "/System/Library/Fonts/Menlo.ttc"


def sans(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_SANS, size, index=1 if bold else 0)


def mono(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_MONO, size, index=1 if bold else 0)
