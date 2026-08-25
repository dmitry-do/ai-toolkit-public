# 🧾 session-cost-stamp

When a session ends, the record of what it cost usually ends with it. session-cost-stamp writes
the worked time, context % and dollar cost into the session's own title, so it shows in the
sessions list, shows on `--resume`, and stays in the transcript file for good.

## 🎬 Demo

The statusLine rendering and stashing, the stash contents, the hook consuming it at session end,
and the title that comes out.

![session-cost-stamp demo](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/session-cost-stamp-demo.png)

## ⚙️ How it works

![How session-cost-stamp works](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/session-cost-stamp-how-it-works.png)

- The **statusLine** is the only surface Claude Code hands the cost and context figures, so on
  every render it parks them in a small stash file.
- On session end, the **`SessionEnd` hook** has no cost data of its own. It reads the stash and
  appends a native `ai-title` entry — the same kind Claude Code writes itself, so it can't corrupt
  the transcript — and that becomes the session's title.
- The stash is deleted after stamping, and a re-stamp replaces the bracket rather than compounding
  it, so a session that ends twice doesn't end up with two.

The `$` and context % match the Claude Code UI exactly, because they *are* the UI's values.

## 📦 Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install session-cost-stamp@ai-toolkit-public
```

Then **`/reload-plugins`** (or restart) — hooks only take effect after a reload. The plugin also
needs a **statusLine that stashes the live stats** for the hook to read (Claude Code won't let a
plugin provide one); copy the bundled `statusline.sh`, or paste the stash block from the skill into
the statusLine you already have. Without the stash, the hook exits quietly and nothing is stamped.

## 🌐 Claude Web

Not applicable — there is no local statusLine or transcript file on claude.ai.

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
