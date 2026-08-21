#!/usr/bin/env python3
"""
build_pwa.py - turn a single-file itinerary HTML into an installable PWA folder + .zip.

Takes the self-contained itinerary HTML and produces a static site directory that
Cloudflare Drop or `wrangler deploy` can publish as-is:

    dist/
      index.html                 (source HTML + injected PWA head tags and SW registration)
      manifest.webmanifest
      sw.js
      icons/icon-192.png, icon-512.png, icon-maskable-512.png, apple-touch-icon.png
    dist.zip                     (same files, zipped at root level)

Usage:
    python3 scripts/build_pwa.py --html itinerary.html --out dist \
        --name "California Coast, May 2026" --short-name "CA Coast" \
        --theme "#b5533c" --bg "#faf6ef" --initials CA

Only --html is required. Everything else is derived from the HTML or defaulted.

Re-running is safe: injected blocks are marked and replaced, so you can edit the
itinerary and rebuild without accumulating duplicate tags.

No third-party dependencies. Icons are drawn with a small pure-Python PNG writer,
so this works on any machine with Python 3.8+.
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import signal
import struct
import sys
import zipfile
import zlib
from pathlib import Path

MARK_HEAD = "trip-plan:pwa-head"
MARK_BODY = "trip-plan:pwa-body"
STAMP = ".trip-plan-build"


def prepare_out(out, src):
    """Clear and recreate the output directory, but only if we put it there.

    This used to be a bare shutil.rmtree(out). `--out .` is a reasonable thing to
    type when you want dist/ next to the itinerary, and it deleted the itinerary,
    then raised on rmdir('.') so the traceback read like a harmless crash. The
    build now refuses anything it can't prove it built: a directory qualifies only
    if it's empty or carries the stamp file this script writes.
    """
    out, src = Path(out).resolve(), Path(src).resolve()
    cwd = Path.cwd().resolve()
    if out == Path(out.anchor) or out == Path.home().resolve():
        sys.exit("Refusing to build into %s. Pass --out with a new subdirectory." % out)
    if out == src.parent or out in src.parents:
        sys.exit("--out %s holds the itinerary and would be deleted. Use a subdirectory,"
                 "\nfor example --out %s." % (out, out / "dist"))
    if out == cwd or out in cwd.parents:
        sys.exit("--out %s is the working directory or above it. Use a subdirectory." % out)
    if out.exists():
        if not out.is_dir():
            sys.exit("--out %s exists and is not a directory." % out)
        if any(out.iterdir()) and not (out / STAMP).exists():
            sys.exit("--out %s already has files in it and wasn't built by this script."
                     "\nEmpty it yourself or pick another path." % out)
        shutil.rmtree(out)
    (out / "icons").mkdir(parents=True)
    (out / STAMP).write_text("trip-plan build output, safe to delete\n", encoding="utf-8")
    return out

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from scrub_check import report, scan_text
except ImportError:  # scanner missing, build still works but says so
    report = scan_text = None

# ---------------------------------------------------------------------------
# Tiny PNG writer (no Pillow required)
# ---------------------------------------------------------------------------


def write_png(path, pixels, width, height):
    """pixels: flat bytearray of RGBA, length width*height*4."""
    raw = bytearray()
    stride = width * 4
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        raw += pixels[y * stride:(y + 1) * stride]

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")
    Path(path).write_bytes(png)


def hex_to_rgb(value):
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError("colour must be #rgb or #rrggbb, got %r" % value)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


# ---------------------------------------------------------------------------
# Signed distance helpers, used for anti-aliased shapes
# ---------------------------------------------------------------------------


def sd_rounded_rect(px, py, cx, cy, half_w, half_h, radius):
    qx = abs(px - cx) - (half_w - radius)
    qy = abs(py - cy) - (half_h - radius)
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    inside = min(max(qx, qy), 0.0)
    return outside + inside - radius


def sd_circle(px, py, cx, cy, r):
    return math.hypot(px - cx, py - cy) - r


def sd_triangle(px, py, a, b, c):
    def sub(u, v):
        return (u[0] - v[0], u[1] - v[1])

    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1]

    def clamp01(t):
        return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)

    p = (px, py)
    e0, e1, e2 = sub(b, a), sub(c, b), sub(a, c)
    v0, v1, v2 = sub(p, a), sub(p, b), sub(p, c)

    def leg(v, e):
        t = clamp01(dot(v, e) / max(dot(e, e), 1e-9))
        return (v[0] - e[0] * t, v[1] - e[1] * t)

    p0, p1, p2 = leg(v0, e0), leg(v1, e1), leg(v2, e2)
    s = 1.0 if (e0[0] * e2[1] - e0[1] * e2[0]) > 0 else -1.0
    dx = min(dot(p0, p0), dot(p1, p1), dot(p2, p2))
    dy = min(
        s * (v0[0] * e0[1] - v0[1] * e0[0]),
        s * (v1[0] * e1[1] - v1[1] * e1[0]),
        s * (v2[0] * e2[1] - v2[1] * e2[0]),
    )
    return -math.sqrt(dx) * (1.0 if dy > 0 else -1.0)


# 5x7 bitmap font, enough for initials (A-Z, 0-9). Each row is 5 bits, MSB left.
FONT = {
    "A": [0x0E, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "B": [0x1E, 0x11, 0x11, 0x1E, 0x11, 0x11, 0x1E],
    "C": [0x0E, 0x11, 0x10, 0x10, 0x10, 0x11, 0x0E],
    "D": [0x1E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x1E],
    "E": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x1F],
    "F": [0x1F, 0x10, 0x10, 0x1E, 0x10, 0x10, 0x10],
    "G": [0x0E, 0x11, 0x10, 0x17, 0x11, 0x11, 0x0F],
    "H": [0x11, 0x11, 0x11, 0x1F, 0x11, 0x11, 0x11],
    "I": [0x0E, 0x04, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "J": [0x07, 0x02, 0x02, 0x02, 0x02, 0x12, 0x0C],
    "K": [0x11, 0x12, 0x14, 0x18, 0x14, 0x12, 0x11],
    "L": [0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F],
    "M": [0x11, 0x1B, 0x15, 0x15, 0x11, 0x11, 0x11],
    "N": [0x11, 0x19, 0x15, 0x13, 0x11, 0x11, 0x11],
    "O": [0x0E, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "P": [0x1E, 0x11, 0x11, 0x1E, 0x10, 0x10, 0x10],
    "Q": [0x0E, 0x11, 0x11, 0x11, 0x15, 0x12, 0x0D],
    "R": [0x1E, 0x11, 0x11, 0x1E, 0x14, 0x12, 0x11],
    "S": [0x0F, 0x10, 0x10, 0x0E, 0x01, 0x01, 0x1E],
    "T": [0x1F, 0x04, 0x04, 0x04, 0x04, 0x04, 0x04],
    "U": [0x11, 0x11, 0x11, 0x11, 0x11, 0x11, 0x0E],
    "V": [0x11, 0x11, 0x11, 0x11, 0x11, 0x0A, 0x04],
    "W": [0x11, 0x11, 0x11, 0x15, 0x15, 0x1B, 0x11],
    "X": [0x11, 0x11, 0x0A, 0x04, 0x0A, 0x11, 0x11],
    "Y": [0x11, 0x11, 0x0A, 0x04, 0x04, 0x04, 0x04],
    "Z": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x10, 0x1F],
    "0": [0x0E, 0x11, 0x13, 0x15, 0x19, 0x11, 0x0E],
    "1": [0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E],
    "2": [0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F],
    "3": [0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E],
    "4": [0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02],
    "5": [0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E],
    "6": [0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E],
    "7": [0x1F, 0x01, 0x02, 0x04, 0x08, 0x08, 0x08],
    "8": [0x0E, 0x11, 0x11, 0x0E, 0x11, 0x11, 0x0E],
    "9": [0x0E, 0x11, 0x11, 0x0F, 0x01, 0x02, 0x0C],
}


def render_icon(size, bg_rgb, fg_rgb, initials=None, maskable=False):
    """Draw a rounded-square icon with either initials or a map-pin glyph."""
    px = bytearray(size * size * 4)
    s = float(size)
    # Maskable icons must survive an aggressive circular crop, so the plate goes
    # full-bleed and the glyph stays inside the middle ~60%.
    if maskable:
        plate_half, plate_r, glyph_scale = s / 2, 0.0, 0.46
    else:
        plate_half, plate_r, glyph_scale = s * 0.46, s * 0.22, 0.62

    cx = cy = s / 2
    glyph = [c for c in (initials or "").upper() if c in FONT][:3]

    if glyph:
        cols = len(glyph) * 5 + (len(glyph) - 1)  # 1 blank column between chars
        cell = (s * glyph_scale) / max(cols, 7)
        gw, gh = cols * cell, 7 * cell
        gx0, gy0 = cx - gw / 2, cy - gh / 2
    else:
        head_r = s * glyph_scale * 0.30
        head_cy = cy - s * glyph_scale * 0.14
        tip = (cx, cy + s * glyph_scale * 0.52)
        left = (cx - head_r * 0.86, head_cy + head_r * 0.52)
        right = (cx + head_r * 0.86, head_cy + head_r * 0.52)
        hole_r = head_r * 0.40

    for y in range(size):
        fy = y + 0.5
        row = y * size * 4
        for x in range(size):
            fx = x + 0.5
            d_plate = sd_rounded_rect(fx, fy, cx, cy, plate_half, plate_half, plate_r)
            a_plate = min(max(0.5 - d_plate, 0.0), 1.0)
            if a_plate <= 0.0:
                continue

            if glyph:
                a_glyph = 0.0
                col = int((fx - gx0) // cell)
                rowi = int((fy - gy0) // cell)
                if 0 <= rowi < 7 and 0 <= col < len(glyph) * 6:
                    ci, sub = divmod(col, 6)
                    if sub < 5 and ci < len(glyph):
                        if FONT[glyph[ci]][rowi] & (1 << (4 - sub)):
                            a_glyph = 1.0
            else:
                d_head = sd_circle(fx, fy, cx, head_cy, head_r)
                d_tail = sd_triangle(fx, fy, left, right, tip)
                d_pin = min(d_head, d_tail)
                d_hole = sd_circle(fx, fy, cx, head_cy, hole_r)
                a_pin = min(max(0.5 - d_pin, 0.0), 1.0)
                a_hole = min(max(0.5 - d_hole, 0.0), 1.0)
                a_glyph = max(a_pin - a_hole, 0.0)

            r = bg_rgb[0] + (fg_rgb[0] - bg_rgb[0]) * a_glyph
            g = bg_rgb[1] + (fg_rgb[1] - bg_rgb[1]) * a_glyph
            b = bg_rgb[2] + (fg_rgb[2] - bg_rgb[2]) * a_glyph
            i = row + x * 4
            px[i] = int(r)
            px[i + 1] = int(g)
            px[i + 2] = int(b)
            px[i + 3] = int(a_plate * 255)
    return px


def downsample(px, size, target):
    """Box-filter an RGBA raster down to target x target."""
    out = bytearray(target * target * 4)
    step = size / target
    for y in range(target):
        y0, y1 = int(y * step), max(int((y + 1) * step), int(y * step) + 1)
        for x in range(target):
            x0, x1 = int(x * step), max(int((x + 1) * step), int(x * step) + 1)
            acc = [0, 0, 0, 0]
            n = 0
            for sy in range(y0, y1):
                base = sy * size * 4
                for sx in range(x0, x1):
                    i = base + sx * 4
                    acc[0] += px[i]
                    acc[1] += px[i + 1]
                    acc[2] += px[i + 2]
                    acc[3] += px[i + 3]
                    n += 1
            o = (y * target + x) * 4
            for k in range(4):
                out[o + k] = acc[k] // max(n, 1)
    return out


# ---------------------------------------------------------------------------
# HTML injection
# ---------------------------------------------------------------------------


def strip_marked(html, mark):
    pattern = re.compile(
        r"[ \t]*<!-- %s:start -->.*?<!-- %s:end -->\n?" % (re.escape(mark), re.escape(mark)),
        re.DOTALL,
    )
    return pattern.sub("", html)


def head_block(name, short_name, theme, bg):
    return f"""<!-- {MARK_HEAD}:start -->
