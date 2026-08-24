# docs-assets

Generates the two images every plugin README carries: the **How it works** diagram
(`plugins/<name>/docs/how-it-works.png`) and the **Demo** animation
(`plugins/<name>/docs/demo.gif`).

```bash
python3 scripts/docs-assets/build.py             # all plugins
python3 scripts/docs-assets/build.py trip-plan   # just one
```

Two plugins also carry a **screenshot** of what they produce — `plugins/trip-plan/docs/output.png`
and `plugins/meeting-notes/docs/transcript-to-summary.png`. Those come from `shots.py`, which needs
Google Chrome:

```bash
python3 scripts/docs-assets/shots.py             # both
python3 scripts/docs-assets/shots.py trip-plan   # just one
```

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
| `samples/` | The trip-plan week the screenshot is of. Generator input, not part of any plugin. |

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
- **The screenshots are of the committed files.** `shots.py` photographs
  [`samples/`](./samples/) and `plugins/meeting-notes/skills/meeting-notes/examples/` as they are
  on disk. The trip-plan sample sits in `samples/` rather than in the plugin, because a file that
  only the docs read shouldn't install with the plugin or upload with the skill. It stages two things
  in a throwaway copy — it pins the clock, so the itinerary shows a day mid-trip rather than a trip
  that hasn't started, and it re-applies the page's own light palette, because Chrome inherits
  macOS dark mode. Nothing else is changed, and the committed file is never touched.
- **Screenshots ship at 2×, diagrams and demos at 1×.** The diagrams are supersampled line art, so
  downsampling them is what makes the edges clean. A screenshot is already-antialiased browser text,
  and downsampling that just blurs it, so `shots.py` keeps the full 2× canvas.
- Diagrams and demos are ~100–160 KB each; the two screenshots are ~400 KB each at 2×.
