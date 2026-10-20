"""Pricing engine tests. This file should stay at 100% coverage of
pricing.py - it's pure functions over a rate table, the easiest and
most important code in the project to test."""

from app.pricing import price, SPREAD_BY_TIER
from app.scope import Scope


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
    # cedar: 38-62 per ft; severity 3 -> midpoint 50/ft; 20 ft -> 1000
    result = price(make_scope())
    assert result.expected_cost == 1000


def test_severity_scales_the_rate():
    cheap = price(make_scope(damage_severity=1)).expected_cost
    pricey = price(make_scope(damage_severity=4)).expected_cost
    assert cheap == 20 * 38  # low end of the card
    assert pricey > cheap


def test_minimum_job_floors_tiny_repairs():
    # 2 ft of cedar at any severity is under the $350 minimum.
    result = price(make_scope(linear_feet=2, damage_severity=1))
    assert result.expected_cost == 350
    assert result.low == 350


def test_gates_add_flat_cost():
    without = price(make_scope()).expected_cost
    with_gate = price(make_scope(gate_count=1)).expected_cost
    assert with_gate == without + 275  # cedar per_gate


def test_ceiling_is_always_above_expected():
    result = price(make_scope())
    for tier in SPREAD_BY_TIER:
        assert result.ceiling(tier) > result.expected_cost


def test_same_scope_same_price_every_time():
    a = price(make_scope())
    b = price(make_scope())
    assert a == b  # deterministic: no randomness, no model calls
