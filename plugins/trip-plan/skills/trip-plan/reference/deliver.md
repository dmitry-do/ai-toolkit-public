# Delivering a trip plan

Read this when the user wants the locked plan as a file, an offline app, or a URL.
Sequencing and the privacy rule live in `SKILL.md`; visual direction lives in
`style.md` next to this file.

One HTML file, shipped two ways:

1. **The file itself.** Self-contained, saved to Files or Downloads, opens offline with no server. This is the fallback that always works.
2. **The installable PWA.** The same file plus a manifest, service worker, and an emoji icon, zipped and published, so it sits on the home screen and survives a dead signal in a valley.

Build the HTML first, then run the packaging script. Don't hand-write manifests or service workers.

### Step 1: the HTML file

- One HTML file, everything inlined (CSS in `<style>`, JS in `<script>`, no external links to fonts, scripts, or images). Keep it that way: the script adds the PWA layer around it without breaking the local copy
- Single `<title>` and a brief `<meta name="description">` so the saved file is recognisable in Files
- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`
- Mobile-first layout with safe-area insets via `env(safe-area-inset-*)` for notched phones
- Nothing that assumes `https://` at runtime, so the file still works from `file://`

#### Day-collapse logic (JS at end of `<body>`)

1. Each day is a `<details class="day-card" data-date="YYYY-MM-DD">`. Find the card whose `data-date` matches today's local date, open it, close every other. Set `data-is-today="true"` on that card so the summary can show a "TODAY · " tag.
2. If today falls outside the trip window: open the next upcoming card; if the trip is over, open the last card.
3. On first paint, scroll the open card into view (`scrollIntoView({block: 'start'})`).

#### Past-stop folding (today's table only)

1. Parse the first `<td>` of each row with `/^\s*~?\s*(\d{1,2}):(\d{2})\s*([ap])?\.?m?\.?/i`. Group 3 present means 12-hour, absent means 24-hour, and a plan drafted in Europe will be 24-hour. Both have to work: an earlier version only accepted AM/PM, and a 24-hour table matched nothing, so no row was ever marked past and the feature quietly did nothing for a whole trip. Skip rows that still don't match.
2. Rows in the past: add class `row-past` (hidden via `display: none`).
3. The first row in the future: add class `row-next` and render a wedge marker before the time.
4. If any rows are hidden, inject a "Show N earlier stops" button above the table. Toggle a `show-past` class on the day card to reveal them.

#### Page structure

```html
<details class="day-card" data-date="2026-05-26">
  <summary>
    <span class="day-title">Day 1, Tue May 26: [title]</span>
    <span class="day-chevron" aria-hidden="true"></span>
  </summary>
  <div class="day-body">
    <p class="suntime">🌅 Sunrise HH:MM &nbsp;·&nbsp; 🌇 Sunset HH:MM</p>
    <table>
      <thead><tr><th>Time</th><th>Stop</th><th>Details</th></tr></thead>
      <tbody>
        <tr><td>HH:MM AM</td><td>emoji + name</td><td>notes, price band, anything time-sensitive</td></tr>
      </tbody>
    </table>
  </div>
</details>
```

Add a totals table (distance, driving time, wake-to-sleep) and a "Before You Go" checklist at the bottom when the trip involves driving, park passes, or pre-booked anything.

#### Style direction

In `style.md` next to this file.

### Step 2: build the PWA and the zip

```bash
# The scripts live in the plugin, not the project, so call them by full path.
# --out must be a new or previously-built directory: the build clears it, and it
# refuses anything it didn't create, including the folder holding the itinerary.
python3 <this skill's folder>/scripts/build_pwa.py --html itinerary.html --out dist \
  --name "California Coast, May 2026" --short-name "CA Coast" \
  --theme "#b5533c" --bg "#faf6ef" --icon "🌊"
```

The build refuses to run when the HTML still holds booking codes, access codes or personal data, so the rule above is enforced rather than remembered. To scan without building, run `python3 <this skill's folder>/scripts/scrub_check.py itinerary.html`. It's a pattern matcher, so it catches shapes and not meaning: it won't recognise a traveller's name or a home address. Read the file as well. When a finding is genuinely a venue's public detail, narrow it: `--allow "phone number"` keeps every other category blocking. `--allow-pii` disables the scan entirely and should be close to never.

