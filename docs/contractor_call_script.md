# Phase 0 contractor call script

Goal per call (10 minutes): prices for the 5 golden-set jobs, the
contractor's real minimums, and a read on whether they'd honor
pre-scoped quotes for free leads. Log everything in
data/golden_set_template.csv right after hanging up.

## Who to call

Search "fence repair" + each area (Westwood, Culver City, Mar Vista,
Palms, Santa Monica). Skip the big franchises - owner-operators with
2-20 reviews pick up their own phone and set their own prices.

## The script

**Opening (honest, not a fake customer):**
> "Hi - my name's Eugene, I'm a UCLA student building a tool that sends
> fence contractors pre-scoped repair jobs, photos and measurements
> already done, no estimate visit needed. I'm pricing it against real
> contractors right now - can I get your take on five quick jobs?
> Takes five minutes, and if it's useful I'd like to send you the first
> leads free."

**The five jobs (read each, note their number):**
1. Three leaning cedar panels in Westwood, posts intact, ~18 ft.
2. Wind-blown vinyl section near Sawtelle, two panels snapped, ~12 ft.
3. Chain-link sagging along a Mar Vista driveway, ~30 ft.
4. Cedar gate dragging in Palms, hinge post loose.
5. Full cedar run after a car impact in West LA, ~40 ft, posts included.

**The three follow-ups that matter more than the prices:**
- "What's your minimum to roll a truck?"
- "Biggest thing that changes the price once you're on site?"
  (their answer = your hidden-risk rules in gate.py)
- "If I sent you a job with photos, measurements, and a homeowner ready
  to book at a price in your range - would you take it at that price?"
  (a yes = a Phase 1 contractor partner; get their email)

## Logging

- One column per contractor in the golden-set CSV; compute the median.
- Note every "depends on..." - those become visibility_gaps and
  never-bind rules.
- After ~10 calls: update LA_FACTOR and the per-foot bands in
  app/rate_cards.py from the medians, bump the version string, and run
  pytest (tests derive from the card, so they'll still pass).

## Rules

- Never pose as a homeowner. The honest pitch works better anyway -
  contractors hate estimate visits that don't convert.
- If they're busy, ask for a better time and move on. Volume beats
  persistence.
