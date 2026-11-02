#!/usr/bin/env python3
"""
build_pwa.py - turn a single-file itinerary HTML into an installable PWA folder + .zip.

Takes the self-contained itinerary HTML and produces a static site directory that
Cloudflare Drop or `wrangler deploy` can publish as-is:

    dist/
      index.html                 (source HTML + injected PWA head tags and SW registration)
      manifest.webmanifest
      sw.js
      icons/icon.svg, icons/icon-maskable.svg   (emoji or initials, plain text)
    dist.zip                     (same files, zipped at root level)

Usage:
    python3 scripts/build_pwa.py --html itinerary.html --out dist \
        --name "California Coast, May 2026" --short-name "CA Coast" \
        --theme "#b5533c" --bg "#faf6ef" --icon "🌊"

Only --html is required. Everything else is derived from the HTML or defaulted.

Re-running is safe: injected blocks are marked and replaced, so you can edit the
itinerary and rebuild without accumulating duplicate tags.

No third-party dependencies. Icons are SVG text, with no PNG and no base64, so
the Cloudflare connector payload stays small. Python 3.8+.
"""

import argparse
import hashlib
import json
import re
import shutil
import signal
import sys
import zipfile
from html import escape as html_escape
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
# Icons: plain SVG text, no PNG and no base64
# ---------------------------------------------------------------------------
# A PNG icon set added ~12 KB of binary, which the connector payload carries as
# ~16 KB of base64 that the model has to copy into the tool call by hand. An SVG
# is a few hundred bytes of text, so the payload stays small and copyable.

EMOJI_FONTS = "'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif"
LETTER_FONTS = "'Helvetica Neue',Arial,sans-serif"
DEFAULT_ICON = "\U0001F5FA\ufe0f"  # world map emoji


def hex_to_rgb(value):
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    if len(v) != 6:
        raise ValueError("colour must be #rgb or #rrggbb, got %r" % value)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


def is_letters(text):
    return bool(re.fullmatch(r"[A-Za-z0-9]{1,3}", text))


def svg_icon(text, theme, bg, maskable=False):
    """One emoji (or 1-3 letters) on a coloured plate.

    Maskable icons must survive an aggressive circular crop, so the plate goes
    full-bleed and the glyph stays inside the middle ~60%.
    """
    text = (text or DEFAULT_ICON).strip() or DEFAULT_ICON
    letters = is_letters(text)
    if letters:
        text = text.upper()
        size = {1: 300, 2: 230, 3: 170}[len(text)] * (0.78 if maskable else 1)
        font, weight, fill = LETTER_FONTS, ' font-weight="700"', bg
    else:
        size = 220 if maskable else 300
        font, weight, fill = EMOJI_FONTS, "", bg
    plate = ('<rect width="512" height="512" fill="%s"/>' % theme if maskable else
             '<rect x="20" y="20" width="472" height="472" rx="104" fill="%s"/>' % theme)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        + plate
        + '<text x="256" y="270" text-anchor="middle" dominant-baseline="middle" '
        + 'font-family="%s" font-size="%d"%s fill="%s">%s</text>'
        % (html_escape(font), size, weight, fill, html_escape(text))
        + "</svg>\n"
    )


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
<link rel="icon" type="image/svg+xml" href="./icons/icon.svg">
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
    ap.add_argument("--icon", help="One emoji or 1-3 letters for the home screen icon, e.g. 🚗 or CA "
                         "(default: a map emoji)")
    ap.add_argument("--initials", help=argparse.SUPPRESS)  # old name for --icon
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
            {"src": "./icons/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
            {"src": "./icons/icon-maskable.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "maskable"},
        ],
    }
    (out / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    assets = [
        "./index.html",
        "./manifest.webmanifest",
        "./icons/icon.svg",
        "./icons/icon-maskable.svg",
    ]
    (out / "sw.js").write_text(
        SW_TEMPLATE.format(build_id=build_id, assets=json.dumps(assets)), encoding="utf-8"
    )

    icon = args.icon or args.initials
    (out / "icons" / "icon.svg").write_text(svg_icon(icon, theme, bg), encoding="utf-8")
    (out / "icons" / "icon-maskable.svg").write_text(svg_icon(icon, theme, bg, maskable=True), encoding="utf-8")

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
