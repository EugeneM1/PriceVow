"""The calibration loop - PriceVow's moat.

Every quote we issue gets recorded. Every invoiced cost a contractor
reports gets matched to its quote. The gap between the two, tracked
per zip and job type over time, is what lets us (a) prove the <=15%
accuracy gate, (b) re-tune bind thresholds and risk spreads, and
(c) own a dataset no competitor can scrape.

Same math as scoring a prediction market book: predicted vs. realized,
median absolute error, and how often our promised ceiling got blown
through (an "overrun" - the guarantee paying out).
"""

from dataclasses import dataclass
from statistics import median

from . import db
from .gate import GateDecision
from .pricing import PriceResult
from .scope import Scope


def record_quote(scope: Scope, decision: GateDecision, result: PriceResult) -> str:
    """Persist one issued quote. Returns the job id shown to the homeowner."""
    job_id = db.new_job_id()
    ceiling = result.ceiling(decision.risk_tier) if decision.binds else None
    with db.connect() as conn:
        conn.execute(
            """INSERT INTO jobs (id, created_at, zip_code, trade, scope_json,
                   scope_source, bindable_prob, risk_tier, expected_cost,
                   low, high, ceiling, bound, rate_card_version)
               VALUES (?, ?, ?, 'fence', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id,
                db.now_iso(),
                scope.zip_code,
                db.scope_to_json(scope),
                scope.source,
                decision.bindable_prob,
                decision.risk_tier,
                result.expected_cost,
                result.low,
                result.high,
                ceiling,
                int(decision.binds),
                result.rate_card_version,
            ),
        )
    return job_id


def record_booking(job_id: str) -> None:
    """The homeowner accepted a bound quote at its ceiling."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT bound FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if not row:
            raise ValueError(f"no job {job_id!r}")
        if not row["bound"]:
            raise ValueError("only bound quotes (with a ceiling) can be booked")
        conn.execute("UPDATE jobs SET booked = 1 WHERE id = ?", (job_id,))


def record_invoice(job_id: str, invoiced_cost: float) -> None:
    """A contractor reported what the job actually cost. This is the
    ground truth every prediction gets scored against."""
    if invoiced_cost <= 0:
        raise ValueError("invoiced_cost must be positive")
    with db.connect() as conn:
        exists = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not exists:
            raise ValueError(f"no job {job_id!r}")
        conn.execute(
            """INSERT INTO invoices (job_id, invoiced_cost, recorded_at)
               VALUES (?, ?, ?)
               ON CONFLICT(job_id) DO UPDATE SET
                   invoiced_cost = excluded.invoiced_cost,
                   recorded_at = excluded.recorded_at""",
            (job_id, invoiced_cost, db.now_iso()),
        )


@dataclass(frozen=True)
class Report:
    quotes_issued: int
    quotes_bound: int
    jobs_invoiced: int
    median_abs_error_pct: float | None  # None until something is invoiced
    overruns: int  # invoiced above the promised ceiling
    overrun_paid_total: float  # what the guarantee cost us

    @property
    def passes_phase0_gate(self) -> bool:
        """The design-doc gate: <=15% median error (and data to prove it)."""
        return (
            self.median_abs_error_pct is not None
            and self.jobs_invoiced >= 5
            and self.median_abs_error_pct <= 15.0
        )


def report() -> Report:
    """Score every invoiced job against what we predicted."""
    with db.connect() as conn:
        totals = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(bound), 0) AS b FROM jobs"
        ).fetchone()
        rows = conn.execute(
            """SELECT j.expected_cost, j.ceiling, j.bound, i.invoiced_cost
               FROM jobs j JOIN invoices i ON i.job_id = j.id"""
        ).fetchall()

    errors = [
        abs(r["invoiced_cost"] - r["expected_cost"]) / r["invoiced_cost"] * 100
        for r in rows
    ]
    overrun_amounts = [
        r["invoiced_cost"] - r["ceiling"]
        for r in rows
        if r["bound"] and r["ceiling"] is not None and r["invoiced_cost"] > r["ceiling"]
    ]
    return Report(
        quotes_issued=totals["n"],
        quotes_bound=totals["b"],
        jobs_invoiced=len(rows),
        median_abs_error_pct=round(median(errors), 1) if errors else None,
        overruns=len(overrun_amounts),
        overrun_paid_total=round(sum(overrun_amounts), 2),
    )


@dataclass(frozen=True)
class Tuning:
    """Recommended risk spreads, derived from realized cost overshoots.

    The spread is the margin added to expected cost before we promise a
    ceiling - a market maker's edge. We set it so the ceiling would have
    covered ~90% of historical invoiced costs in that tier, plus a small
    buffer. Recommendations only; a human updates SPREAD_BY_TIER."""

    samples_per_tier: dict[str, int]
    suggested_spread_per_tier: dict[str, float]  # e.g. {"none": 0.10}
    current_spread_per_tier: dict[str, float]

    MIN_SAMPLES = 10  # below this, keep the hand-set spreads


def suggest_tuning() -> Tuning:
    from .pricing import SPREAD_BY_TIER  # avoid import cycle at module load

    with db.connect() as conn:
        rows = conn.execute(
            """SELECT j.risk_tier, j.expected_cost, i.invoiced_cost
               FROM jobs j JOIN invoices i ON i.job_id = j.id
               WHERE j.risk_tier != 'severe'"""
        ).fetchall()

    by_tier: dict[str, list[float]] = {}
    for r in rows:
        overshoot = r["invoiced_cost"] / r["expected_cost"] - 1  # +0.08 = 8% over
        by_tier.setdefault(r["risk_tier"], []).append(overshoot)

    suggested: dict[str, float] = {}
    counts: dict[str, int] = {}
    for tier, overshoots in by_tier.items():
        counts[tier] = len(overshoots)
        if len(overshoots) < Tuning.MIN_SAMPLES:
            continue  # not enough data - no recommendation
        overshoots.sort()
        # 90th-percentile overshoot + 3 points of buffer, floored at 5%.
        p90 = overshoots[min(len(overshoots) - 1, int(0.9 * len(overshoots)))]
        suggested[tier] = round(max(0.05, p90 + 0.03), 2)

    return Tuning(
        samples_per_tier=counts,
        suggested_spread_per_tier=suggested,
        current_spread_per_tier=dict(SPREAD_BY_TIER),
    )


def list_jobs(limit: int = 50) -> list[dict]:
    """Newest quotes first, with any invoiced cost joined on."""
    with db.connect() as conn:
        rows = conn.execute(
            """SELECT j.*, i.invoiced_cost
               FROM jobs j LEFT JOIN invoices i ON i.job_id = j.id
               ORDER BY j.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
