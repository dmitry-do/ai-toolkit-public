# deslop report — README.before.md → README.after.md

**CORRECTIONS**
- "cached for ten minutes by default" -> the source default is 300 seconds, i.e. five minutes
  (`cache.py:3`, `DEFAULT_TTL = 300`).
- "turn caching off per call" was vague -> the source names the mechanism: `no_cache=True`
  (`cache.py:7`).

**FLAGGED**
- "a hundred times a minute" — no such figure exists in the source; cut rather than kept, since it
  was scene-setting, not a claim about the tool.

**STYLE**
- Dropped the "Ever notice how…" teaser opener; the first line now states what widgetcache is and
  does.
- Cut the "blazing-fast, rock-solid, drop-in" rule-of-three and the "fast / low / happy" promo.
- Named the real interface (`key`, `ttl=`, `--ttl`, `no_cache=True`) instead of "per call".

**FILE**
- README.after.md
