"""Contractor rate cards.

A rate card is a contractor's pre-committed pricing rule. The figures
below are v0.1 ESTIMATES derived from free national cost-guide data
(Oct 2026), adjusted to Los Angeles - good enough to sanity-check
contractor calls, NOT yet prices anyone has committed to honor.

!! Phase 0 contractor calls replace these with real committed LA
!! prices before any quote is shown to a real homeowner.

Sources (national figures, repairs incl. labor + materials):
- Fixr fence repair guide (updated Jan 2025): repairs $10-50/ft;
  wood $400-600, vinyl $200-700, chain-link $300-600, wrought iron
  $300-1,000 per job; gate repair $150-500; call-out fees $75-100.
  https://fixr.com/costs/fence-repair
- HomeGnome 2026 guide: repairs $14-48/ft; chain-link $200-567,
  wood $220-600, vinyl $225-750, wrought iron $300-1,067 per job;
  gate repair/replacement $125-513; post replacement $160-450.
  https://homegnome.com/blog/cost/fence-repair-price/
- HomeAdvisor: national avg $618 (range $304-948); ~$30/ft average
  (wood & chain-link ~$20/ft, wrought iron ~$30/ft); gate repair
  $100-400; post replacement ~$270; labor ~$50/hr.
  https://www.homeadvisor.com/cost/fencing/repair-a-fence

LA adjustment: national figures x LA_FACTOR for the LA metro's labor
premium. 1.20 is an assumption, not data - Phase 0 calls will tell us
the real local multiple.

Rate cards are versioned: never edit a card in place once a quote has
been issued from it - add a new version instead, so every bound quote
traces back to the exact rule that backed it.
"""

from dataclasses import dataclass

LA_FACTOR = 1.20  # assumed LA labor premium over national; replace via Phase 0

VERSION = "v0.1-webdata-2026-10"


@dataclass(frozen=True)
class RateCard:
    version: str
    material: str
    repair_per_foot_low: float  # USD per linear foot, light repair
    repair_per_foot_high: float  # USD per linear foot, heavy repair
    per_gate: float  # extra per gate in the affected run
    minimum_job: float  # contractor won't roll a truck for less
    max_bindable_feet: float  # above this, too big to bind sight-unseen


def _la(national: float) -> float:
    """Round an LA-adjusted national figure to whole dollars."""
    return round(national * LA_FACTOR, 0)


# Per-foot national bands derived from the sources above:
# - wood/cedar: ~$20/ft light (HomeAdvisor) up to ~$40/ft for heavy
#   panel/rot work (Fixr $400-600 jobs over typical 15-20 ft runs);
#   cedar carries a small material premium over pine.
# - vinyl: panel-driven; $225-750 jobs over ~8-16 ft runs => ~$20-55/ft.
# - chain-link: cheapest per foot (~$20/ft HomeAdvisor) across longer
#   runs; $200-600 jobs over 25-40 ft => ~$10-22/ft.
# - wrought iron: welding work; ~$30/ft light up to ~$60/ft heavy
#   ($300-1,067 jobs over short 8-18 ft sections).
RATE_CARDS: dict[str, RateCard] = {
    "cedar": RateCard(
        VERSION, "cedar",
        repair_per_foot_low=_la(21), repair_per_foot_high=_la(42),
        per_gate=_la(300),  # gate repair mid of $100-513 across sources
        minimum_job=_la(250),  # call-out + smallest real job
        max_bindable_feet=80.0,
    ),
    "vinyl": RateCard(
        VERSION, "vinyl",
        repair_per_foot_low=_la(20), repair_per_foot_high=_la(55),
        per_gate=_la(300),
        minimum_job=_la(275),
        max_bindable_feet=80.0,
    ),
    "chain-link": RateCard(
        VERSION, "chain-link",
        repair_per_foot_low=_la(10), repair_per_foot_high=_la(22),
        per_gate=_la(250),
        minimum_job=_la(225),
        max_bindable_feet=120.0,
    ),
    "wrought-iron": RateCard(
        VERSION, "wrought-iron",
        repair_per_foot_low=_la(30), repair_per_foot_high=_la(60),
        per_gate=_la(400),
        minimum_job=_la(375),
        max_bindable_feet=60.0,
    ),
}


def card_for(material: str) -> RateCard:
    try:
        return RATE_CARDS[material]
    except KeyError:
        raise ValueError(f"no rate card covers material {material!r}") from None
