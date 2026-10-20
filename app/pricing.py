"""The pricing engine: scope x rate card = price.

Deliberately boring. No AI in this file - pricing must be explainable,
testable, and reproducible, because money depends on it. Think of the
guarantee ceiling like a market maker's quote: expected cost plus a
spread that pays for the risk we're taking on.
"""

from dataclasses import dataclass

from .rate_cards import RateCard, card_for
from .scope import Scope

# How the per-foot rate scales with damage severity (1-5).
# Severity 1 prices at the card's low rate, severity 5 at the high rate.
def _severity_fraction(severity: int) -> float:
    return (severity - 1) / 4.0  # 1 -> 0.0, 3 -> 0.5, 5 -> 1.0


# Risk spread by tier: the margin we add on top of expected cost before
# we promise a ceiling. These get re-tuned weekly by the calibration
# service once real predicted-vs-invoiced data exists.
SPREAD_BY_TIER = {
    "none": 0.12,  # clean scope: promise 12% above expected
    "moderate": 0.22,  # some uncertainty: wider spread
    # "severe" never gets a ceiling at all - see gate.py
}


@dataclass(frozen=True)
class PriceResult:
    expected_cost: float  # our best single estimate, USD
    low: float  # optimistic end of the range
    high: float  # pessimistic end of the range
    rate_card_version: str

    def ceiling(self, risk_tier: str) -> float:
        """The guaranteed maximum price for a given risk tier."""
        spread = SPREAD_BY_TIER[risk_tier]
        return round(self.expected_cost * (1 + spread), 0)


def price(scope: Scope) -> PriceResult:
    """Pure function: same scope in, same price out, every time."""
    card: RateCard = card_for(scope.material)

    frac = _severity_fraction(scope.damage_severity)
    per_foot = card.repair_per_foot_low + frac * (
        card.repair_per_foot_high - card.repair_per_foot_low
    )

    base = scope.linear_feet * per_foot + scope.gate_count * card.per_gate
    expected = max(base, card.minimum_job)

    # The range reflects the card's own low/high band, floored at the
    # minimum job - a 4-foot patch still costs the truck roll.
    low = max(scope.linear_feet * card.repair_per_foot_low
              + scope.gate_count * card.per_gate, card.minimum_job)
    high = max(scope.linear_feet * card.repair_per_foot_high
               + scope.gate_count * card.per_gate, card.minimum_job)

    return PriceResult(
        expected_cost=round(expected, 0),
        low=round(low, 0),
        high=round(high, 0),
        rate_card_version=card.version,
    )