<link rel="manifest" href="./manifest.webmanifest">
<meta name="theme-color" content="{bg}" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="{theme}" media="(prefers-color-scheme: dark)">
<meta name="color-scheme" content="light dark">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<meta name="apple-mobile-web-app-title" content="{short_name}">
<meta name="application-name" content="{short_name}">
<link rel="apple-touch-icon" href="./icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="./icons/icon-192.png">
<link rel="icon" type="image/png" sizes="512x512" href="./icons/icon-512.png">
<style>
.tp-install{{position:fixed;right:max(12px,env(safe-area-inset-right));
bottom:calc(12px + env(safe-area-inset-bottom));z-index:9999;display:none;
padding:10px 16px;border:0;border-radius:999px;font:600 15px/1 system-ui,sans-serif;
color:{bg};background:{theme};box-shadow:0 4px 14px rgba(0,0,0,.22);cursor:pointer}}
.tp-install[data-show="1"]{{display:block}}
@media print{{.tp-install{{display:none!important}}}}
</style>
<!-- {MARK_HEAD}:end -->"""


def body_block(build_id):
    return f"""<!-- {MARK_BODY}:start -->
<button class="tp-install" type="button" hidden>Add to Home Screen</button>
<script>
(function () {{
  var local = location.protocol === 'file:';
  if ('serviceWorker' in navigator && !local) {{
    addEventListener('load', function () {{
      navigator.serviceWorker.register('./sw.js', {{ scope: './' }}).catch(function () {{}});
    }});
  }}
  var btn = document.querySelector('.tp-install');
  var deferred = null;
  addEventListener('beforeinstallprompt', function (e) {{
    e.preventDefault();
    deferred = e;
    if (btn) {{ btn.hidden = false; btn.dataset.show = '1'; }}
  }});
  if (btn) {{
    btn.addEventListener('click', function () {{
      if (!deferred) return;
      deferred.prompt();
      deferred.userChoice.finally(function () {{
        deferred = null;
        btn.dataset.show = '0';
        btn.hidden = true;
      }});
    }});
  }}
  addEventListener('appinstalled', function () {{
    if (btn) {{ btn.dataset.show = '0'; btn.hidden = true; }}
  }});
  document.documentElement.dataset.tpBuild = '{build_id}';
}})();
</script>
<!-- {MARK_BODY}:end -->"""


def inject(html, name, short_name, theme, bg, build_id):
    html = strip_marked(strip_marked(html, MARK_HEAD), MARK_BODY)
    head = head_block(name, short_name, theme, bg)
    body = body_block(build_id)

    if re.search(r"</head\s*>", html, re.I):
        html = re.sub(r"</head\s*>", head + "\n</head>", html, count=1, flags=re.I)
    elif re.search(r"<body[^>]*>", html, re.I):
        html = re.sub(r"(<body[^>]*>)", r"\1\n" + head, html, count=1, flags=re.I)
    else:
        html = head + "\n" + html

    if re.search(r"</body\s*>", html, re.I):
        html = re.sub(r"</body\s*>", body + "\n</body>", html, count=1, flags=re.I)
    else:
        html = html + "\n" + body
    return html


SW_TEMPLATE = """/* trip-plan service worker, build {build_id} */
const CACHE = 'trip-{build_id}';
const ASSETS = {assets};

