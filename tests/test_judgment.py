"""The judgment seam: rules by default, Jev behind a flag, and both
speaking the same interface."""

import pytest

from app.judgment import JevJudge, RuleBasedJudge, get_judge
from app.scope import Scope


def test_default_judge_is_rules(monkeypatch):
    monkeypatch.delenv("PRICEVOW_JUDGE", raising=False)
    assert isinstance(get_judge(), RuleBasedJudge)


def test_flag_selects_jev(monkeypatch):
    monkeypatch.setenv("PRICEVOW_JUDGE", "jev")
    assert isinstance(get_judge(), JevJudge)


def test_rules_judge_matches_gate():
    scope = Scope(
        linear_feet=20, material="cedar", damage_severity=2,
        gate_count=0, zip_code="90024", visibility_gaps=[],
    )
    decision = RuleBasedJudge().assess(scope)
    assert decision.binds  # same behavior as gate.assess, through the seam


def test_jev_is_honest_about_not_existing_yet():
    scope = Scope(
        linear_feet=20, material="cedar", damage_severity=2,
        gate_count=0, zip_code="90024", visibility_gaps=[],
    )
    with pytest.raises(NotImplementedError):
        JevJudge().assess(scope)
