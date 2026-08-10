#!/usr/bin/env python3
"""Historical cumulative next-week NQ returns for every scored COT state.

This is a realized-history study, not a current forecast. For each scored COT
state, the Tuesday snapshot is assumed public Friday. The next week's exact
calendar weekday session returns are chained as:

  Monday    = prior trading close -> Monday close
  Tuesday   = Monday close -> Tuesday close
  Wednesday = Tuesday close -> Wednesday close
  Thursday  = Wednesday close -> Thursday close
  Friday    = Thursday close -> Friday close

Cumulative values compound those exact daily returns from Monday onward. A
holiday/missing weekday breaks the chain rather than relabeling another trading
day. Every scored COT state is retained in the audit, including states whose
future return is unavailable; this makes coverage explicit instead of silently
claiming 502 realized outcomes when the latest reports or holiday weeks cannot
supply them.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import build_worldclass_backtest as backtest
import diagnose_nq_daily_release_path as weekday_diag
import evaluate_analog_robustness as robustness

OUT = Path(__file__).resolve().with_name("nq_cumulative_weekday_history.json")
WEEKDAYS = tuple(weekday_diag.WEEKDAYS.keys())


def summarize(values):
    clean = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not clean:
        return {"observations": 0}
    return {
        "observations": len(clean),
        "mean_return_pct": round(statistics.mean(clean), 4),
        "median_return_pct": round(statistics.median(clean), 4),
        "positive_rate_pct": round(sum(v > 0 for v in clean) / len(clean) * 100.0, 2),
        "q25_return_pct": round(backtest.quantile(clean, 0.25), 4),
        "q75_return_pct": round(backtest.quantile(clean, 0.75), 4),
        "stddev_pct": round(statistics.pstdev(clean), 4) if len(clean) >= 2 else 0.0,
        "min_return_pct": round(min(clean), 4),
        "max_return_pct": round(max(clean), 4),
    }


def cumulative_path(outcomes):
    """Compound exact Mon->... weekday returns; stop at first missing weekday."""
    path = {}
    growth = 1.0
    for weekday in WEEKDAYS:
        value = outcomes.get(weekday)
        if value is None:
            break
        growth *= 1.0 + float(value) / 100.0
        path[weekday] = (growth - 1.0) * 100.0
    return path


def main():
    cot_data, prices = robustness.build_full_inputs()
    payload = ((cot_data.get("tff") or {}).get("nq"))
    price_payload = prices.get("nq")
    if not isinstance(payload, dict) or price_payload is None:
        raise RuntimeError("Missing NQ/TFF full-history inputs")

    states = weekday_diag.build_states("nq", "tff", payload, price_payload)
    per_report = []
    available = {weekday: [] for weekday in WEEKDAYS}
    complete_rows = []

    for state in states:
        path = cumulative_path(state["outcomes"])
        for weekday, value in path.items():
            available[weekday].append(value)
        complete = len(path) == len(WEEKDAYS)
        if complete:
            complete_rows.append(path)
        per_report.append({
            "report_date_tuesday": state["report_date"],
            "release_date_friday": state["release_date"],
            "score": round(state["score"], 6),
            "delta_4w": round(state["delta_4w"], 6),
            "exact_session_returns_pct": {
                weekday: round(state["outcomes"][weekday], 6)
                for weekday in WEEKDAYS
                if weekday in state["outcomes"]
            },
            "cumulative_from_monday_start_pct": {
                weekday: round(path[weekday], 6) for weekday in WEEKDAYS if weekday in path
            },
            "complete_five_weekday_path": complete,
        })

    available_summary = {weekday: summarize(values) for weekday, values in available.items()}
    same_sample_summary = {
        weekday: summarize([row[weekday] for row in complete_rows]) for weekday in WEEKDAYS
    }

    reports_with_any = sum(bool(row["cumulative_from_monday_start_pct"]) for row in per_report)
    reports_with_complete = len(complete_rows)
    reports_without_any = len(per_report) - reports_with_any

    output = {
        "study": "NQ historical cumulative weekday returns after previous-week COT release",
        "definition": {
            "cot_snapshot": "Tuesday",
            "release_assumption": "Friday = report date + 3 calendar days",
            "weekday_returns": "exact calendar weekday close-to-close returns",
            "cumulative_path": "compound Monday, then Monday+Tuesday, then +Wednesday, +Thursday, +Friday",
            "holiday_rule": "missing exact weekday breaks cumulative chain; no day is relabeled",
            "interpretation": "realized unconditional historical return path across COT report weeks; not the current-state analog forecast",
        },
        "coverage": {
            "scored_cot_states_processed": len(states),
            "reports_with_any_realized_cumulative_return": reports_with_any,
            "reports_with_complete_monday_through_friday_path": reports_with_complete,
            "reports_without_any_future_cumulative_return": reports_without_any,
        },
        "available_history_per_horizon": available_summary,
        "same_sample_complete_weeks": {
            "observations_each_horizon": reports_with_complete,
            "summary": same_sample_summary,
        },
        "per_report_audit": per_report,
    }

    OUT.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("NQ CUMULATIVE WEEKDAY HISTORY")
    print(
        f"states={len(states)} any_realized={reports_with_any} "
        f"complete_mon_fri={reports_with_complete} no_future={reports_without_any}"
    )
    print("\nMAXIMUM AVAILABLE HISTORY PER CUMULATIVE HORIZON")
    print("THROUGH     | OBS | MEAN      | MEDIAN    | POSITIVE | Q25       | Q75")
    for weekday in WEEKDAYS:
        row = available_summary[weekday]
        print(
            f"{weekday.title():11s}| {row['observations']:3d} | {row['mean_return_pct']:+8.4f}% | "
            f"{row['median_return_pct']:+8.4f}% | {row['positive_rate_pct']:7.2f}% | "
            f"{row['q25_return_pct']:+8.4f}% | {row['q75_return_pct']:+8.4f}%"
        )

    print("\nSAME-SAMPLE COMPLETE WEEKS")
    print("THROUGH     | OBS | MEAN      | MEDIAN    | POSITIVE | Q25       | Q75")
    for weekday in WEEKDAYS:
        row = same_sample_summary[weekday]
        print(
            f"{weekday.title():11s}| {row['observations']:3d} | {row['mean_return_pct']:+8.4f}% | "
            f"{row['median_return_pct']:+8.4f}% | {row['positive_rate_pct']:7.2f}% | "
            f"{row['q25_return_pct']:+8.4f}% | {row['q75_return_pct']:+8.4f}%"
        )
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
