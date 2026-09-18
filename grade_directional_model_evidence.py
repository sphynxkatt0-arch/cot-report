#!/usr/bin/env python3
"""Add explicit evidence grades and estimability to model-comparison rows."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from build_directional_cot_system import OUT_DIR, write_csv

SUMMARY = OUT_DIR / "directional_model_comparison_summary.csv"


def finite(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def truthy(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def evidence_grade(row: dict[str, Any]) -> tuple[str, str]:
    score_p = finite(row.get("score_hac_p"))
    edge_p = finite(row.get("edge_hac_p"))
    edge = finite(row.get("positive_minus_negative"))
    stability = finite(row.get("subperiod_sign_agreement_pct"))
    directional_n = int(finite(row.get("directional_n")) or 0)
    directional_return = finite(row.get("avg_directional_return"))
    path_utility = finite(row.get("path_utility"))
    score_slope = finite(row.get("score_slope_pp_per_unit"))

    score_estimable = score_p is not None and score_slope is not None
    edge_estimable = edge_p is not None and edge is not None
    reasons: list[str] = []
    if not score_estimable:
        reasons.append("continuous HAC not estimable")
    if not edge_estimable:
        reasons.append("directional edge HAC not estimable")
    if directional_n < 20:
        reasons.append(f"directional sample {directional_n}<20")
    if stability is None:
        reasons.append("subperiod stability not estimable")
    if directional_return is None or path_utility is None:
        reasons.append("path utility not estimable")

    contradiction = (
        edge_estimable
        and edge is not None
        and edge < 0
        and edge_p is not None
        and edge_p <= 0.10
    ) or (
        score_estimable
        and score_slope is not None
        and score_slope < 0
        and score_p is not None
        and score_p <= 0.10
    )
    if contradiction:
        return "Contradictory", "; ".join(reasons) if reasons else "statistically adverse sign"

    supported = (
        score_estimable
        and edge_estimable
        and score_slope is not None
        and score_slope > 0
        and score_p is not None
        and score_p <= 0.05
        and edge is not None
        and edge > 0
        and edge_p is not None
        and edge_p <= 0.05
        and stability is not None
        and stability >= 66.0
        and directional_n >= 20
        and directional_return is not None
        and directional_return > 0
        and path_utility is not None
        and path_utility > 0
    )
    if supported:
        return "Supported", "positive HAC score and edge; stable sign; positive path utility"

    tentative = (
        edge is not None
        and edge > 0
        and directional_n >= 20
        and directional_return is not None
        and directional_return > 0
        and path_utility is not None
        and path_utility > 0
        and stability is not None
        and stability >= 66.0
        and (
            (edge_p is not None and edge_p <= 0.10)
            or (score_p is not None and score_p <= 0.10 and score_slope is not None and score_slope > 0)
        )
    )
    if tentative:
        return "Tentative", "; ".join(reasons) if reasons else "positive but not fully supported"

    if not score_estimable and not edge_estimable:
        return "Not estimable", "; ".join(reasons) or "insufficient model variation"
    return "Weak/Mixed", "; ".join(reasons) if reasons else "evidence thresholds not met"


def grade_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        score_estimable = finite(row.get("score_hac_p")) is not None and finite(
            row.get("score_slope_pp_per_unit")
        ) is not None
        edge_estimable = finite(row.get("edge_hac_p")) is not None and finite(
            row.get("positive_minus_negative")
        ) is not None
        grade, reason = evidence_grade(row)
        row["score_hac_estimable"] = score_estimable
        row["edge_hac_estimable"] = edge_estimable
        row["evidence_grade"] = grade
        row["evidence_reason"] = reason
        output.append(row)
    return output


def main() -> None:
    if not SUMMARY.exists():
        raise FileNotFoundError(f"Missing {SUMMARY}")
    with SUMMARY.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError("Model-comparison summary is empty")
    write_csv(SUMMARY, grade_rows(rows))
    print(f"Added evidence grades to {SUMMARY}")


if __name__ == "__main__":
    main()
