"""Calibration loop tests: record quotes, record invoiced costs, and
score the predictions - including the Phase 0 gate check itself."""

import os

import pytest

from app import calibration
from app.gate import assess
from app.pricing import price
from app.scope import Scope


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    """Every test gets its own throwaway database file."""
    monkeypatch.setenv("PRICEVOW_DB", str(tmp_path / "test.db"))


def quote_one(**overrides) -> tuple[str, float]:
    """Issue a quote the way main.py does; return (job_id, expected_cost)."""
    defaults = dict(
        linear_feet=20,
        material="cedar",
        damage_severity=3,
        gate_count=0,
        zip_code="90024",
        visibility_gaps=[],
    )
    defaults.update(overrides)
    scope = Scope(**defaults)
    decision = assess(scope)
    result = price(scope)
    return calibration.record_quote(scope, decision, result), result.expected_cost


def test_quote_is_recorded_and_listed():
    job_id, _ = quote_one()
    jobs = calibration.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["invoiced_cost"] is None  # nothing invoiced yet


def test_invoice_scores_the_prediction():
    job_id, expected = quote_one()
    # Contractor reports the job cost 10% more than we predicted.
    calibration.record_invoice(job_id, expected * 1.10)
    r = calibration.report()
    assert r.jobs_invoiced == 1
    assert r.median_abs_error_pct == pytest.approx(9.1, abs=0.2)  # 0.1/1.1


def test_overrun_is_counted_when_invoice_blows_the_ceiling():
    job_id, expected = quote_one()  # clean scope -> binds with 12% spread
    calibration.record_invoice(job_id, expected * 2)  # way over the ceiling
    r = calibration.report()
    assert r.overruns == 1
    assert r.overrun_paid_total > 0


def test_phase0_gate_needs_five_accurate_jobs():
    ids = [quote_one(linear_feet=10 + i)[0] for i in range(5)]
    # First four accurate, gate still closed (only 4 invoiced).
    for job_id in ids[:4]:
        exp = next(j["expected_cost"] for j in calibration.list_jobs() if j["id"] == job_id)
        calibration.record_invoice(job_id, exp * 1.05)
    assert not calibration.report().passes_phase0_gate
    # Fifth accurate job opens the gate.
    exp = next(j["expected_cost"] for j in calibration.list_jobs() if j["id"] == ids[4])
    calibration.record_invoice(ids[4], exp * 0.95)
    r = calibration.report()
    assert r.passes_phase0_gate
    assert r.median_abs_error_pct <= 15


def test_invoice_for_unknown_job_is_rejected():
    with pytest.raises(ValueError):
        calibration.record_invoice("PV-NOPE00", 500)


def test_booking_a_bound_quote():
    job_id, _ = quote_one()  # clean scope -> bound
    calibration.record_booking(job_id)
    job = next(j for j in calibration.list_jobs() if j["id"] == job_id)
    assert job["booked"] == 1


def test_unbound_quote_cannot_be_booked():
    job_id, _ = quote_one(damage_severity=5)  # never binds
    with pytest.raises(ValueError):
        calibration.record_booking(job_id)
