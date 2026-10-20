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

    Not implemented yet - we are on the access waitlist. When the key
    arrives, this class sends the scope as structured context with the
    question set above and maps Jev's probabilities onto GateDecision.
    Jev's 'zero hallucination' means constrained OUTPUT, not correctness:
    it can be confidently wrong, so its probabilities only earn trust
    through the calibration report, never by default."""

    name = "jev-v1"

    def assess(self, scope: Scope) -> GateDecision:  # pragma: no cover
        raise NotImplementedError(
            "Jev access pending (waitlist / Vercel AI Gateway). "
            "Set PRICEVOW_JUDGE=rules until then."
        )


def get_judge() -> Judge:
    """Pick the judgment backend. Defaults to rules; this is the feature
    flag the design doc's error-handling table calls for."""
    choice = os.environ.get("PRICEVOW_JUDGE", "rules").lower()
    if choice == "jev":
        return JevJudge()
    return RuleBasedJudge()
