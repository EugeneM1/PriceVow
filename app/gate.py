"""The guarantee gate: the binding decision.

This is where PriceVow differs from every estimate tool - we only
promise a ceiling when we're confident enough to put money behind it.
The system always degrades toward LESS commitment, never toward a bad
guarantee.

v0 computes the bindable probability with simple hand-set rules. In
Phase 2 this becomes a Jev (TypeSafe AI) question set returning real
calibrated probabilities; the interface below stays the same, which is
why it already returns a probability instead of a plain yes/no.
"""

from dataclasses import dataclass

from .rate_cards import card_for
from .scope import Scope

# Bind only above this probability. Starts conservative; the calibration
# service re-tunes it once predicted-vs-invoiced data exists.
BIND_THRESHOLD = 0.90


@dataclass(frozen=True)
class GateDecision:
    bindable_prob: float  # 0..1
    risk_tier: str  # "none" | "moderate" | "severe"
    reasons: list[str]  # human-readable, shown to the homeowner

    @property
    def binds(self) -> bool:
        return self.risk_tier != "severe" and self.bindable_prob >= BIND_THRESHOLD


def assess(scope: Scope) -> GateDecision:
    """Score how safe this scope is to guarantee."""
    prob = 1.0
    reasons: list[str] = []

    # --- hard risk rules -------------------------------------------------
    # Severity 5 means possible rot/structural problems hiding below
    # ground. We NEVER bind those - invariant tested in tests/test_gate.py.
    if scope.damage_severity >= 5:
        return GateDecision(
            bindable_prob=0.0,
            risk_tier="severe",
            reasons=["possible structural/rot damage - needs an in-person look"],
        )

    card = card_for(scope.material)
    if scope.linear_feet > card.max_bindable_feet:
        prob -= 0.35
        reasons.append(
            f"job larger than {card.max_bindable_feet:.0f} ft - too big to bind sight-unseen"
        )

    # --- soft confidence rules -------------------------------------------
    # Every visibility gap chips away at confidence.
    gap_penalty = 0.12 * len(scope.visibility_gaps)
    if gap_penalty:
        prob -= gap_penalty
        reasons.extend(f"not visible: {g}" for g in scope.visibility_gaps)

    # Severity 4 is borderline - price it, but with a wider spread.
    tier = "moderate" if (scope.damage_severity == 4 or reasons) else "none"

    prob = max(0.0, min(1.0, prob))
    if prob >= BIND_THRESHOLD:
        reasons.append("scope complete - safe to guarantee")
    else:
        reasons.append("confidence too low to guarantee - a guided video would close the gaps")

    return GateDecision(bindable_prob=round(prob, 2), risk_tier=tier, reasons=reasons)