self.addEventListener('install', (e) => {{
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
}});

self.addEventListener('activate', (e) => {{
  e.waitUntil((async () => {{
    const keys = await caches.keys();
    await Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)));
    if (self.registration.navigationPreload) await self.registration.navigationPreload.enable();
    await self.clients.claim();
  }})());
}});

self.addEventListener('fetch', (e) => {{
  const req = e.request;
  if (req.method !== 'GET' || new URL(req.url).origin !== location.origin) return;

  // Itineraries get edited, so a live network wins for page loads and the cache
  // is the fallback when the phone is offline or on hotel wifi that lies.
  if (req.mode === 'navigate') {{
    e.respondWith((async () => {{
      try {{
        const preload = await e.preloadResponse;
        const res = preload || await fetch(req);
        // A 404 after the deploy lapses, a 502, or a hotel captive portal
        // answering 200 with a login page would otherwise overwrite the last
        // good itinerary, which is the one thing the cache exists to hold.
        if (res.ok && !res.redirected && res.type === 'basic') {{
          const cache = await caches.open(CACHE);
          cache.put('./index.html', res.clone());
        }}
        return res;
      }} catch (err) {{
        const cache = await caches.open(CACHE);
        return (await cache.match('./index.html')) || Response.error();
      }}
    }})());
    return;
  }}

  // Icons and the manifest never change within a build, so serve them instantly.
  e.respondWith((async () => {{
    const cached = await caches.match(req);
    if (cached) return cached;
    try {{
      const res = await fetch(req);
      if (res.ok && res.type === 'basic') (await caches.open(CACHE)).put(req, res.clone());
      return res;
    }} catch (err) {{
      return cached || Response.error();
    }}
  }})());
}});
"""


def main():
    # Piping into head/less shouldn't produce a traceback.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    ap = argparse.ArgumentParser(description="Build an installable PWA from an itinerary HTML file.")
    ap.add_argument("--html", required=True, help="Path to the single-file itinerary HTML")
    ap.add_argument("--out", default="dist", help="Output directory (default: dist)")
    ap.add_argument("--name", help="Full app name (default: the HTML <title>)")
    ap.add_argument("--short-name", help="Home screen label, keep under ~12 characters")
    ap.add_argument("--theme", default="#8a4b3a", help="Accent colour, e.g. #b5533c")
    ap.add_argument("--bg", default="#faf6ef", help="Background/splash colour")
    ap.add_argument("--initials", help="1-3 letters for the icon, e.g. CA. Omit for a map pin")
    ap.add_argument("--lang", default="en", help="Manifest lang (default: en)")
    ap.add_argument("--zip", dest="zip_path", help="Zip path (default: <out>.zip)")
    ap.add_argument("--no-zip", action="store_true", help="Skip the zip step")
    ap.add_argument("--allow", action="append", default=[], metavar="CATEGORY",
                    help="Stop one scan category blocking, e.g. --allow 'phone number'. "
                         "Repeatable, and narrower than --allow-pii")
    ap.add_argument("--allow-pii", action="store_true",
                    help="Build despite every privacy scan finding. Prefer --allow")
    args = ap.parse_args()

    src = Path(args.html)
    if not src.is_file():
        sys.exit("No such file: %s" % src)
    html = src.read_text(encoding="utf-8", errors="replace")

    # Publishing is the point of no return: the zip gets uploaded to a public URL,
    # so the scan runs before anything is written rather than as a later reminder.
    if scan_text is None:
        print("Warning: scrub_check.py not found, skipping the privacy scan.")
    elif not args.allow_pii:
        findings = scan_text(html)
        if report(findings, allow=args.allow) != 0:
            sys.exit("\nNothing was built. Fix the file above, or rerun with --allow-pii "
                     "if you've checked each finding is public venue information.")

    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    name = args.name or (title.group(1).strip() if title else "Trip itinerary")
    short_name = args.short_name or (name.split(",")[0].split("(")[0].strip()[:12] or "Trip")
    theme, bg = args.theme, args.bg
    hex_to_rgb(theme), hex_to_rgb(bg)  # fail early on bad colours

    out = prepare_out(args.out, src)

    build_id = hashlib.sha256(html.encode("utf-8")).hexdigest()[:10]
    (out / "index.html").write_text(
        inject(html, name, short_name, theme, bg, build_id), encoding="utf-8"
    )

    manifest = {
        "id": "./",
        "name": name,
        "short_name": short_name,
        "description": "Offline travel itinerary",
        "lang": args.lang,
        "dir": "ltr",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "display_override": ["standalone", "minimal-ui", "browser"],
        "orientation": "portrait",
        "background_color": bg,
        "theme_color": theme,
        "categories": ["travel", "navigation"],
        "icons": [
            {"src": "./icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "./icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "./icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    (out / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    assets = [
        "./index.html",
        "./manifest.webmanifest",
        "./icons/icon-192.png",
        "./icons/icon-512.png",
        "./icons/icon-maskable-512.png",
        "./icons/apple-touch-icon.png",
    ]
    (out / "sw.js").write_text(
        SW_TEMPLATE.format(build_id=build_id, assets=json.dumps(assets)), encoding="utf-8"
    )

    theme_rgb, bg_rgb = hex_to_rgb(theme), hex_to_rgb(bg)
    base = render_icon(512, theme_rgb, bg_rgb, args.initials, maskable=False)
    write_png(out / "icons" / "icon-512.png", base, 512, 512)
    write_png(out / "icons" / "icon-192.png", downsample(base, 512, 192), 192, 192)
    write_png(out / "icons" / "apple-touch-icon.png", downsample(base, 512, 180), 180, 180)
    mask = render_icon(512, theme_rgb, bg_rgb, args.initials, maskable=True)
    write_png(out / "icons" / "icon-maskable-512.png", mask, 512, 512)

    zip_path = None
    if not args.no_zip:
        zip_path = Path(args.zip_path) if args.zip_path else out.with_suffix(".zip")
        if zip_path.exists():
            zip_path.unlink()
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(out.rglob("*")):
                if f.is_file() and f.name != STAMP:
                    z.write(f, f.relative_to(out).as_posix())

    print("Built %s (build %s)" % (out, build_id))
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.name != STAMP:
            print("  %-34s %7d bytes" % (f.relative_to(out).as_posix(), f.stat().st_size))
    if zip_path:
        print("Zipped: %s (%d bytes, files at zip root)" % (zip_path, zip_path.stat().st_size))
    print("Deploy this directory or the zip. index.html sits at the root, as Drop expects.")


if __name__ == "__main__":
    main()
