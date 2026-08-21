# Visual direction for the itinerary HTML

The plan gets read one-handed, outdoors, in daylight, on a phone that has been
awake since 6am. Everything below follows from that.

- Warm paper palette: cream background, ink text, one accent colour picked from the destination (terracotta for California, indigo for Japan, moss for Scotland, etc.)
- Body in a serif stack (`Georgia, 'Iowan Old Style', Charter, serif`); headings and table headers in a sans stack (`'Helvetica Neue', Arial, sans-serif`)
- Mobile-first padding; respect notch and home indicator via `env(safe-area-inset-*)` inside `@supports (padding: max(0px))`
- Soft shadows and rounded corners (6–8 px) on cards and tables. Avoid heavy borders
- Today's card gets a tinted summary so the user can see at a glance which day is live
- A `@media (prefers-color-scheme: dark)` block, since the app opens full screen at night

Two more that matter on the day:

- Table rows want vertical breathing room. A time column scanned at a walking pace
  is easier to read loose than dense
- Nothing that depends on hover. The whole thing is touched, never pointed at
