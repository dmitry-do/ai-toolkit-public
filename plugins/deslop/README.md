# 🧹 deslop

deslop reworks a document in two passes: it checks every claim against the source that document
describes, then rewrites the prose to be direct. Accuracy comes first, because there's no point
polishing a sentence that says the wrong thing. The rework runs on a bundled `claude-opus-4-8`
subagent, one document at a time.

## 🎬 Demo

A README checked against its skill: a wrong default caught and corrected to what the code actually
says, a made-up figure flagged and cut, and the teaser opening rewritten to lead with the subject.
Walked through step by step in [How to use](#how-to-use).

![deslop demo](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/deslop-demo.gif)

## ⚙️ How it works

![How deslop works](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/deslop-how-it-works.png)

- **Pass 1 — accuracy, first.** The subagent reads the source of truth (for a plugin README, that's
  the `SKILL.md`, scripts, hooks, and `plugin.json`), then goes through the document claim by claim:
  names, flags, filenames, numbers, defaults, ordering, what-runs-where. It fixes what the source
  contradicts, corrects framings that are backwards, and cuts claims the source doesn't support.
- **Pass 2 — style, second.** Once the content is true, it's made direct: lead with the subject,
  drop the teaser and round-the-subject openings, land each point once. Structure, code blocks, and
  real command output are left exactly as they are.
- **It flags what it can't verify, and never invents.** A claim with no support in the source is
  reported, not kept and not backfilled with a plausible-sounding number.
- **The rework runs on `claude-opus-4-8`.** The plugin bundles an agent (`agents/deslop.md`) pinned
  to that model, and the skill dispatches one subagent per document to it, in isolation, so one
  document's facts can't bleed into another's.
- **`humanizer` is an optional last step.** deslop fixes truth and directness; if `humanizer` is
  installed, deslop can hand off to it for a final AI-tell cleanup. It isn't required.

## 📦 Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install deslop@ai-toolkit-public
```

## 🌐 Install in Claude Web

The skill is plain editing and runs on claude.ai. The one Claude Code-only piece is the model pin:
`agents/deslop.md` pins the rework to `claude-opus-4-8`, and bundled agents are a Claude Code
feature — on claude.ai the two passes run on whatever model you're using. Package the skill folder:

```bash
scripts/package-skill.sh deslop        # writes dist/deslop-skill.zip
```

Then in claude.ai: **Customize → Skills → Add → Create skill → Upload a skill**, and select the zip.

> Packaging the skill zips `skills/deslop/` only; the `agents/` folder (the model pin) stays behind,
> which is expected since claude.ai has no subagents to pin.

## 🧩 What it does

- Reworks a README, `SKILL.md`, release notes, changelog, or API doc so its claims match the
  implementation and its prose is direct.
- **Verifies before it rewrites.** Every checkable statement is read against the source; the
  accuracy pass runs before the style pass, never after.
- **Reports, doesn't paper over.** Each run returns the corrections (claim → what the source says),
  the claims it couldn't verify, and the directness changes made.
- **Runs on a pinned `claude-opus-4-8` subagent**, one document at a time in isolation.
- **Composes with `humanizer`** as an optional final tell-cleanup, and works fine without it.

## 📖 How to use

### 1. Point it at a document and its source

> "deslop plugins/widgetcache/README.md against its skill" · "fact-check this doc against the code"

deslop identifies the source of truth (for a plugin README, the plugin's own `SKILL.md`, scripts,
hooks, and `plugin.json`) and dispatches a `claude-opus-4-8` subagent to rework the document. If the
source isn't obvious, it asks rather than guessing.

### 2. Pass 1 finds what the doc gets wrong

The subagent reads the source, then checks the document against it. Here the source is
`DEFAULT_TTL = 300`:

```
CORRECTIONS
  "cached for ten minutes by default"  ->  the source default is 300 s, i.e. five minutes (cache.py:3)
  "turn caching off per call"          ->  the source names it: no_cache=True (cache.py:7)

FLAGGED
  "a hundred times a minute"  ->  no such figure in the source; cut, since it was scene-setting
```

### 3. Pass 2 makes the true content direct

Only after the facts are settled does the prose get reworked:

```diff
-Ever notice how the same request hammers your API a hundred times a minute? widgetcache is here to
-change all that. It wraps your calls in a blazing-fast, rock-solid, drop-in cache — so your app
-stays fast, your costs stay low, and your users stay happy.
-
-Responses are cached for ten minutes by default, and you can turn caching off per call.
+widgetcache memoises a function call in memory, keyed by a `key` you supply: within the TTL a
+repeated call returns the stored value instead of running the function again.
+
+Values are cached for five minutes by default (`DEFAULT_TTL = 300`); pass `ttl=` to change it for
+one call, `--ttl` to change the default, or `no_cache=True` to skip the cache for a single call.
```

The full input, source, and output are in [`examples/`](./skills/deslop/examples/).

### 4. Read the report, then optionally humanize

Each run ends with CORRECTIONS, FLAGGED, STYLE, and the file written. If `humanizer` is installed,
deslop offers to run it over the reworked file as a final pass on AI tells (em-dashes, rule of
three, stock vocabulary) — a different job from deslop's, and optional.

## 🗂️ Structure

```
plugins/deslop/
├── .claude-plugin/plugin.json   # marketplace manifest
├── README.md                    # this file
├── agents/deslop.md             # the worker, pinned to model: claude-opus-4-8
└── skills/deslop/               # this folder is what uploads to Claude Web
    ├── SKILL.md                 # when to use, source identification, dispatch, the two passes
    └── examples/                # a real source + before → after + report
```

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
