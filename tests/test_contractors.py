"""Contractor marketplace tests: matching by ZIP, offer sequencing, and
the decline -> auto-reoffer -> release chain from the error-handling table."""

import pytest

from app import calibration, contractors
from app.gate import assess
from app.pricing import price
from app.scope import Scope


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("PRICEVOW_DB", str(tmp_path / "test.db"))


def booked_job(zip_code="90024") -> str:
    scope = Scope(
        linear_feet=20, material="cedar", damage_severity=3,
        gate_count=0, zip_code=zip_code, visibility_gaps=[],
    )
    job_id = calibration.record_quote(scope, assess(scope), price(scope))
    calibration.record_booking(job_id)
    return job_id


def test_offer_goes_to_a_matching_contractor():
    ctr = contractors.add_contractor("Westwood Fence Co", "wf@example.com", ["90024"])
    job_id = booked_job(zip_code="90024")
    assert contractors.offer_job(job_id) == ctr
    offers = contractors.offers_for_job(job_id)
    assert len(offers) == 1 and offers[0]["status"] == "pending"


def test_no_matching_zip_raises_instead_of_promising_labor():
    contractors.add_contractor("Valley Fence", "", ["91401"])  # wrong ZIP
    job_id = booked_job(zip_code="90024")
    with pytest.raises(LookupError):
        contractors.offer_job(job_id)


def test_decline_reoffers_to_the_next_contractor():
    first = contractors.add_contractor("A Fence", "", ["90024"])
    second = contractors.add_contractor("B Fence", "", ["90024"])
    job_id = booked_job()
    assert contractors.offer_job(job_id) == first
    offer = contractors.offers_for_job(job_id)[0]
    next_ctr = contractors.decide_offer(offer["id"], accept=False, reason="too far")
    assert next_ctr == second
    offers = contractors.offers_for_job(job_id)
    assert [o["status"] for o in offers] == ["declined", "pending"]
    assert offers[0]["reason"] == "too far"  # decline reasons feed rule tuning


def test_everyone_declining_releases_the_homeowner():
    contractors.add_contractor("Only Fence", "", ["90024"])
    job_id = booked_job()
    contractors.offer_job(job_id)
    offer = contractors.offers_for_job(job_id)[0]
    # The last decline returns None: nobody left, homeowner gets released.
    assert contractors.decide_offer(offer["id"], accept=False) is None


def test_accept_closes_the_offer():
    contractors.add_contractor("A Fence", "", ["90024"])
    contractors.add_contractor("B Fence", "", ["90024"])
    job_id = booked_job()
    contractors.offer_job(job_id)
    offer = contractors.offers_for_job(job_id)[0]
    assert contractors.decide_offer(offer["id"], accept=True) is None
    assert contractors.offers_for_job(job_id)[0]["status"] == "accepted"
    with pytest.raises(ValueError):  # no double-deciding
        contractors.decide_offer(offer["id"], accept=False)
