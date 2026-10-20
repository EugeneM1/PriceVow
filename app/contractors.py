"""The contractor side of the marketplace.

Contractors who agreed (Phase 0 calls) to honor pre-scoped quotes get
registered here. When a homeowner books a bound quote, the job is
OFFERED to one matching contractor at a time. A decline triggers an
automatic re-offer to the next match - the design doc's fallback - and
the decline reason is logged, because "why contractors say no" is the
raw material for better never-bind rules.

The guarantee math only works if every bound quote has a contractor
behind it, so booking without any matching contractor raises instead
of silently promising labor nobody committed.
"""

import uuid
from dataclasses import dataclass

from . import db


@dataclass(frozen=True)
class Contractor:
    id: str
    name: str
    email: str
    zips: list[str]
    active: bool


def add_contractor(name: str, email: str, zips: list[str]) -> str:
    """Register a contractor and the ZIPs they serve."""
    if not zips:
        raise ValueError("a contractor must serve at least one ZIP")
    contractor_id = "CTR-" + uuid.uuid4().hex[:6].upper()
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO contractors (id, name, email, zips) VALUES (?, ?, ?, ?)",
            (contractor_id, name.strip(), email.strip(), ",".join(z.strip() for z in zips)),
        )
    return contractor_id


def list_contractors() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM contractors ORDER BY name"
        ).fetchall()
    return [dict(r) for r in rows]


def _matching_contractors(conn, zip_code: str) -> list[dict]:
    # rowid = registration order: earliest-signed partners get first offer.
    # (Ordering by the random hex id made "first" a coin flip - real bug.)
    rows = conn.execute(
        "SELECT * FROM contractors WHERE active = 1 ORDER BY rowid"
    ).fetchall()
    return [dict(r) for r in rows if zip_code in r["zips"].split(",")]


def offer_job(job_id: str) -> str:
    """Offer a booked job to the first matching contractor who has not
    already declined it. Returns the contractor id."""
    with db.connect() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            raise ValueError(f"no job {job_id!r}")
        already = {
            r["contractor_id"]
            for r in conn.execute(
                "SELECT contractor_id FROM job_offers WHERE job_id = ?", (job_id,)
            ).fetchall()
        }
        candidates = [
            c for c in _matching_contractors(conn, job["zip_code"])
            if c["id"] not in already
        ]
        if not candidates:
            raise LookupError(
                f"no active contractor covers ZIP {job['zip_code']} for {job_id}"
            )
        chosen = candidates[0]
        conn.execute(
            """INSERT INTO job_offers (job_id, contractor_id, status, created_at)
               VALUES (?, ?, 'pending', ?)""",
            (job_id, chosen["id"], db.now_iso()),
        )
    return chosen["id"]


def decide_offer(offer_id: int, accept: bool, reason: str = "") -> str | None:
    """Record the contractor's decision. A decline automatically re-offers
    the job to the next matching contractor; returns that contractor's id,
    or None when accepted or when nobody is left (then the homeowner gets
    released - the error-handling table's last resort)."""
    with db.connect() as conn:
        offer = conn.execute(
            "SELECT * FROM job_offers WHERE id = ?", (offer_id,)
        ).fetchone()
        if not offer:
            raise ValueError(f"no offer {offer_id!r}")
        if offer["status"] != "pending":
            raise ValueError("offer already decided")
        conn.execute(
            "UPDATE job_offers SET status = ?, reason = ?, decided_at = ? WHERE id = ?",
            ("accepted" if accept else "declined", reason.strip(), db.now_iso(), offer_id),
        )
    if accept:
        return None
    try:
        return offer_job(offer["job_id"])
    except LookupError:
        return None  # nobody left - release the homeowner, apologize, credit


def offers_for_job(job_id: str) -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT o.*, c.name AS contractor_name
               FROM job_offers o JOIN contractors c ON c.id = o.contractor_id
               WHERE o.job_id = ? ORDER BY o.id""",
            (job_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def pending_offers() -> list[dict]:
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT o.*, c.name AS contractor_name, j.zip_code, j.ceiling,
                      j.expected_cost
               FROM job_offers o
               JOIN contractors c ON c.id = o.contractor_id
               JOIN jobs j ON j.id = o.job_id
               WHERE o.status = 'pending' ORDER BY o.id""",
        ).fetchall()
    return [dict(r) for r in rows]
