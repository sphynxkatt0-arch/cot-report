#!/usr/bin/env python3
"""Single source of truth for governed COT markets and contract selection.

Every market in this registry flows through the same release-aligned structural,
tactical, macro-sizing, price-execution, UX, and validation pipeline. Financial
indices use Traders in Financial Futures (TFF) plus Legacy futures-only data.
Gold uses Disaggregated plus Legacy futures-only data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

EQUITY_PARTICIPANTS: tuple[dict[str, str], ...] = (
    {
        "key": "legacy_noncommercial",
        "label": "Legacy Non-commercial",
        "source": "legacy",
        "net": "noncommercial_net",
        "long": "noncommercial_long",
        "short": "noncommercial_short",
        "net_oi_pct": "noncommercial_net_oi_pct",
    },
    {
        "key": "asset_manager",
        "label": "Asset Manager",
        "source": "secondary",
        "net": "asset_mgr_net",
        "long": "asset_mgr_long",
        "short": "asset_mgr_short",
        "net_oi_pct": "asset_mgr_net_oi_pct",
    },
    {
        "key": "leveraged_money",
        "label": "Leveraged Money",
        "source": "secondary",
        "net": "lev_money_net",
        "long": "lev_money_long",
        "short": "lev_money_short",
        "net_oi_pct": "lev_money_net_oi_pct",
    },
    {
        "key": "other_reportables",
        "label": "Other Reportables",
        "source": "secondary",
        "net": "other_reportable_net",
        "long": "other_reportable_long",
        "short": "other_reportable_short",
        "net_oi_pct": "other_reportable_net_oi_pct",
    },
    {
        "key": "nonreportables",
        "label": "Retail proxy (Nonreportables)",
        "source": "secondary",
        "net": "non_reportable_net",
        "long": "non_reportable_long",
        "short": "non_reportable_short",
        "net_oi_pct": "non_reportable_net_oi_pct",
    },
)

GOLD_PARTICIPANTS: tuple[dict[str, str], ...] = (
    {
        "key": "legacy_noncommercial",
        "label": "Legacy Non-commercial",
        "source": "legacy",
        "net": "noncommercial_net",
        "long": "noncommercial_long",
        "short": "noncommercial_short",
        "net_oi_pct": "noncommercial_net_oi_pct",
    },
    {
        "key": "managed_money",
        "label": "Managed Money",
        "source": "secondary",
        "net": "managed_money_net",
        "long": "managed_money_long",
        "short": "managed_money_short",
        "net_oi_pct": "managed_money_net_oi_pct",
    },
    {
        "key": "swap_dealer",
        "label": "Swap Dealer",
        "source": "secondary",
        "net": "swap_dealer_net",
        "long": "swap_dealer_long",
        "short": "swap_dealer_short",
        "net_oi_pct": "swap_dealer_net_oi_pct",
    },
    {
        "key": "producer_merchant",
        "label": "Producer/Merchant",
        "source": "secondary",
        "net": "producer_merchant_net",
        "long": "producer_merchant_long",
        "short": "producer_merchant_short",
        "net_oi_pct": "producer_merchant_net_oi_pct",
    },
    {
        "key": "other_reportables",
        "label": "Other Reportables",
        "source": "secondary",
        "net": "other_reportable_net",
        "long": "other_reportable_long",
        "short": "other_reportable_short",
        "net_oi_pct": "other_reportable_net_oi_pct",
    },
    {
        "key": "nonreportables",
        "label": "Nonreportables",
        "source": "secondary",
        "net": "non_reportable_net",
        "long": "non_reportable_long",
        "short": "non_reportable_short",
        "net_oi_pct": "non_reportable_net_oi_pct",
    },
)


def _equity(
    *,
    label: str,
    cftc_code: str,
    contract_name: str,
    price_col: str,
    price_symbol: str,
    contract_multiplier: float,
    contract_unit: str,
    model_slot: str,
    invalidation_pct: float,
    confidence_base: float,
    selection_mode: str = "consolidated_exact",
    selection_note: str = "Exact CFTC consolidated parent row; component, E-mini, Micro, dividend, and TR rows are excluded.",
) -> dict[str, Any]:
    key = {
        "S&P 500": "sp500",
        "NASDAQ-100": "nq",
        "Russell 2000": "russell2000",
        "Dow Jones": "dow",
    }[label]
    return {
        "key": key,
        "label": label,
        "asset_class": "equity_index",
        "secondary_kind": "tff",
        "secondary_label": "TFF",
        "legacy_glob": f"cot_legacy_output/{key}_legacy_data_*.csv",
        "secondary_glob": f"cot_exact_output/{key}_exact_consolidated_data_*.csv",
        "price_path": PROJECT / "data" / f"{price_col}.csv",
        "price_col": price_col,
        "price_symbol": price_symbol,
        "legacy_cftc_code": cftc_code,
        "legacy_contract_name": contract_name,
        "secondary_cftc_code": cftc_code,
        "secondary_contract_name": contract_name,
        "contract_multiplier": contract_multiplier,
        "contract_unit": contract_unit,
        "contract_selection_mode": selection_mode,
        "contract_selection_note": selection_note,
        "conviction_group_label": "Asset Manager",
        "conviction_column": "asset_mgr_net_oi_pct",
        "other_reportable_column": "other_reportable_net_oi_pct",
        "nonreportable_column": "non_reportable_net_oi_pct",
        "model_slot": model_slot,
        "invalidation_pct": invalidation_pct,
        "confidence_base": confidence_base,
        "participant_specs": EQUITY_PARTICIPANTS,
    }


MARKETS: dict[str, dict[str, Any]] = {
    "sp500": _equity(
        label="S&P 500",
        cftc_code="13874+",
        contract_name="S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        price_col="SP500",
        price_symbol="^GSPC",
        contract_multiplier=50.0,
        contract_unit="S&P 500 Index x $50",
        model_slot="sp500",
        invalidation_pct=3.0,
        confidence_base=0.65,
    ),
    "nq": _equity(
        label="NASDAQ-100",
        cftc_code="20974+",
        contract_name="NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
        price_col="NASDAQ100",
        price_symbol="^NDX",
        contract_multiplier=20.0,
        contract_unit="NASDAQ-100 Index x $20",
        model_slot="nq",
        invalidation_pct=4.0,
        confidence_base=0.80,
    ),
    "russell2000": _equity(
        label="Russell 2000",
        cftc_code="239742",
        contract_name="RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE",
        price_col="RUSSELL2000",
        price_symbol="^RUT",
        contract_multiplier=50.0,
        contract_unit="Russell 2000 Index x $50",
        model_slot="nq",
        invalidation_pct=3.0,
        confidence_base=0.70,
        selection_mode="primary_contract_exact",
        selection_note=(
            "CFTC does not publish a Russell 2000 consolidated parent row in the financial futures-only file. "
            "The exact primary E-mini row 239742 is used; Micro, annual-dividend, and Russell 1000 rows are excluded."
        ),
    ),
    "dow": _equity(
        label="Dow Jones",
        cftc_code="12460+",
        contract_name="DJIA Consolidated - CHICAGO BOARD OF TRADE",
        price_col="DJIA",
        price_symbol="^DJI",
        contract_multiplier=5.0,
        contract_unit="DJIA Index x $5 representative notional",
        model_slot="sp500",
        invalidation_pct=3.0,
        confidence_base=0.65,
    ),
    "gold": {
        "key": "gold",
        "label": "Gold",
        "asset_class": "commodity",
        "secondary_kind": "disaggregated",
        "secondary_label": "Disaggregated",
        "legacy_glob": "cot_legacy_output/gold_legacy_data_*.csv",
        "secondary_glob": "cot_disaggregated_output/gold_disaggregated_data_*.csv",
        "price_path": PROJECT / "data" / "GOLD.csv",
        "price_col": "GOLD",
        "price_symbol": "GC=F",
        "legacy_cftc_code": "088691",
        "legacy_contract_name": "GOLD - COMMODITY EXCHANGE INC.",
        "secondary_cftc_code": "088691",
        "secondary_contract_name": "GOLD - COMMODITY EXCHANGE INC.",
        "contract_multiplier": 100.0,
        "contract_unit": "100 troy ounces",
        "contract_selection_mode": "primary_contract_exact",
        "contract_selection_note": "Exact COMEX Gold futures-only row 088691; Micro Gold and other metals are excluded.",
        "conviction_group_label": "Managed Money",
        "conviction_column": "managed_money_net_oi_pct",
        "other_reportable_column": "other_reportable_net_oi_pct",
        "nonreportable_column": "non_reportable_net_oi_pct",
        "model_slot": "sp500",
        "invalidation_pct": 3.0,
        "confidence_base": 0.65,
        "participant_specs": GOLD_PARTICIPANTS,
    },
}

DIRECTIONAL_MARKETS: tuple[str, ...] = tuple(MARKETS)
BASELINE_MARKETS: tuple[str, ...] = ("sp500", "nq")


def market_config(market: str) -> dict[str, Any]:
    try:
        return MARKETS[market]
    except KeyError as exc:
        raise KeyError(f"Unknown COT market {market!r}; expected one of {list(MARKETS)}") from exc


def expected_contract(market: str, report_kind: str) -> str:
    meta = market_config(market)
    if report_kind == "legacy":
        return str(meta["legacy_contract_name"])
    if report_kind == str(meta["secondary_kind"]):
        return str(meta["secondary_contract_name"])
    raise KeyError(f"{market}: unsupported report kind {report_kind!r}")