Only `--html` is required; name and theme fall back to the `<title>` and sane defaults. Pick `--theme` to match the itinerary's accent colour and `--icon` from the trip: one emoji (🚗 for a road trip, 🏯 for Japan) or 1-3 letters, so the home screen icon is recognisable next to other apps. Use the same emoji as the plan's title when it has one. The script needs Python 3.8 and nothing else. `python3 <this skill's folder>/tests/run_tests.py` covers all the scripts if you have changed any of them.

It writes `dist/` with `index.html`, `manifest.webmanifest`, `sw.js`, and two SVG icons (`icon.svg` and `icon-maskable.svg`), then zips the whole thing with the files at the zip root, which is the layout Cloudflare Drop expects. The connector path uses the folder, not the zip.

The icons are SVG text, not PNG. A PNG set travels to the connector as base64, which made the payload about 50 KB, most of it base64 that has to be copied into the tool call without one changed character. With SVG icons there is nothing binary in `dist/` and the payload is plain text. Android and desktop Chrome use the SVG icons when they install the app. iOS does not read SVG for the home screen, so it uses a screenshot of the page as the icon. The emoji is drawn with the phone's own emoji font, so it looks a little different on each platform. Do not add PNG files to `dist/` to fix this.

Into `index.html` it injects a manifest link, light and dark `theme-color`, the iOS meta tags, an SVG favicon, an "Add to Home Screen" button that only appears when the browser fires `beforeinstallprompt`, and a service worker registration guarded so the local `file://` copy keeps working untouched.

The service worker serves pages network-first with a cache fallback, so a redeployed itinerary shows up immediately when there's signal and still opens on airplane mode. Icons and the manifest are cache-first. The cache name is keyed to a hash of the HTML, so each rebuild retires the old cache instead of stranding people on a stale plan. Re-running the script on an already-built `index.html` replaces the injected blocks rather than duplicating them, so edit and rebuild freely.

### Step 3: publish on Cloudflare

A service worker only runs in a secure context, so `https://` or localhost, never `file://`. Use the first path below that is available. Do not ask the user which one to use.

Always try path 1 first when its `execute` tool is there. Do not skip it because the payload looks large, because a copy might go wrong, or because Wrangler is quicker. The payload checks itself, so a bad copy deploys nothing and comes back as `PAYLOAD_CHANGED`. Go to path 2 only when no qualifying tool is available, or when path 1 returns an error that the list below says to fall back on.

**1. With the Cloudflare connector (preferred):** this deploys to the user's own Cloudflare account. The URL does not expire, and a redeploy with the same name updates the app that is already on the phone.

The connector qualifies when one of its tools is named `execute` and its description says that it runs JavaScript with `cloudflare.request()` against the Cloudflare API. This is the server at `https://mcp.cloudflare.com/mcp`. The tool name has the connector's prefix, which changes. If the tool is deferred, load it with a tool search for "cloudflare execute". The plugin bundles this server as `cloudflare-api`, so it is usually there once the user has signed in to Cloudflare through it. The older Workers Bindings connector, named "Cloudflare Developer Platform" on claude.ai (tools such as `workers_list` and `kv_namespace_create`, but no `execute`), is deprecated and cannot upload a Worker.

If no qualifying `execute` tool is available, tell the user once, then go on to path 2 without waiting:

> Your current Cloudflare connector can't deploy this app. [If the old one is connected: "Cloudflare Developer Platform" is the deprecated Workers Bindings server, and it has no tool that uploads a Worker.] The deploy needs the Cloudflare API connector at `https://mcp.cloudflare.com/mcp`. To add it:
> - **claude.ai:** Customize → Connectors → Add custom connector. Name it "Cloudflare API", paste `https://mcp.cloudflare.com/mcp` as the URL, then select Connect and sign in to Cloudflare. Allow it to edit Workers scripts.
> - **Claude Code:** run `/mcp`, choose `plugin:trip-plan:cloudflare-api` and sign in. If the plugin's server is missing, run `claude mcp add --transport http cloudflare-api https://mcp.cloudflare.com/mcp`.
>
> Until then I'll publish with Wrangler or Cloudflare Drop instead.

Say it only once per session, and skip the bracketed sentence when the old connector isn't connected.

