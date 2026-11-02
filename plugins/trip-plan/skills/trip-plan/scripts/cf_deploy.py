#!/usr/bin/env python3
"""
cf_deploy.py - turn a built dist/ folder into one `execute` payload for the
Cloudflare API connector (the MCP server at https://mcp.cloudflare.com/mcp).

The connector runs JavaScript in a sandbox that can only call the Cloudflare
API, with the user's token added outside the sandbox. It cannot read local
files, and it cannot use the static-assets upload, because that endpoint wants
the upload JWT as the bearer token and the connector always sends the user's
token. So this script packs every file of dist/ into a small Worker module that
serves them itself, and wraps the upload in one async arrow function:

    python3 scripts/cf_deploy.py --dist dist --name trip-ca-coast-may-2026

writes cf_deploy.js next to dist/. Pass its full contents, unchanged, as the
`code` argument of the connector's `execute` tool. The function:

  1. Compares a SHA-256 of every file with the hash this script wrote, so a
     payload that changed on its way into the tool call deploys nothing.
  2. Reads the account's workers.dev subdomain, and stops if there is none.
  3. Refuses to overwrite a Worker with the same name that it did not create
     (it marks its own Workers with the tag "trip-plan").
  4. Uploads the Worker, turns on its workers.dev route, and returns the URL.

Re-running with the same --name replaces the Worker in place, so the URL and
any installed home-screen copy stay the same.

No third-party dependencies. Python 3.8+.
"""

import argparse
import base64
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

STAMP = ".trip-plan-build"
TAG = "trip-plan"
NAME_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}

# The Worker that serves the packed files. FILES is prepended at deploy time:
# { "/path": [contentType, "t" | "b", text-or-base64, etag] }.
HANDLER = r"""
const BIN = {};
const bytes = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

export default {
  async fetch(request) {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("Method not allowed", { status: 405, headers: { allow: "GET, HEAD" } });
    }
    let path;
    try {
      path = decodeURIComponent(new URL(request.url).pathname);
    } catch {
      return new Response("Bad request", { status: 400 });
    }
    if (path.endsWith("/")) path += "index.html";
    const f = FILES[path];
    if (!f) {
      return new Response("Not found", { status: 404, headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    const etag = '"' + f[3] + '"';
    const headers = {
      "content-type": f[0],
      etag,
      // Pages, the manifest and the service worker revalidate every time, so a
      // redeploy shows up at once. Icons rarely change.
      "cache-control": f[0].startsWith("image/") ? "public, max-age=86400" : "no-cache",
      "x-content-type-options": "nosniff",
      "referrer-policy": "no-referrer",
      // The URL is unlisted, not private. Ask search engines to stay out.
      "x-robots-tag": "noindex, nofollow",
    };
    if (request.headers.get("if-none-match") === etag) {
      return new Response(null, { status: 304, headers });
    }
    const body = f[1] === "b" ? (BIN[path] ??= bytes(f[2])) : f[2];
    return new Response(request.method === "HEAD" ? null : body, { headers });
  },
};
""".strip()

# The `execute` payload. __NAME__, __COMPAT__, __TAG__ and __FILES__ are filled
# in below; everything else is sent as written.
EXECUTE = r"""
async () => {
  const NAME = __NAME__;
  const COMPAT = __COMPAT__;
  const TAG = __TAG__;
  const HANDLER = __HANDLER__;
  // "/path": [contentType, "t" text | "b" base64, content, sha256 of the bytes]
  const FILES = __FILES__;

  // 1. Integrity. The model copies this payload into the tool call. If one
  //    character changed on the way, stop before anything reaches Cloudflare.
  const enc = new TextEncoder();
  const raw = (f) => (f[1] === "b" ? Uint8Array.from(atob(f[2]), (c) => c.charCodeAt(0)) : enc.encode(f[2]));
  const hex = async (b) =>
    [...new Uint8Array(await crypto.subtle.digest("SHA-256", b))].map((x) => x.toString(16).padStart(2, "0")).join("");
  const changed = [];
  for (const [p, f] of Object.entries(FILES)) {
    if ((await hex(raw(f))) !== f[3]) changed.push(p);
  }
  if (changed.length) {
    throw new Error("PAYLOAD_CHANGED: these files do not match their hashes, nothing was deployed: " + changed.join(", "));
  }

  // 2. The account needs a workers.dev subdomain. Choosing one names every
  //    Worker on the account, so that stays the user's decision.
  let sub;
  try {
    sub = (await cloudflare.request({ method: "GET", path: `/accounts/${accountId}/workers/subdomain` })).result?.subdomain;
  } catch (e) {
    sub = undefined;
  }
  if (!sub) {
    throw new Error("NO_SUBDOMAIN: this account has no workers.dev subdomain yet, nothing was deployed. Ask the user to choose one in the Cloudflare dashboard.");
  }

  // 3. Never replace a Worker that this skill did not create.
  const list = await cloudflare.request({ method: "GET", path: `/accounts/${accountId}/workers/scripts` });
  const existing = (list.result || []).find((s) => s.id === NAME);
  if (existing && !(existing.tags || []).includes(TAG)) {
    throw new Error(`NAME_TAKEN: a Worker named "${NAME}" exists and was not made by trip-plan, nothing was deployed. Choose another --name.`);
  }

  // 4. Upload, then open the workers.dev route.
  const served = Object.fromEntries(Object.entries(FILES).map(([p, f]) => [p, [f[0], f[1], f[2], f[3].slice(0, 16)]]));
  const module = "const FILES = " + JSON.stringify(served) + ";\n" + HANDLER;
  const metadata = { main_module: "worker.js", compatibility_date: COMPAT, tags: [TAG] };
  const form = new FormData();
  form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
  form.append("worker.js", new Blob([module], { type: "application/javascript+module" }), "worker.js");
  await cloudflare.request({ method: "PUT", path: `/accounts/${accountId}/workers/scripts/${NAME}`, body: form });
  await cloudflare.request({
    method: "POST",
    path: `/accounts/${accountId}/workers/scripts/${NAME}/subdomain`,
    body: { enabled: true, previews_enabled: false },
  });

  return {
    deployed: NAME,
    replaced: Boolean(existing),
    url: `https://${NAME}.${sub}.workers.dev/`,
    files: Object.keys(FILES).length,
  };
}
""".strip()


