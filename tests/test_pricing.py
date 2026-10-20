"""Pricing engine tests. This file should stay at 100% coverage of
pricing.py - it's pure functions over a rate table, the easiest and
most important code in the project to test.

Expectations are DERIVED from the rate card, not hardcoded, so updating
rates (Phase 0 calls, web-data refreshes) never breaks tests that are
really about the pricing math."""

from app.pricing import price, SPREAD_BY_TIER
from app.rate_cards import card_for
from app.scope import Scope

CARD = card_for("cedar")


def make_scope(**overrides) -> Scope:
    defaults = dict(
        linear_feet=20,
        material="cedar",
        damage_severity=3,
        gate_count=0,
        zip_code="90024",
        visibility_gaps=[],
    )
    defaults.update(overrides)
    return Scope(**defaults)


def test_mid_severity_prices_at_mid_rate():
    # severity 3 sits exactly between the card's low and high per-foot rates
    mid_rate = (CARD.repair_per_foot_low + CARD.repair_per_foot_high) / 2
    result = price(make_scope())
    assert result.expected_cost == round(max(20 * mid_rate, CARD.minimum_job), 0)


def test_severity_scales_the_rate():
    cheap = price(make_scope(damage_severity=1)).expected_cost
    pricey = price(make_scope(damage_severity=4)).expected_cost
    assert cheap == round(max(20 * CARD.repair_per_foot_low, CARD.minimum_job), 0)
    assert pricey > cheap


def test_minimum_job_floors_tiny_repairs():
    # 2 ft of cedar at any severity is under the truck-roll minimum.
    result = price(make_scope(linear_feet=2, damage_severity=1))
    assert result.expected_cost == CARD.minimum_job
    assert result.low == CARD.minimum_job


def test_gates_add_flat_cost():
    without = price(make_scope()).expected_cost
    with_gate = price(make_scope(gate_count=1)).expected_cost
    assert with_gate == without + CARD.per_gate


def test_ceiling_is_always_above_expected():
    result = price(make_scope())
    for tier in SPREAD_BY_TIER:
        assert result.ceiling(tier) > result.expected_cost


def test_same_scope_same_price_every_time():
    a = price(make_scope())
    b = price(make_scope())
    assert a == b  # deterministic: no randomness, no model calls
