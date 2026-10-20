"""Backtest the pricing engine against the golden set.

Run this AFTER the Phase 0 contractor calls, once median_price is
filled in for each row of data/golden_set_template.csv:

    python3 -m scripts.backtest

It prices every golden-set job with the current rate cards and scores
the predictions against the contractor medians - the same <=15% gate
the live calibration report enforces, but runnable before a single
real customer exists. Rerun it after every rate-card change; the
design doc calls this the prompt/rate regression check.
"""

import csv
import sys
from pathlib import Path
from statistics import median

from app.pricing import price
from app.scope import Scope

GOLDEN = Path(__file__).resolve().parent.parent / "data" / "golden_set_template.csv"
GATE_PCT = 15.0


def run(path: Path = GOLDEN) -> int:
    rows = list(csv.DictReader(path.open()))
    scored: list[tuple[str, float, float, float]] = []  # id, predicted, actual, err%

    for row in rows:
        if not row.get("median_price", "").strip():
            continue  # not called in yet
        actual = float(row["median_price"])
        scope = Scope(
            linear_feet=float(row["linear_feet"]),
            material=row["material"].strip().lower(),
            damage_severity=int(row["damage_severity"]),
            gate_count=int(row["gate_count"]),
            zip_code=row["zip_code"].strip(),
            visibility_gaps=[],
        )
        predicted = price(scope).expected_cost
        err = abs(predicted - actual) / actual * 100
        scored.append((row["job_id"], predicted, actual, err))

    if not scored:
        print("No golden-set rows have median_price yet - make the calls first")
        print(f"(see docs/contractor_call_script.md, then fill in {path.name}).")
        return 1

    print(f"{'job':5} {'predicted':>10} {'actual':>10} {'error':>8}")
    for job_id, predicted, actual, err in scored:
        print(f"{job_id:5} {predicted:>10,.0f} {actual:>10,.0f} {err:>7.1f}%")

    med = median(e for *_, e in scored)
    print(f"\nmedian absolute error over {len(scored)} jobs: {med:.1f}%")
    if med <= GATE_PCT and len(scored) >= 5:
        print(f"PASSES the Phase 0 gate (<= {GATE_PCT:.0f}% on 5+ jobs)")
        return 0
    print(
        f"Gate not passed (need <= {GATE_PCT:.0f}% on 5+ jobs) - "
        "tune app/rate_cards.py (LA_FACTOR, per-foot bands) and rerun."
    )
    return 1


if __name__ == "__main__":
    sys.exit(run())
