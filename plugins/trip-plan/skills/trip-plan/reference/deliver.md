# Delivering a trip plan

Read this when the user wants the locked plan as a file, an offline app, or a URL.
Sequencing and the privacy rule live in `SKILL.md`; visual direction lives in
`style.md` next to this file.

One HTML file, shipped two ways:

1. **The file itself.** Self-contained, saved to Files or Downloads, opens offline with no server. This is the fallback that always works.
2. **The installable PWA.** The same file plus a manifest, service worker, and icons, zipped and published, so it sits on the home screen and survives a dead signal in a valley.

Build the HTML first, then run the packaging script. Don't hand-write manifests or service workers.

### Step 1: the HTML file

A built example of everything below is in `../examples/tokyo-2026-12.html`, next to the Markdown it
came from. Copying its structure is faster than assembling one from this list.

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
python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-plan/scripts/build_pwa.py --html itinerary.html --out dist \
  --name "California Coast, May 2026" --short-name "CA Coast" \
  --theme "#b5533c" --bg "#faf6ef" --initials CA
```

The build refuses to run when the HTML still holds booking codes, access codes or personal data, so the rule above is enforced rather than remembered. To scan without building, run `python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-plan/scripts/scrub_check.py itinerary.html`. It's a pattern matcher, so it catches shapes and not meaning: it won't recognise a traveller's name or a home address. Read the file as well. When a finding is genuinely a venue's public detail, narrow it: `--allow "phone number"` keeps every other category blocking. `--allow-pii` disables the scan entirely and should be close to never.

Only `--html` is required; name and theme fall back to the `<title>` and sane defaults. Pick `--theme` to match the itinerary's accent colour and `--initials` from the destination, so the home screen icon is recognisable next to other apps. The script needs Python 3.8 and nothing else. `python3 ${CLAUDE_PLUGIN_ROOT}/skills/trip-plan/tests/run_tests.py` covers both scripts if you've changed either.

It writes `dist/` with `index.html`, `manifest.webmanifest`, `sw.js`, and four icons (192, 512, maskable 512, apple-touch 180), then zips the whole thing with the files at the zip root, which is the layout Cloudflare Drop expects.

Into `index.html` it injects a manifest link, light and dark `theme-color`, the iOS meta tags and touch icon, an "Add to Home Screen" button that only appears when the browser fires `beforeinstallprompt`, and a service worker registration guarded so the local `file://` copy keeps working untouched.

The service worker serves pages network-first with a cache fallback, so a redeployed itinerary shows up immediately when there's signal and still opens on airplane mode. Icons and the manifest are cache-first. The cache name is keyed to a hash of the HTML, so each rebuild retires the old cache instead of stranding people on a stale plan. Re-running the script on an already-built `index.html` replaces the injected blocks rather than duplicating them, so edit and rebuild freely.

### Step 3: publish on Cloudflare Drop

Cloudflare Drop puts a static folder on Cloudflare's network with no account needed, which is what this needs: a service worker only runs in a secure context, so `https://` or localhost, never `file://`.

**With a terminal (preferred):** use Wrangler, which is the CLI path Cloudflare recommends for local project folders.

```bash
npm exec --yes wrangler@latest -- deploy ./dist \
  --name ca-coast-may-2026 --temporary --compatibility-date <today YYYY-MM-DD>
```

- Use today's real date for `--compatibility-date`
- `--name` is required; use a slug of the trip
- Drop `--temporary` if Wrangler is already authenticated via OAuth, `CLOUDFLARE_API_TOKEN`, or a global API key. In that case plain `wrangler deploy` is correct
- If a deploy fails asking for a name or a compatibility date, rerun with the flag it asked for
- Wrangler 4.102.0 or later is needed for the unauthenticated path

**With browser automation only:** upload `dist.zip` at https://www.cloudflare.com/drop/ and read the URLs off the result page.

**With neither:** hand the user `dist.zip` and the Drop URL and let them drop it in themselves. It takes them about ten seconds. Some sandboxes block outbound traffic to Cloudflare, so check rather than assume the deploy failed for a code reason.

Then verify and hand over:

- Open the live `workers.dev` URL. A 404 right after deploy is normal, wait a few seconds and retry before changing anything
- Return both the live URL and the claim URL
- Say plainly that the claim URL expires in 60 minutes and grants ownership of the deployment, so it shouldn't be shared
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

