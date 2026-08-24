# docs-assets

Generates the two images every plugin README carries: the **How it works** diagram
(`docs/assets/<name>-how-it-works.png`) and the **Demo** animation
(`docs/assets/<name>-demo.gif`).

```bash
python3 scripts/docs-assets/build.py             # all plugins
python3 scripts/docs-assets/build.py trip-plan   # just one
```

Two plugins also carry a **screenshot** of what they produce —
`docs/assets/trip-plan-itinerary.png` and `docs/assets/meeting-notes-summary.png`. Those come from
`shots.py`, which needs Google Chrome:

```bash
python3 scripts/docs-assets/shots.py             # both
python3 scripts/docs-assets/shots.py trip-plan   # just one
```

Everything lands in `docs/assets/`, never inside a plugin: a plugin directory is downloaded on
install and uploaded as a skill, and an image nothing at runtime reads has no business in either.
The READMEs reference them by their public `raw.githubusercontent.com` URL, so the same file renders
from the private repo, the public mirror, and anywhere else a README is read.

The assets are committed, because GitHub renders them in the READMEs. This generator is here so
they stay editable — change a step in a workflow and you regenerate the picture instead of
redrawing it.

## Files

| File | What it is |
| --- | --- |
| `build.py` | CLI. Validates glyph coverage, then writes both assets per plugin. |
| `theme.py` | The shared palette and the two macOS system fonts (Helvetica, Menlo). |
| `diagram.py` | Block-and-arrow renderer: nodes at explicit coordinates, orthogonal edges, group frames. Draws at 2× and downsamples. |
| `terminal.py` | Terminal renderer: typing, in-place progress lines, soft wrap at the window width, and a single global palette so the GIF stays small. |
| `spec_diagrams.py` | One function per plugin — the diagram content. |
| `spec_demos.py` | One function per plugin — the demo script. |
| `shots.py` | Screenshots. Renders real files in headless Chrome and composes the captures with Pillow. Separate entry point because it needs Chrome. |
| `samples/` | The trip-plan week the screenshot is of. Gitignored — see below. |

## Conventions

- **Demo output is real.** Where a plugin ships a script, the lines in `spec_demos.py` are copied
  from an actual run of it. The Claude turns around that output are the ones the README's
  *How to use* section walks through. Don't invent output that the tool doesn't produce.
- **Glyph coverage is checked, not assumed.** Helvetica has no `→` and Menlo has no `⏺`; both render
  as an invisible-here, obvious-on-GitHub tofu box. `build.py` scans the spec files for non-ASCII
  characters and fails the build rather than shipping one.
- **Pillow only, Python 3.9.** Same constraint as the bundled plugin scripts — it has to run on the
  macOS system interpreter, with no third-party drawing tools installed. `shots.py` adds one
  dependency, Google Chrome, because a screenshot of a real page needs a real browser.
- **The screenshots are of real files.** `shots.py` photographs what's on disk, never a mockup.
  meeting-notes uses the plugin's own `examples/`, which is committed. trip-plan uses `samples/`,
  which is **not**: a week of itinerary is docs input, not a plugin fixture, so it's gitignored.
  The trade that buys is worth knowing — `docs/assets/trip-plan-itinerary.png` is a committed
  artifact rather than a reproducible one. Rebuilding it means restoring those three files first
  (`git log --diff-filter=D -- scripts/docs-assets/samples` finds the last version), and `shots.py`
  says so rather than failing obscurely. It stages two things
  in a throwaway copy — it pins the clock, so the itinerary shows a day mid-trip rather than a trip
  that hasn't started, and it re-applies the page's own light palette, because Chrome inherits
  macOS dark mode. Nothing else is changed, and the committed file is never touched.
- **Everything ships at retina resolution, by three different routes.** Diagrams are drawn at 4× and
  downsampled to 2×, because supersampling is what keeps line art's edges clean. Demo frames are
  rendered at 2× natively, since a GIF can't be supersampled without smearing the type. Screenshots
  are captured at 3× and never resized, because browser text is antialiased once already and
  resampling it a second time is exactly what made them look soft.
- Diagrams are ~230–410 KB, demos ~130–300 KB, the two screenshots ~580–690 KB. The full set is
  about 6 MB — all of it outside the plugins.
