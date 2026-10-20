"""Guarantee gate tests, including the one invariant that must never
break: severe-risk jobs never get a guaranteed ceiling."""

from app.gate import assess, BIND_THRESHOLD
from app.scope import Scope


def make_scope(**overrides) -> Scope:
    defaults = dict(
        linear_feet=20,
        material="cedar",
        damage_severity=2,
        gate_count=0,
        zip_code="90024",
        visibility_gaps=[],
    )
    defaults.update(overrides)
    return Scope(**defaults)


def test_clean_scope_binds():
    decision = assess(make_scope())
    assert decision.binds
    assert decision.risk_tier == "none"
    assert decision.bindable_prob >= BIND_THRESHOLD


def test_never_bind_severe_damage():
    # THE invariant: severity 5 (possible rot/structural) never binds,
    # no matter how clean everything else looks.
    decision = assess(make_scope(damage_severity=5))
    assert decision.risk_tier == "severe"
    assert not decision.binds
    assert decision.bindable_prob == 0.0


def test_visibility_gaps_lower_confidence():
    clean = assess(make_scope())
    gappy = assess(make_scope(visibility_gaps=["post footings not visible"]))
    assert gappy.bindable_prob < clean.bindable_prob
    assert gappy.risk_tier == "moderate"


def test_enough_gaps_block_the_bind():
    decision = assess(
        make_scope(visibility_gaps=["no photos provided", "far end cut off"])
    )
    assert not decision.binds
    # The homeowner should be told what unlocks the guarantee.
    assert any("guided video" in r for r in decision.reasons)


def test_oversized_jobs_do_not_bind():
    # cedar max_bindable_feet is 80 in the placeholder card.
    decision = assess(make_scope(linear_feet=150))
    assert not decision.binds
