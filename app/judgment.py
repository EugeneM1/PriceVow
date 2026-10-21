"""The judgment layer's seam: where Jev plugs in at Phase 2.

Today the gate's rules (gate.py) make the bind decision. In Phase 2
those same questions go to Jev, TypeSafe AI's "System One" model:
structured judgments with probabilities in 70-500 ms, via the Vercel
AI Gateway model id typesafe-ai/jev.

This module defines the interface BOTH implementations satisfy, so
swapping rules -> Jev is a one-line config change, not a refactor:

    judge = get_judge()          # picks by PRICEVOW_JUDGE env var
    decision = judge.assess(scope)

The questions Jev will answer (from the design doc):
  - Is this scope complete enough to price?  -> yes/no probability
  - Hidden-risk flags present?               -> none / moderate / severe
  - Which capture gap matters most?          -> enum of gap types
  - Does footage now cover the gap?          -> yes / pan-left / closer / done
"""

import os
from typing import Protocol

from . import gate
from .gate import GateDecision
from .scope import Scope


class Judge(Protocol):
    """Anything that can turn a Scope into a bind decision."""

    name: str

    def assess(self, scope: Scope) -> GateDecision: ...


class RuleBasedJudge:
    """v0/v1: the hand-set rules in gate.py. Transparent, free, instant -
    and the baseline Jev has to beat on calibration data before it ships."""

    name = "rules-v0"

    def assess(self, scope: Scope) -> GateDecision:
        return gate.assess(scope)


class JevJudge:
    """Phase 2: Jev via the Vercel AI Gateway (model typesafe-ai/jev).

    Setup: get an AI Gateway API key from a Vercel account, then
        export AI_GATEWAY_API_KEY=...
        export PRICEVOW_JUDGE=jev

    Division of labor stays the same as the rules judge:
    - HARD invariants stay in code: severity 5 never binds, oversized
      jobs never bind. Exact rules are code's job, not a model's.
    - Jev answers the SOFT judgment the 0.12-per-gap heuristic answers
      today: given this scope, how safe is it to promise a ceiling?

    Jev's 'zero hallucination' means constrained OUTPUT, not correctness:
    it can be confidently wrong, so its probabilities only earn trust
    through the calibration report. Any API failure falls back to the
    rules judge - degrade toward rules, never toward a bad guarantee."""

    name = "jev-v1"

    ENDPOINT = "https://ai-gateway.vercel.sh/typesafe/v1/systemone"
    MODEL = "typesafe-ai/jev"

    def assess(self, scope: Scope) -> GateDecision:
        from .rate_cards import card_for

        # --- hard rules stay in code, exactly like the rules judge ---
        if scope.damage_severity >= 5:
            return GateDecision(
                bindable_prob=0.0,
                risk_tier="severe",
                reasons=["possible structural/rot damage - needs an in-person look"],
            )
        card = card_for(scope.material)
        if scope.linear_feet > card.max_bindable_feet:
            return GateDecision(
                bindable_prob=0.5,
                risk_tier="moderate",
                reasons=[
                    f"job larger than {card.max_bindable_feet:.0f} ft - "
                    "too big to bind sight-unseen",
                    "confidence too low to guarantee - a guided video would close the gaps",
                ],
            )

        # --- the soft judgment goes to Jev ---
        api_key = os.environ.get("AI_GATEWAY_API_KEY")
        if not api_key:
            return self._fallback(scope, "AI_GATEWAY_API_KEY not set")
        try:
            answers = self._ask_jev(api_key, scope)
        except Exception as exc:  # network, auth, schema - all degrade to rules
            return self._fallback(scope, f"Jev unavailable ({type(exc).__name__})")

        prob = float(answers["bindable"]["noul"])
        tier_answer = answers["risk"]["choice"]
        tier = "moderate" if (tier_answer == "moderate" or scope.damage_severity == 4) else "none"

        reasons = [f"Jev bindable probability {prob:.0%}, risk read: {tier_answer}"]
        reasons.extend(f"not visible: {g}" for g in scope.visibility_gaps)
        if prob >= gate.BIND_THRESHOLD and tier != "severe":
            reasons.append("scope complete - safe to guarantee")
        else:
            reasons.append(
                "confidence too low to guarantee - a guided video would close the gaps"
            )
        return GateDecision(bindable_prob=round(prob, 2), risk_tier=tier, reasons=reasons)

    def _ask_jev(self, api_key: str, scope: Scope) -> dict:
        import requests

        state = (
            f"Fence repair quote request. Material: {scope.material}. "
            f"Affected length: {scope.linear_feet} linear feet. "
            f"Damage severity: {scope.damage_severity} on a 1-5 scale "
            f"(1 cosmetic, 3 broken panels, 4 borderline structural). "
            f"Gates in the run: {scope.gate_count}. "
            f"Scope source: {scope.source}. "
            f"Things the photos/video did NOT show: "
            f"{', '.join(scope.visibility_gaps) or 'none - full coverage'}."
        )
        response = requests.post(
            self.ENDPOINT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.MODEL,
                "state": state,
                "questions": {
                    "bindable": {
                        "type": "noul",
                        "instructions": (
                            "Is this scope complete and unambiguous enough for a "
                            "pricing platform to commit a guaranteed maximum price "
                            "without a site visit?"
                        ),
                    },
                    "risk": {
                        "type": "choice",
                        "instructions": "How much cost-overrun risk does this scope carry?",
                        "criteria": {
                            "none": "Fully visible, standard repair, no surprises likely",
                            "moderate": "Some uncertainty: coverage gaps, borderline damage",
                        },
                    },
                },
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["answers"]

    def _fallback(self, scope: Scope, why: str) -> GateDecision:
        decision = gate.assess(scope)
        return GateDecision(
            bindable_prob=decision.bindable_prob,
            risk_tier=decision.risk_tier,
            reasons=[f"rules fallback: {why}"] + decision.reasons,
        )


def get_judge() -> Judge:
    """Pick the judgment backend. Defaults to rules; this is the feature
    flag the design doc's error-handling table calls for."""
    choice = os.environ.get("PRICEVOW_JUDGE", "rules").lower()
    if choice == "jev":
        return JevJudge()
    return RuleBasedJudge()
