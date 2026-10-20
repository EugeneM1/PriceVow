"""Backtest script tests, run against temporary golden-set CSVs."""

import csv
from pathlib import Path

from scripts.backtest import run

HEADER = [
    "job_id", "description", "material", "linear_feet", "damage_severity",
    "gate_count", "zip_code", "contractor_1_price", "contractor_2_price",
    "contractor_3_price", "median_price", "notes",
]


def write_golden(path: Path, rows: list[dict]) -> Path:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADER)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in HEADER})
    return path


def golden_row(job_id: str, median_price, feet=18, severity=3) -> dict:
    return dict(
        job_id=job_id, description="t", material="cedar", linear_feet=feet,
        damage_severity=severity, gate_count=0, zip_code="90024",
        median_price=median_price,
    )


def test_empty_golden_set_asks_for_calls(tmp_path, capsys):
    path = write_golden(tmp_path / "g.csv", [golden_row("G01", "")])
    assert run(path) == 1
    assert "make the calls first" in capsys.readouterr().out


def test_accurate_medians_pass_the_gate(tmp_path, capsys):
    from app.pricing import price
    from app.scope import Scope

    rows = []
    for i in range(5):
        feet = 12 + 4 * i
        predicted = price(Scope(
            linear_feet=feet, material="cedar", damage_severity=3,
            gate_count=0, zip_code="90024", visibility_gaps=[],
        )).expected_cost
        # Contractors come in 5% above our prediction - within the gate.
        rows.append(golden_row(f"G{i:02d}", round(predicted * 1.05), feet=feet))
    path = write_golden(tmp_path / "g.csv", rows)
    assert run(path) == 0
    assert "PASSES the Phase 0 gate" in capsys.readouterr().out


def test_way_off_medians_fail_the_gate(tmp_path, capsys):
    rows = [golden_row(f"G{i:02d}", 99999, feet=12 + i) for i in range(5)]
    path = write_golden(tmp_path / "g.csv", rows)
    assert run(path) == 1
    assert "Gate not passed" in capsys.readouterr().out
