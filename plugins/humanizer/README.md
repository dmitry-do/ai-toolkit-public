# ✍️ humanizer

Strip the tells of AI-generated writing and put a human back behind the text. Based on Wikipedia's
[Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing) guide, maintained
by WikiProject AI Cleanup.

## Install

```
/plugin install humanizer@ai-toolkit-public
```

## What it does

Detects and rewrites the patterns that mark text as machine-made:

- Inflated significance ("a testament to", "pivotal moment", "evolving landscape")
- Promotional language, vague attributions, and superficial `-ing` analyses
- Em-dash pileups, rule-of-three, negative parallelisms, false ranges
- Stock AI vocabulary, copula avoidance, synonym cycling, hedging and filler
- Chatbot artifacts ("Great question!", "I hope this helps!"), emojis, curly quotes

It doesn't just delete bad patterns — it adds voice: varied rhythm, real opinions, first person
where it fits. Give it a sample of your own writing and it matches your style instead of a generic
default.

## Usage

> "humanize this text" · "make this sound less AI-generated"
>
> "humanize this. Here's a sample of my writing for voice matching: [sample]"

The skill returns a draft, an honest "what still reads as AI" pass, and a final rewrite.

## Learn more

The full pattern catalog (29 categories with before/after examples):
[`skills/humanizer/SKILL.md`](./skills/humanizer/SKILL.md).

## Attribution

Mirrored from [blader/humanizer](https://github.com/blader/humanizer) by Siqi Chen, MIT-licensed.
The upstream author and version are preserved in `.claude-plugin/plugin.json`; see
[`NOTICE.md`](./NOTICE.md) and [`LICENSE.upstream`](./LICENSE.upstream).