def pack(dist):
    files = {}
    for path in sorted(p for p in dist.rglob("*") if p.is_file()):
        rel = path.relative_to(dist).as_posix()
        if rel == STAMP or rel.startswith(".") or "/." in rel:
            continue
        data = path.read_bytes()
        ctype = TYPES.get(path.suffix.lower(), "application/octet-stream")
        text = None
        # SVG is text. Sending it as text keeps it out of base64, which is a third
        # larger and is the part of the payload most likely to be miscopied.
        if ctype == "image/svg+xml" or (not ctype.startswith("image/") and ctype != "application/octet-stream"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = None
        if text is not None:
            files["/" + rel] = [ctype, "t", text, hashlib.sha256(data).hexdigest()]
        else:
            files["/" + rel] = [ctype, "b", base64.b64encode(data).decode("ascii"), hashlib.sha256(data).hexdigest()]
    return files


def js(value):
    # ensure_ascii=False keeps emoji and non-Latin text as themselves, which is
    # about a third of the size of \u escapes. U+2028/2029 are legal in modern JS
    # strings but some tools still trip on them, so escape those two.
    return json.dumps(value, ensure_ascii=False).replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


CHUNK = 1500


def js_files(files):
    """FILES as one entry per line, with long strings cut into "..." + "..." pieces.

    The model reads this file and copies it into the tool call. One 47 KB line
    is past what a file read shows at once, so it had to be split by hand before
    it could be copied. Short lines read and copy in order. The SHA-256 check
    still catches any piece that changes on the way.
    """
    def lit(text):
        parts = [text[i:i + CHUNK] for i in range(0, len(text), CHUNK)] or [""]
        return " +\n      ".join(js(p) for p in parts)

    rows = []
    for path, (ctype, kind, body, digest) in files.items():
        rows.append("    %s: [%s, %s,\n      %s,\n      %s]" % (js(path), js(ctype), js(kind), lit(body), js(digest)))
    return "{\n" + ",\n".join(rows) + "\n  }"


def main():
    ap = argparse.ArgumentParser(description="Pack dist/ into an execute payload for the Cloudflare API connector.")
    ap.add_argument("--dist", required=True, help="the folder build_pwa.py wrote")
    ap.add_argument("--name", required=True, help="Worker name, also the first label of the URL, e.g. trip-ca-coast-may-2026")
    ap.add_argument("--compat-date", default=datetime.date.today().isoformat(), help="compatibility date, defaults to today")
    ap.add_argument("--out", help="where to write the payload, defaults to cf_deploy.js next to --dist")
    a = ap.parse_args()

    dist = Path(a.dist).resolve()
    if not dist.is_dir():
        sys.exit("No such folder: %s" % dist)
    # Only ship what build_pwa.py built, because the build is where the privacy scan runs.
    if not (dist / STAMP).is_file():
        sys.exit("%s was not built by build_pwa.py (no %s). Build it first, so the privacy scan runs." % (dist, STAMP))
    if not (dist / "index.html").is_file():
        sys.exit("%s has no index.html." % dist)
    if not NAME_RE.match(a.name):
        sys.exit("Bad --name %r: use 1-63 lowercase letters, digits and dashes, no dash at either end." % a.name)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", a.compat_date):
        sys.exit("Bad --compat-date %r: use YYYY-MM-DD." % a.compat_date)

    out = Path(a.out).resolve() if a.out else dist.parent / "cf_deploy.js"
    if out == dist or dist in out.parents:
        sys.exit("Write the payload outside %s, or it ships inside the next deploy." % dist)

    files = pack(dist)
    payload = (EXECUTE
               .replace("__NAME__", js(a.name))
               .replace("__COMPAT__", js(a.compat_date))
               .replace("__TAG__", js(TAG))
               .replace("__HANDLER__", js(HANDLER))
               .replace("__FILES__", js_files(files)))
    out.write_text(payload + "\n", encoding="utf-8")

    size = out.stat().st_size
    print("Packed %d files from %s" % (len(files), dist))
    print("Wrote %s (%d bytes)" % (out, size))
    binary = [p for p, f in files.items() if f[1] == "b"]
    if binary:
        print("Note: %d binary file(s) travel as base64 and make the payload harder to copy: %s"
              % (len(binary), ", ".join(binary)))
    print("Pass the whole file, unchanged, as `code` to the Cloudflare connector's execute tool.")
    print("Expected URL: https://%s.<account subdomain>.workers.dev/" % a.name)


if __name__ == "__main__":
    main()
