## Onboarding Redesign Sync

### TLDR
The team is cutting signup from five screens to three: signup goes email-only, and phone verification moves to a soft prompt after the first session. Phone verification is the biggest leak — about 40% of users drop between screens two and three. Welcome-screen copy will be settled by an A/B test rather than debate. One open risk: legal and the fraud team need to sign off on dropping phone verification before anything ships.

### Key discussion points
- Drop-off data: roughly 40% of users are lost between screen two and screen three, and the phone verification step is the worst offender.
- Proposal to keep signup email-only and move phone verification to a later soft prompt, after the first session.
- Welcome-screen copy is contested — marketing wants it punchier, and the current draft has pushback. Suggestion: A/B test it instead of arguing.
- Open risk: dropping phone verification may need legal and fraud-team sign-off. The fraud team raised concerns the last time this came up.

### Decisions made
- Signup goes email-only; phone verification is deferred to a soft prompt after the first session.
- Welcome-screen copy will be decided by an A/B test, not internal debate.

### Action items
- [ ] Draft the spec for email-only signup with deferred phone verification -- Marcus, by end of next week
- [ ] Set up the welcome-copy A/B test, once the spec lands -- Dana, after the spec
- [ ] Check with legal and the fraud team before committing to ship -- Priya, before launch

### Next steps
Marcus's spec is the gating item — the A/B test waits on it. Priya's legal and fraud check runs in parallel and has to clear before any ship decision.
