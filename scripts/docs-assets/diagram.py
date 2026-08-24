"""Block-and-arrow diagram renderer for the plugin READMEs.

A diagram is plain data: nodes at explicit 1x coordinates, orthogonal edges
between named node sides, and optional group frames. Everything is drawn at
4x and downsampled to 2x: the supersampling is what keeps the edges clean, and
the 2x output is what stays sharp on a retina screen.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

import theme as T

OUT = 2            # output device pixel ratio
SS = 2             # supersampling on top of it, which is what keeps edges clean
SCALE = OUT * SS


def _s(v):
    if isinstance(v, (tuple, list)):
        return tuple(int(round(x * SCALE)) for x in v)
    return int(round(v * SCALE))


KINDS = {
    # fill, border, dashed, bar (left accent stripe), title colour
    "step":  (T.SURFACE, T.LINE, False, T.ACCENT, T.INK),
    "guard": (T.SURFACE, T.ACCENT, False, T.ACCENT, T.ACCENT),
    "ext":   (T.SURFACE, T.ACCENT2, True, None, T.ACCENT2),
    "io":    (None, T.LINE, True, None, T.INK),
    "store": ("#FBF8F2", T.LINE, False, T.MUTED, T.INK),
}


class Canvas:
    def __init__(self, width, height, title=None, subtitle=None):
        self.w, self.h = width, height
        self.img = Image.new("RGB", (_s(width), _s(height)), T.BG)
        self.d = ImageDraw.Draw(self.img)
        self.nodes = {}
        if title:
            self.d.text(_s((40, 30)), title, font=T.mono(_s(19), bold=True), fill=T.INK)
        if subtitle:
            self.d.text(_s((40, 57)), subtitle, font=T.sans(_s(15)), fill=T.MUTED)

    # -- primitives ---------------------------------------------------------
    def _dashed_round_rect(self, box, radius, colour, width, dash=9, gap=6):
        x0, y0, x1, y1 = box
        r = radius
        segs = []
        segs += [((x, y0), (min(x + dash, x1 - r), y0)) for x in range(x0 + r, x1 - r, dash + gap)]
        segs += [((x, y1), (min(x + dash, x1 - r), y1)) for x in range(x0 + r, x1 - r, dash + gap)]
        segs += [((x0, y), (x0, min(y + dash, y1 - r))) for y in range(y0 + r, y1 - r, dash + gap)]
        segs += [((x1, y), (x1, min(y + dash, y1 - r))) for y in range(y0 + r, y1 - r, dash + gap)]
        for a, b in segs:
            self.d.line([a, b], fill=colour, width=width)
        for cx, cy, s, e in (
            (x0 + r, y0 + r, 180, 270), (x1 - r, y0 + r, 270, 360),
            (x1 - r, y1 - r, 0, 90), (x0 + r, y1 - r, 90, 180),
        ):
            self.d.arc([cx - r, cy - r, cx + r, cy + r], s, e, fill=colour, width=width)

    def group(self, x, y, w, h, label=None):
        box = _s((x, y, x + w, y + h))
        self.d.rounded_rectangle(box, radius=_s(14), fill=T.GROUP_BG)
        if label:
            self.d.text(_s((x + 16, y + 11)), label,
                        font=T.sans(_s(11), bold=True), fill=T.MUTED)

    def node(self, nid, x, y, w, h, title, lines=(), kind="step", mono_title=False,
             title_size=16, badge=None):
        fill, border, dashed, bar, tcol = KINDS[kind]
        box = _s((x, y, x + w, y + h))
        r = _s(10)
        if fill:
            self.d.rounded_rectangle(box, radius=r, fill=fill)
        if dashed:
            self._dashed_round_rect(box, r, border, _s(1.5))
        else:
            self.d.rounded_rectangle(box, radius=r, outline=border, width=_s(1.5))
        if bar:
            self.d.rounded_rectangle(_s((x, y + 9, x + 4, y + h - 9)), radius=_s(2), fill=bar)

        tx = x + (16 if bar else 14)
        tf = T.mono(_s(title_size - 1), bold=True) if mono_title else T.sans(_s(title_size), bold=True)
        ty = y + 13
        self.d.text(_s((tx, ty)), title, font=tf, fill=tcol)
        ly = ty + (title_size + 9)
        lf = T.sans(_s(12))
        for ln in lines:
            col = T.MUTED
            if ln.startswith("!"):
                ln, col = ln[1:], T.ACCENT
            elif ln.startswith("+"):
                ln, col = ln[1:], T.GREEN
            self.d.text(_s((tx, ly)), ln, font=lf, fill=col)
            ly += 16
        if badge:
            bf = T.mono(_s(10), bold=True)
            bw = self.d.textlength(badge, font=bf) / SCALE + 12
            self.d.rounded_rectangle(_s((x + w - bw - 10, y + 11, x + w - 10, y + 28)),
                                     radius=_s(5), fill=T.GROUP_BG)
            self.d.text(_s((x + w - bw - 4, y + 15)), badge, font=bf, fill=T.MUTED)
        self.nodes[nid] = (x, y, w, h)
        return nid

    def label(self, x, y, text, size=12, colour=None, bold=False, mono=False, anchor="la"):
        f = T.mono(_s(size), bold=bold) if mono else T.sans(_s(size), bold=bold)
        self.d.text(_s((x, y)), text, font=f, fill=colour or T.MUTED, anchor=anchor)

    # -- edges --------------------------------------------------------------
    def _anchor(self, nid, side, off=0.5):
        x, y, w, h = self.nodes[nid]
        return {
            "l": (x, y + h * off), "r": (x + w, y + h * off),
            "t": (x + w * off, y), "b": (x + w * off, y + h),
        }[side]

    def edge(self, a, b, label=None, style="solid", colour=None, off_a=0.5, off_b=0.5,
             bend=None, label_dx=0, label_dy=-16, arrow=True, back=False):
        """a/b are "node:side" strings. Routes orthogonally with one elbow."""
        an, asd = a.split(":")
        bn, bsd = b.split(":")
        p0 = self._anchor(an, asd, off_a)
        p1 = self._anchor(bn, bsd, off_b)
        col = colour or (T.ACCENT if style == "accent" else T.MUTED)
        pts = [p0]
        if asd in "lr" and bsd in "lr":
            mid = bend if bend is not None else (p0[0] + p1[0]) / 2
            if abs(p0[1] - p1[1]) > 1:
                pts += [(mid, p0[1]), (mid, p1[1])]
        elif asd in "tb" and bsd in "tb":
            mid = bend if bend is not None else (p0[1] + p1[1]) / 2
            if abs(p0[0] - p1[0]) > 1:
                pts += [(p0[0], mid), (p1[0], mid)]
        elif asd in "lr":
            pts += [(p1[0], p0[1])]
        else:
            pts += [(p0[0], p1[1])]
        pts.append(p1)

        w = _s(2)
        for i in range(len(pts) - 1):
            seg = [_s(pts[i]), _s(pts[i + 1])]
            if style == "dashed":
                self._dashed_line(pts[i], pts[i + 1], col, w)
            else:
                self.d.line(seg, fill=col, width=w)
        if arrow:
            self._arrow_head(pts[-2], pts[-1], col)
        if back:
            self._arrow_head(pts[1], pts[0], col)
        if label:
            mx = (pts[len(pts) // 2 - 1][0] + pts[len(pts) // 2][0]) / 2 + label_dx
            my = (pts[len(pts) // 2 - 1][1] + pts[len(pts) // 2][1]) / 2 + label_dy
            f = T.sans(_s(11.5))
            tw = self.d.textlength(label, font=f) / SCALE
            self.d.rectangle(_s((mx - tw / 2 - 5, my - 2, mx + tw / 2 + 5, my + 15)), fill=T.BG)
            self.d.text(_s((mx, my)), label, font=f, fill=col, anchor="ma")

    def _dashed_line(self, p0, p1, colour, width, dash=8, gap=5):
        import math
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        dist = math.hypot(dx, dy)
        if dist == 0:
            return
        ux, uy = dx / dist, dy / dist
        t = 0.0
        while t < dist:
            e = min(t + dash, dist)
            self.d.line([_s((p0[0] + ux * t, p0[1] + uy * t)),
                         _s((p0[0] + ux * e, p0[1] + uy * e))], fill=colour, width=width)
            t = e + gap

    def _arrow_head(self, frm, to, colour, size=9):
        import math
        ang = math.atan2(to[1] - frm[1], to[0] - frm[0])
        tip = to
        a = (to[0] - size * math.cos(ang - 0.42), to[1] - size * math.sin(ang - 0.42))
        b = (to[0] - size * math.cos(ang + 0.42), to[1] - size * math.sin(ang + 0.42))
        self.d.polygon([_s(tip), _s(a), _s(b)], fill=colour)

    def save(self, path):
        out = self.img.resize((self.w * OUT, self.h * OUT), Image.LANCZOS)
        out.save(path, "PNG", optimize=True)
        return path
