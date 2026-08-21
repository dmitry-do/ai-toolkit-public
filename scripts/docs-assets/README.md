# docs-assets

Generates the two images every plugin README carries: the **How it works** diagram
(`plugins/<name>/docs/how-it-works.png`) and the **Demo** animation
(`plugins/<name>/docs/demo.gif`).

```bash
python3 scripts/docs-assets/build.py             # all plugins
python3 scripts/docs-assets/build.py trip-plan   # just one
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

## Conventions

- **Demo output is real.** Where a plugin ships a script, the lines in `spec_demos.py` are copied
  from an actual run of it. The Claude turns around that output are the ones the README's
  *How to use* section walks through. Don't invent output that the tool doesn't produce.
- **Glyph coverage is checked, not assumed.** Helvetica has no `→` and Menlo has no `⏺`; both render
  as an invisible-here, obvious-on-GitHub tofu box. `build.py` scans the spec files for non-ASCII
  characters and fails the build rather than shipping one.
- **Pillow only, Python 3.9.** Same constraint as the bundled plugin scripts — it has to run on the
  macOS system interpreter, with no third-party drawing tools installed.
- Assets are ~100–160 KB each; the full set is about 2 MB.
