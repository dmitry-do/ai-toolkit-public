# samples

Input for `shots.py`, not part of any plugin. These files sit here rather than in
`plugins/trip-plan/` because they'd otherwise install with the plugin and upload with the skill,
and nothing at runtime reads them.

`tokyo-2026-12.{md,json,html}` is one week in Tokyo, 23–29 December 2026, carried through all three
trip-plan phases: the Markdown plan, the same seven days as `route_check.py` input, and the
delivered single-file HTML. The screenshot in the trip-plan README is a photograph of these two:

```bash
python3 scripts/docs-assets/shots.py trip-plan
```

The trip is invented and the hours, ratings and prices are illustrative — plausible rather than
researched. They exist so the screenshot shows a real page with real constraints in it, not lorem
ipsum. The constraints that shape the week are the true ones: museums that shut for the year end,
weekly closing days, and an observatory deck that closes on fourth Mondays.

Both files still hold up under the plugin's own checks, which is the point of keeping them:

```bash
SK=plugins/trip-plan/skills/trip-plan
python3 "$SK/scripts/route_check.py" scripts/docs-assets/samples/tokyo-2026-12.json
python3 "$SK/scripts/scrub_check.py" scripts/docs-assets/samples/tokyo-2026-12.html
```

```
Order holds: nothing shut, nothing late, no day over its hours.
No blocking findings. Confirm the flagged items are public venue details.
```

The scrub scan prints seven `check` lines — "door code", "password", "booking", "Passport" — and no
blocking ones. That's the intended end state: the *fact* is in the plan ("the door code is in your
password manager", "ref in email") and the *value* never is.
