"""Contractor rate cards.

A rate card is a contractor's pre-committed pricing rule. In Phase 0
these numbers come from calling 10-15 LA fence contractors; until then
the figures below are PLACEHOLDERS so the pipeline runs end to end.

!! PLACEHOLDER DATA - replace with real Phase 0 numbers before any
!! quote is shown to a real homeowner.

Rate cards are versioned: never edit a card in place once a quote has
been issued from it - add a new version instead, so every bound quote
traces back to the exact rule that backed it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RateCard:
    version: str
    material: str
    repair_per_foot_low: float  # USD per linear foot, light repair
    repair_per_foot_high: float  # USD per linear foot, heavy repair
    per_gate: float  # extra per gate in the affected run
    minimum_job: float  # contractor won't roll a truck for less
    max_bindable_feet: float  # above this, too big to bind sight-unseen


# One card per material. version "v0-placeholder" marks fake numbers.
RATE_CARDS: dict[str, RateCard] = {
    "cedar": RateCard("v0-placeholder", "cedar", 38.0, 62.0, 275.0, 350.0, 80.0),
    "vinyl": RateCard("v0-placeholder", "vinyl", 42.0, 70.0, 325.0, 400.0, 80.0),
    "chain-link": RateCard("v0-placeholder", "chain-link", 22.0, 40.0, 225.0, 300.0, 120.0),
    "wrought-iron": RateCard("v0-placeholder", "wrought-iron", 55.0, 95.0, 400.0, 500.0, 60.0),
}


def card_for(material: str) -> RateCard:
    try:
        return RATE_CARDS[material]
    except KeyError:
        raise ValueError(f"no rate card covers material {material!r}") from None
