#!/usr/bin/env python3
"""Lookahead-safe NQ actor change-magnitude / cumulative-weekday research.

Primary question:
Given the previous week's Tuesday COT snapshot, published Friday, does an unusually
large change by TFF Asset Manager / Institutional or Legacy Non-Commercial predict
the cumulative NQ path of the following exact Monday-Friday sessions?

Governance:
- universe starts from the 502 scored NQ COT states used by the existing research;
- exact weekdays only; holidays are missing rather than relabeled;
- actor level and change-magnitude percentiles are expanding-history transforms;
- fixed magnitude threshold grid: 60/65/70/75/80/85/90;
- threshold discovery uses pre-2022 only; 2022+ is untouched confirmation;
- one threshold per actor/direction applies to the entire Mon-Friday path;
- selection prefers the lowest stable threshold, never the highest-return cutoff;
- no production model parameters are changed.
"""
from __future__ import annotations

import json
import math
import statistics
from bisect import bisect_left
from datetime import date
from pathlib import Path
from typing import Any, Callable

import backtest_nq_cumulative_weekday_history as cumulative
import build_worldclass_backtest as backtest
import diagnose_nq_daily_release_path as weekday_diag
import evaluate_analog_robustness as robustness

OUT = Path(__file__).resolve().with_name("nq_actor_change_thresholds.json")
HOLDOUT_START = date(2022, 1, 1)
THRESHOLDS = (60, 65, 70, 75, 80, 85, 90)
WEEKDAYS = tuple(weekday_diag.WEEKDAYS.keys())
ACTORS = {
    "asset_manager": {
        "dataset": "tff",
        "field": "asset_mgr_net_oi_pct",
        "label": "Asset Manager / Institutional",
    },
    "noncommercial": {
        "dataset": "legacy",
        "field": "noncommercial_net_oi_pct",
        "label": "Legacy Non-Commercial",
    },
}


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def percentile_rank(values: list[float], current: float) -> float | None:
    clean = sorted(value for value in values if math.isfinite(value))
    if not clean:
        return None
    left = bisect_left(clean, current)
    equal = sum(1 for value in clean if value == current)
    return (left + max(equal, 1) / 2.0) / len(clean) * 100.0


