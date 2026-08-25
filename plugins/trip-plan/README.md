# 🗺️ trip-plan

trip-plan turns a list of places and dates into a day-by-day itinerary, ordered around opening
hours, travel time, and fixed bookings. It can also audit a plan you already have, and it ships
the result two ways: a Markdown plan you can edit, and an installable app that lives on your home
screen and works with no signal.

## 🎬 Demo

A broken day caught by the checker, the reorder that fixes it, the privacy scan blocking a build,
and the same build succeeding once the codes are gone.

![trip-plan demo](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/trip-plan-demo.png)

## ⚙️ How it works

![How trip-plan works](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/trip-plan-how-it-works.png)

Three phases — create, review, deliver. On a new trip they run in order, but each stands on its
own, so the skill enters at whichever the request asks for.

- **Create** builds the itinerary in layers, because each layer constrains the next: fixed anchors
  first (timed tickets, trains, sunset, weekly closing days), then stops clustered by neighbourhood,
  ordered by walking distance, with an honest dwell time on each. Every day opens with a one-line
  *why this order*, so the reasoning is on the page rather than buried.
- **Review** audits a plan you already have against the same rules and says plainly what's broken —
  a stop on its closing day, a dinner you arrive at 27 minutes late — then ranks cuts by regret.
- **Deliver** locks the plan and hands you both artifacts. A feasibility check turns "this day looks
  tight" into an arithmetic answer, and a privacy scan runs *inside* the build and refuses a file
  that carries a booking reference or door code — masking the value even in its own report.

## 📱 What you get: Markdown, then an app

![The Markdown plan, and the app built from it](https://raw.githubusercontent.com/dmitry-do/ai-toolkit-public/main/docs/assets/trip-plan-itinerary.png)

One plan, two artifacts. **The Markdown** is the version you edit, a section per day. **The app** is
that same plan built into a [Progressive Web App](https://web.dev/articles/what-are-pwas) — one
self-contained file that installs to a home screen, opens full screen, works offline, opens on
today's card, and folds away the stops you've already passed.

## 📦 Install in Claude Code

```
/plugin marketplace add dmitry-do/ai-toolkit-public
/plugin install trip-plan@ai-toolkit-public
```

## 🌐 Claude Web

All three phases work on claude.ai, the build and the deploy included — package the skill folder
with `scripts/package-skill.sh trip-plan` and upload it in **Customize → Skills**. Wherever a shell
can run Wrangler, the skill deploys the built folder and reads the live URL back; otherwise it hands
you `dist.zip` to drop on [Cloudflare Drop](https://www.cloudflare.com/drop/) yourself.

Mine, MIT-licensed (see the root [LICENSE](../../LICENSE)).