```bash
python3 <this skill's folder>/scripts/cf_deploy.py --dist dist --name trip-ca-coast-may-2026
```

- `--name` is the Worker name and the first label of the URL. Use `trip-` plus a slug of the trip. Keep the same name for every redeploy of the same trip
- The script writes `cf_deploy.js` next to `dist/` and prints its size. It refuses a folder that `build_pwa.py` did not build, because the build runs the privacy scan
- Read `cf_deploy.js` and pass its whole content, unchanged, as `code` to the `execute` tool. Do not edit, shorten or retype parts of it. Long strings are cut into `"..." +` pieces of 1,500 characters, so every line fits in one file read. Copy the pieces in order
- If the script prints a note about binary files, something other than `build_pwa.py` put them in `dist/`. Rebuild instead of deploying them
- If the session can reach more than one Cloudflare account, `execute` says that no account is resolved. Then list the accounts with `async () => cloudflare.request({ method: "GET", path: "/accounts" })`, ask the user which one to use, and pass its id as `account_id`

The payload stops before it uploads anything when a guard fails. Each error starts with a code:

- `PAYLOAD_CHANGED`: the content changed on its way into the tool call. Read the file again and retry once. If it fails again, use path 2
- `NO_SUBDOMAIN`: the account has no `workers.dev` subdomain. That name is shared by every Worker on the account, so ask the user to choose one in the Cloudflare dashboard. Then retry
- `NAME_TAKEN`: a Worker with that name exists and trip-plan did not make it. Pick a different `--name`, rebuild the payload and retry
- An HTTP 401 or 403: the error names the missing permission. Tell the user to reconnect the connector with permission to edit Workers scripts

The result gives the live URL. The payload marks the Worker with the tag `trip-plan` and asks search engines not to index it. If the user asks to take a trip offline, send this through the same tool, with the real name:

```js
async () => cloudflare.request({ method: "DELETE", path: `/accounts/${accountId}/workers/scripts/trip-ca-coast-may-2026` })
```

**2. With a terminal:** use Wrangler, which is the CLI path Cloudflare recommends for local project folders.

```bash
npm exec --yes wrangler@latest -- deploy ./dist \
  --name ca-coast-may-2026 --temporary --compatibility-date <today YYYY-MM-DD>
```

- Use today's real date for `--compatibility-date`
- `--name` is required; use a slug of the trip
- Drop `--temporary` if Wrangler is already authenticated via OAuth, `CLOUDFLARE_API_TOKEN`, or a global API key. In that case plain `wrangler deploy` is correct
- If a deploy fails asking for a name or a compatibility date, rerun with the flag it asked for
- Wrangler 4.102.0 or later is needed for the unauthenticated path

**3. With browser automation only:** upload `dist.zip` at https://www.cloudflare.com/drop/ and read the URLs off the result page.

**4. With none of these:** hand the user `dist.zip` and the Drop URL and let them drop it in themselves. It takes them about ten seconds. Some sandboxes block outbound traffic to Cloudflare, so check rather than assume the deploy failed for a code reason.

Then verify and hand over:

- Open the live `workers.dev` URL. A 404 right after deploy is normal, wait a few seconds and retry before changing anything
- Connector path: return the live URL. There is no claim URL, because the Worker is already on the user's account
- Wrangler `--temporary` or Drop path: return both the live URL and the claim URL. Say plainly that the claim URL expires in 60 minutes and grants ownership of the deployment, so it shouldn't be shared
- The live URL is public and unlisted, which is why the file has to be clean before it gets here. Anyone with the link can read it, and links leak

### What to confirm before shipping

- Trip dates are filled in on every `data-date` attribute and match the day titles
- Times in each table parse: `9:30 AM` and `09:30` both work, mixing the two in one table doesn't. Open the file and confirm at least one row folds as past
- All CSS and JS is inlined, no external links to fonts, scripts, or images
- `scrub_check.py` comes back clean, and a read-through confirms no traveller names or home address slipped past the patterns
- The plain HTML file opens cleanly from Files with no network (no `https://` assumptions in the code)
- Today's card scrolls into view on first paint
- On the published URL: the manifest loads, the service worker registers, and the install prompt appears on Android or "Add to Home Screen" works on iOS
- Offline check on the published version: load it once, switch to airplane mode, reload, and confirm the itinerary still renders