def magnitude_bucket(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    if percentile < 50:
        return "SMALL"
    if percentile < 75:
        return "MEDIUM"
    if percentile < 90:
        return "LARGE"
    return "EXTREME"


def direction(delta: float | None) -> str:
    if delta is None or abs(delta) < 1e-12:
        return "FLAT"
    return "ADD" if delta > 0 else "CUT"


def summarize(values: list[float], baseline_values: list[float]) -> dict[str, Any]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    baseline = [float(value) for value in baseline_values if math.isfinite(float(value))]
    if not clean:
        return {"n": 0}
    mean = statistics.mean(clean)
    baseline_mean = statistics.mean(baseline) if baseline else None
    return {
        "n": len(clean),
        "mean_return_pct": round(mean, 4),
        "median_return_pct": round(statistics.median(clean), 4),
        "positive_rate_pct": round(sum(value > 0 for value in clean) / len(clean) * 100.0, 2),
        "q25_return_pct": round(backtest.quantile(clean, 0.25), 4),
        "q75_return_pct": round(backtest.quantile(clean, 0.75), 4),
        "stddev_pct": round(statistics.pstdev(clean), 4) if len(clean) > 1 else 0.0,
        "baseline_return_pct": round(baseline_mean, 4) if baseline_mean is not None else None,
        "edge_vs_baseline_pct": round(mean - baseline_mean, 4) if baseline_mean is not None else None,
    }


def segment_filter(segment: str) -> Callable[[dict[str, Any]], bool]:
    if segment == "train_pre_2022":
        return lambda row: row["report_date"] < HOLDOUT_START
    if segment == "holdout_2022_plus":
        return lambda row: row["report_date"] >= HOLDOUT_START
    return lambda row: True


def period_filter(start: date | None, end: date | None) -> Callable[[dict[str, Any]], bool]:
    def predicate(row: dict[str, Any]) -> bool:
        current = row["report_date"]
        return (start is None or current >= start) and (end is None or current <= end)
    return predicate


def path_metrics(
    rows: list[dict[str, Any]],
    condition: Callable[[dict[str, Any]], bool],
    scope: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    scoped = [row for row in rows if scope(row)]
    selected = [row for row in scoped if condition(row)]
    output: dict[str, Any] = {}
    for weekday in WEEKDAYS:
        values = [row["cumulative"][weekday] for row in selected if weekday in row["cumulative"]]
        baseline = [row["cumulative"][weekday] for row in scoped if weekday in row["cumulative"]]
        output[weekday] = summarize(values, baseline)
    return output


def build_universe(cot_data: dict[str, Any], prices: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    tff_payload = ((cot_data.get("tff") or {}).get("nq"))
    price_payload = prices.get("nq")
    if not isinstance(tff_payload, dict) or price_payload is None:
        raise RuntimeError("Missing NQ TFF or price data")
    states = weekday_diag.build_states("nq", "tff", tff_payload, price_payload)
    if len(states) != 502:
        raise RuntimeError(f"Expected 502 scored NQ states for this frozen study, got {len(states)}")
    universe: list[dict[str, Any]] = []
    by_date: dict[str, dict[str, Any]] = {}
    for state in states:
        report_date = parse_date(state["report_date"])
        if report_date is None:
            continue
        path = cumulative.cumulative_path(state["outcomes"])
        row = {
            "report_date": report_date,
            "report_date_str": state["report_date"],
            "release_date": state["release_date"],
            "cumulative": path,
            "exact_sessions": state["outcomes"],
        }
        universe.append(row)
        by_date[state["report_date"]] = row
    return universe, by_date


def actor_records(
    payload: dict[str, Any],
    actor_field: str,
    universe_by_date: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [row for row in (payload.get("records") or []) if isinstance(row, dict) and parse_date(row.get("date"))]
    rows.sort(key=lambda row: str(row.get("date")))
    level_history: list[float] = []
    magnitude_history: list[float] = []
    previous: float | None = None
    output: list[dict[str, Any]] = []

    for source in rows:
        report_date = parse_date(source.get("date"))
        current = finite(source.get(actor_field))
        if report_date is None or current is None:
            previous = current if current is not None else previous
            continue

        level_history.append(current)
        level_pct = percentile_rank(level_history, current)
        delta = current - previous if previous is not None else None
        mag_pct = None
        if delta is not None:
            magnitude_history.append(abs(delta))
            mag_pct = percentile_rank(magnitude_history, abs(delta))
        previous = current

        universe = universe_by_date.get(report_date.isoformat())
        if universe is None:
            continue
        output.append({
            "report_date": report_date,
            "report_date_str": report_date.isoformat(),
            "release_date": universe["release_date"],
            "net_oi_pct": current,
            "level_percentile": level_pct,
            "delta_net_oi_pp": delta,
            "direction": direction(delta),
            "magnitude_percentile": mag_pct,
            "magnitude_bucket": magnitude_bucket(mag_pct),
            "cumulative": universe["cumulative"],
            "exact_sessions": universe["exact_sessions"],
        })
    return output


def threshold_condition(signal_direction: str, threshold: int) -> Callable[[dict[str, Any]], bool]:
    return lambda row: (
        row["direction"] == signal_direction
        and row["magnitude_percentile"] is not None
        and row["magnitude_percentile"] >= threshold
    )


def bucket_condition(signal_direction: str, bucket: str) -> Callable[[dict[str, Any]], bool]:
    return lambda row: row["direction"] == signal_direction and row["magnitude_bucket"] == bucket


def sign(value: float | None) -> int:
    if value is None or abs(value) < 1e-12:
        return 0
    return 1 if value > 0 else -1


def discovery_selection(grid: dict[str, Any]) -> dict[str, Any]:
    """Choose the lowest stable threshold from training data only.

    Precommitted rule:
    - Friday train N >= 20;
    - absolute Friday edge >= 0.15 percentage points;
    - next-higher threshold exists, N >= 15, same edge sign, abs edge >= 0.10 pp.

    The lowest qualifying threshold is selected to favor sample breadth. Holdout
    data is not referenced anywhere in this selection function.
    """
    for index, threshold in enumerate(THRESHOLDS[:-1]):
        next_threshold = THRESHOLDS[index + 1]
        current = grid[str(threshold)]["train_pre_2022"]["friday"]
        neighbor = grid[str(next_threshold)]["train_pre_2022"]["friday"]
        current_edge = current.get("edge_vs_baseline_pct")
        neighbor_edge = neighbor.get("edge_vs_baseline_pct")
        if (
            int(current.get("n") or 0) >= 20
            and int(neighbor.get("n") or 0) >= 15
            and current_edge is not None
            and neighbor_edge is not None
            and abs(float(current_edge)) >= 0.15
            and abs(float(neighbor_edge)) >= 0.10
            and sign(float(current_edge)) == sign(float(neighbor_edge)) != 0
        ):
            return {
                "selected_threshold": threshold,
                "selection_reason": "lowest pre-2022 threshold with >=20 observations, >=0.15pp Friday edge, and same-sign next-threshold confirmation",
                "train_friday": current,
                "neighbor_threshold": next_threshold,
                "neighbor_train_friday": neighbor,
            }
    return {
        "selected_threshold": None,
        "selection_reason": "no pre-2022 threshold satisfied the fixed stability rule",
    }


def validate_holdout(selection: dict[str, Any], grid: dict[str, Any]) -> dict[str, Any]:
    threshold = selection.get("selected_threshold")
    if threshold is None:
        return {"classification": "NO_STABLE_DISCOVERY_THRESHOLD"}
    train = grid[str(threshold)]["train_pre_2022"]
    holdout = grid[str(threshold)]["holdout_2022_plus"]
    train_friday_edge = train["friday"].get("edge_vs_baseline_pct")
    holdout_friday_edge = holdout["friday"].get("edge_vs_baseline_pct")
    train_sign = sign(float(train_friday_edge)) if train_friday_edge is not None else 0
    same_sign_horizons = 0
    tested_horizons = 0
    for weekday in WEEKDAYS:
        edge = holdout[weekday].get("edge_vs_baseline_pct")
        if edge is None:
            continue
        tested_horizons += 1
        if sign(float(edge)) == train_sign and train_sign != 0:
            same_sign_horizons += 1
    holdout_n = int(holdout["friday"].get("n") or 0)
    supported = (
        holdout_n >= 12
        and holdout_friday_edge is not None
        and sign(float(holdout_friday_edge)) == train_sign != 0
        and abs(float(holdout_friday_edge)) >= 0.10
        and same_sign_horizons >= 3
    )
    return {
        "classification": "OOS_SUPPORTED" if supported else "FAILED_HOLDOUT",
        "holdout_friday": holdout["friday"],
        "same_sign_cumulative_horizons": same_sign_horizons,
        "tested_cumulative_horizons": tested_horizons,
        "rule": "2022+ Friday N>=12, same sign as discovery, abs Friday edge>=0.10pp, and >=3/5 cumulative horizons same sign",
    }


def selected_era_stability(rows: list[dict[str, Any]], signal_direction: str, threshold: int | None) -> dict[str, Any]:
    if threshold is None:
        return {}
    condition = threshold_condition(signal_direction, threshold)
    eras = {
        "2016_2019": (date(2016, 1, 1), date(2019, 12, 31)),
        "2020_2022": (date(2020, 1, 1), date(2022, 12, 31)),
        "2023_plus": (date(2023, 1, 1), None),
    }
    return {
        label: path_metrics(rows, condition, period_filter(start, end))
        for label, (start, end) in eras.items()
    }


def actor_study(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "coverage": {
            "records_on_502_state_universe": len(rows),
            "records_with_change": sum(row["delta_net_oi_pp"] is not None for row in rows),
            "records_with_complete_mon_fri_path": sum(len(row["cumulative"]) == len(WEEKDAYS) for row in rows),
        },
        "dose_response": {},
        "threshold_grid": {},
        "selected": {},
    }
    for signal_direction in ("ADD", "CUT"):
        result["dose_response"][signal_direction] = {}
        for bucket in ("SMALL", "MEDIUM", "LARGE", "EXTREME"):
            result["dose_response"][signal_direction][bucket] = {
                segment: path_metrics(rows, bucket_condition(signal_direction, bucket), segment_filter(segment))
                for segment in ("full_history", "train_pre_2022", "holdout_2022_plus")
            }

        grid: dict[str, Any] = {}
        for threshold in THRESHOLDS:
            condition = threshold_condition(signal_direction, threshold)
            grid[str(threshold)] = {
                segment: path_metrics(rows, condition, segment_filter(segment))
                for segment in ("full_history", "train_pre_2022", "holdout_2022_plus")
            }
        result["threshold_grid"][signal_direction] = grid
        selection = discovery_selection(grid)
        validation = validate_holdout(selection, grid)
        selected_threshold = selection.get("selected_threshold")
        result["selected"][signal_direction] = {
            **selection,
            "holdout_validation": validation,
            "full_history": grid[str(selected_threshold)]["full_history"] if selected_threshold is not None else None,
            "era_stability": selected_era_stability(rows, signal_direction, selected_threshold),
        }
    return result


def event(row: dict[str, Any] | None, signal_direction: str, threshold: int | None) -> bool:
    return bool(
        row is not None
        and threshold is not None
        and row["direction"] == signal_direction
        and row["magnitude_percentile"] is not None
        and row["magnitude_percentile"] >= threshold
    )


def cross_actor_study(
    asset_rows: list[dict[str, Any]],
    noncommercial_rows: list[dict[str, Any]],
    asset_selected: dict[str, Any],
    noncommercial_selected: dict[str, Any],
) -> dict[str, Any]:
    am = {row["report_date_str"]: row for row in asset_rows}
    nc = {row["report_date_str"]: row for row in noncommercial_rows}
    common_dates = sorted(set(am) & set(nc))
    merged = []
    for report_date in common_dates:
        a = am[report_date]
        n = nc[report_date]
        merged.append({
            "report_date": a["report_date"],
            "report_date_str": report_date,
            "cumulative": a["cumulative"],
            "asset": a,
            "noncommercial": n,
        })

    am_add = asset_selected["ADD"].get("selected_threshold")
    am_cut = asset_selected["CUT"].get("selected_threshold")
    nc_add = noncommercial_selected["ADD"].get("selected_threshold")
    nc_cut = noncommercial_selected["CUT"].get("selected_threshold")

    conditions = {
        "both_add": lambda row: event(row["asset"], "ADD", am_add) and event(row["noncommercial"], "ADD", nc_add),
        "both_cut": lambda row: event(row["asset"], "CUT", am_cut) and event(row["noncommercial"], "CUT", nc_cut),
        "asset_add_noncommercial_cut": lambda row: event(row["asset"], "ADD", am_add) and event(row["noncommercial"], "CUT", nc_cut),
        "asset_cut_noncommercial_add": lambda row: event(row["asset"], "CUT", am_cut) and event(row["noncommercial"], "ADD", nc_add),
    }
    return {
        "common_actor_dates": len(common_dates),
        "thresholds": {
            "asset_manager_add": am_add,
            "asset_manager_cut": am_cut,
            "noncommercial_add": nc_add,
            "noncommercial_cut": nc_cut,
        },
        "states": {
            label: {
                segment: path_metrics(merged, condition, segment_filter(segment))
                for segment in ("full_history", "train_pre_2022", "holdout_2022_plus")
            }
            for label, condition in conditions.items()
        },
    }


def main() -> None:
    cot_data, prices = robustness.build_full_inputs()
    universe, universe_by_date = build_universe(cot_data, prices)

    actor_rows: dict[str, list[dict[str, Any]]] = {}
    studies: dict[str, Any] = {}
    for actor_key, spec in ACTORS.items():
        payload = ((cot_data.get(spec["dataset"]) or {}).get("nq"))
        if not isinstance(payload, dict):
            raise RuntimeError(f"Missing NQ/{spec['dataset']} payload for {actor_key}")
        rows = actor_records(payload, spec["field"], universe_by_date)
        actor_rows[actor_key] = rows
        studies[actor_key] = {
            "label": spec["label"],
            "dataset": spec["dataset"],
            "field": spec["field"],
            **actor_study(rows),
        }

    common_dates = set(row["report_date_str"] for row in actor_rows["asset_manager"]) & set(
        row["report_date_str"] for row in actor_rows["noncommercial"]
    )
    output = {
        "schema_version": 1,
        "study": "NQ actor weekly change magnitude vs following cumulative weekday path",
        "information_contract": {
            "snapshot": "Tuesday COT positions",
            "public_availability": "Friday, modeled as report date + 3 calendar days",
            "target": "next exact Monday-Friday cumulative path beginning with Friday-close->Monday-close session",
            "holiday_rule": "missing exact weekday breaks cumulative chain; no weekday relabeling",
            "normalization": "expanding historical percentile of net/OI level and absolute one-report net/OI change",
            "lookahead_safe": True,
        },
        "governance": {
            "threshold_grid": list(THRESHOLDS),
            "discovery": "report dates before 2022-01-01",
            "confirmation": "report dates on/after 2022-01-01",
            "selection": "lowest stable discovery threshold; holdout never used to select threshold",
            "production_changes": False,
        },
        "coverage": {
            "scored_nq_state_universe": len(universe),
            "asset_manager_records_on_universe": len(actor_rows["asset_manager"]),
            "noncommercial_records_on_universe": len(actor_rows["noncommercial"]),
            "common_actor_report_dates": len(common_dates),
            "universe_complete_mon_fri_paths": sum(len(row["cumulative"]) == len(WEEKDAYS) for row in universe),
        },
        "actors": studies,
        "cross_actor": cross_actor_study(
            actor_rows["asset_manager"],
            actor_rows["noncommercial"],
            studies["asset_manager"]["selected"],
            studies["noncommercial"]["selected"],
        ),
    }
    OUT.write_text(json.dumps(output, indent=2, default=str, sort_keys=True) + "\n", encoding="utf-8")

    print("NQ ACTOR CHANGE THRESHOLD STUDY BEGIN")
    print(
        "coverage universe={u} asset={a} noncommercial={n} common={c} complete5={f}".format(
            u=output["coverage"]["scored_nq_state_universe"],
            a=output["coverage"]["asset_manager_records_on_universe"],
            n=output["coverage"]["noncommercial_records_on_universe"],
            c=output["coverage"]["common_actor_report_dates"],
            f=output["coverage"]["universe_complete_mon_fri_paths"],
        )
    )
    for actor_key in ("asset_manager", "noncommercial"):
        study = studies[actor_key]
        print(f"\n{study['label'].upper()} ({study['dataset']})")
        for signal_direction in ("ADD", "CUT"):
            print(f"  {signal_direction} THRESHOLD GRID -- Friday cumulative edge")
            print("  T   | train N | train edge | holdout N | holdout edge")
            grid = study["threshold_grid"][signal_direction]
            for threshold in THRESHOLDS:
                train = grid[str(threshold)]["train_pre_2022"]["friday"]
                hold = grid[str(threshold)]["holdout_2022_plus"]["friday"]
                te = train.get("edge_vs_baseline_pct")
                he = hold.get("edge_vs_baseline_pct")
                print(
                    f"  {threshold:3d} | {int(train.get('n') or 0):7d} | "
                    f"{te if te is not None else float('nan'):+10.4f}% | "
                    f"{int(hold.get('n') or 0):9d} | {he if he is not None else float('nan'):+12.4f}%"
                )
            selected = study["selected"][signal_direction]
            validation = selected["holdout_validation"]
            print(
                f"  SELECTED={selected.get('selected_threshold')} "
                f"OOS={validation.get('classification')}"
            )
            if selected.get("selected_threshold") is not None:
                threshold = selected["selected_threshold"]
                hold = grid[str(threshold)]["holdout_2022_plus"]
                print("  HOLDOUT CUMULATIVE EDGE Mon->Fri:")
                print("    " + " | ".join(
                    f"{day[:3].upper()} {hold[day].get('edge_vs_baseline_pct', float('nan')):+.4f}% n={hold[day].get('n', 0)}"
                    for day in WEEKDAYS
                ))
        print("  FULL-HISTORY DOSE RESPONSE -- Friday cumulative edge")
        for signal_direction in ("ADD", "CUT"):
            cells = []
            for bucket in ("SMALL", "MEDIUM", "LARGE", "EXTREME"):
                row = study["dose_response"][signal_direction][bucket]["full_history"]["friday"]
                edge = row.get("edge_vs_baseline_pct")
                cells.append(f"{bucket} {edge if edge is not None else float('nan'):+.4f}% n={row.get('n', 0)}")
            print(f"    {signal_direction}: " + " | ".join(cells))

    print("\nCROSS-ACTOR HOLDOUT -- Friday cumulative edge")
    for label, segments in output["cross_actor"]["states"].items():
        row = segments["holdout_2022_plus"]["friday"]
        edge = row.get("edge_vs_baseline_pct")
        print(f"  {label:34s} n={row.get('n', 0):3d} edge={edge if edge is not None else float('nan'):+.4f}%")
    print("NQ ACTOR CHANGE THRESHOLD STUDY END")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
