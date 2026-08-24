"""Animated terminal renderer: a demo script in, an optimised GIF out.

Frames are rendered at SCALE device pixels per CSS pixel, so the type stays
sharp on a retina screen. Every layout constant below derives from it.

A demo is a list of actions. Text carries a tiny colour markup — {g}green{/},
plus {r} {y} {c} {d} {m} {b} {w} — so the specs stay readable. Lines soft-wrap
at the window width exactly as a real terminal does.
"""
from __future__ import annotations

import re

from PIL import Image, ImageDraw

import theme as T

SCALE = 2          # device pixel ratio the frames are rendered at
COLS = 112
FONT_SIZE = 14 * SCALE
LINE_H = 20 * SCALE
PAD_X = 16 * SCALE
PAD_Y = 12 * SCALE
CHROME_H = 32 * SCALE
ROWS = 21

_COLOURS = {
    "g": T.T_GREEN, "r": T.T_RED, "y": T.T_YELLOW, "c": T.T_CYAN,
    "d": T.T_DIM, "m": T.T_MAGENTA, "b": T.T_BLUE, "w": "#FFFFFF",
}
_TAG = re.compile(r"\{(/|[grycdmbw])\}")


def spans(text):
    """'a {g}b{/} c' -> [('a ', fg), ('b', green), (' c', fg)]"""
    out, colour, pos = [], T.T_FG, 0
    for m in _TAG.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], colour))
        colour = T.T_FG if m.group(1) == "/" else _COLOURS[m.group(1)]
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], colour))
    return out


def _wrap(sp, cols=COLS):
    """Soft-wrap coloured spans into display rows, like a real terminal."""
    rows, row, used = [], [], 0
    for text, colour in sp:
        while text:
            room = cols - used
            if room <= 0:
                rows.append(row)
                row, used, room = [], 0, cols
            chunk, text = text[:room], text[room:]
            row.append((chunk, colour))
            used += len(chunk)
    rows.append(row)
    return rows


class Terminal:
    def __init__(self, title="claude code", prompt="$ "):
        self.font = T.mono(FONT_SIZE)
        self.bold = T.mono(FONT_SIZE, bold=True)
        self.adv = self.font.getlength("M")
        self.w = int(PAD_X * 2 + self.adv * COLS)
        self.h = CHROME_H + PAD_Y * 2 + LINE_H * ROWS
        self.title = title
        self.prompt = prompt
        self.rows = []            # committed display rows
        self.frames = []          # (Image, duration_ms)

    # -- frame plumbing -----------------------------------------------------
    def _render(self, pending=None, cursor=False):
        img = Image.new("RGB", (self.w, self.h), T.T_BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.w, CHROME_H], fill=T.T_CHROME)
        d.line([0, CHROME_H, self.w, CHROME_H], fill=T.T_BORDER)
        for i, c in enumerate(("#E0796F", "#DCA95C", "#8CC08A")):
            cx, r = (16 + i * 18) * SCALE, 5 * SCALE
            d.ellipse([cx, CHROME_H // 2 - r, cx + 2 * r, CHROME_H // 2 + r], fill=c)
        d.text((self.w // 2, CHROME_H // 2), self.title, font=T.mono(12 * SCALE),
               fill=T.T_DIM, anchor="mm")

        body = list(self.rows)
        if pending is not None:
            body += pending
        body = body[-ROWS:]
        y = CHROME_H + PAD_Y
        for row in body:
            x = PAD_X
            for text, colour in row:
                d.text((x, y), text, font=self.font, fill=colour)
                x += self.adv * len(text)
            if cursor and row is body[-1]:
                d.rectangle([x + SCALE, y + 2 * SCALE, x + self.adv,
                             y + FONT_SIZE + 4 * SCALE], fill=T.T_FG)
            y += LINE_H
        return img

    def _emit(self, ms, pending=None, cursor=False):
        self.frames.append((self._render(pending, cursor), ms))

    # -- actions ------------------------------------------------------------
    def hold(self, ms):
        self._emit(ms)

    def clear(self):
        self.rows = []
        self._emit(220)

    def write(self, text, pause=90):
        for row in _wrap(spans(text)):
            self.rows.append(row)
        self._emit(pause)

    def blank(self, pause=70):
        self.rows.append([])
        self._emit(pause)

    def rewrite(self, text, ms=90):
        """Redraw the last row in place (progress bars, spinners)."""
        if self.rows:
            self.rows.pop()
        self.rows.append(_wrap(spans(text))[0])
        self._emit(ms)

    def progress(self, make, steps, ms=95):
        """Animate an in-place progress line: make(i, n) -> markup string."""
        self.write(make(0, steps), ms)
        for i in range(1, steps + 1):
            self.rewrite(make(i, steps), ms)

    def out(self, lines, pause=110):
        for ln in lines:
            self.write(ln, pause)

    def outfast(self, lines, pause=460):
        for ln in lines:
            for row in _wrap(spans(ln)):
                self.rows.append(row)
        self._emit(pause)

    def type(self, text, prompt=None, per_frame=3, ms=55, settle=520):
        """Type a command out character by character after the prompt."""
        pr = self.prompt if prompt is None else prompt
        head = spans(pr)
        plain = _TAG.sub("", text)
        for i in range(0, len(plain) + 1, per_frame):
            shown = plain[:i]
            self._emit(ms, pending=_wrap(head + [(shown, T.T_FG)]), cursor=True)
        self._emit(settle, pending=_wrap(head + spans(text)), cursor=True)
        for row in _wrap(head + spans(text)):
            self.rows.append(row)
        self._emit(240)

    def ask(self, text):
        """A chat-style user turn."""
        self.type(text, prompt="{m}> {/}", per_frame=2, ms=48)

    def say(self, lines, pause=520):
        """A Claude turn: the bullet marker plus indented body."""
        first = True
        for ln in lines:
            prefix = "{c}●{/}  " if first else "   "
            self.write(prefix + ln, pause if first else 200)
            first = False

    # -- output -------------------------------------------------------------
    def save(self, path, tail_ms=2600):
        if not self.frames:
            raise ValueError("nothing recorded")
        self.frames[-1] = (self.frames[-1][0], self.frames[-1][1] + tail_ms)

        sample = self.frames[:: max(1, len(self.frames) // 8)][:9]
        cols = 3
        rowsn = (len(sample) + cols - 1) // cols
        montage = Image.new("RGB", (self.w * cols, self.h * rowsn), T.T_BG)
        for i, (fr, _) in enumerate(sample):
            montage.paste(fr, ((i % cols) * self.w, (i // cols) * self.h))
        ref = montage.convert("P", palette=Image.ADAPTIVE, colors=128)

        quant = [f.quantize(palette=ref, dither=Image.Dither.NONE) for f, _ in self.frames]
        quant[0].save(
            path, save_all=True, append_images=quant[1:],
            duration=[max(40, ms) for _, ms in self.frames],
            loop=0, optimize=True, disposal=1,
        )
        return path
