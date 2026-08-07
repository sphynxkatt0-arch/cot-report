#!/usr/bin/env python3
"""
Build an interactive COT dashboard from the generated analysis CSVs.

Run:
  py build_interactive_cot_dashboard.py

Output:
  interactive_cot_dashboard.html
"""

from __future__ import annotations

import json
import io
import csv
import calendar as calendar_lib
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, date, datetime, timedelta
from html import unescape
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import requests
except ModuleNotFoundError:
    requests = None

try:
    from pypdf import PdfReader
except ModuleNotFoundError:
    PdfReader = None


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
OUT = ROOT / "interactive_cot_dashboard.html"
TEMPLATE_DIR = ROOT / "dashboard_template"
CONFIG_DIR = ROOT / "config"
FRED_API_KEY_FILE = CONFIG_DIR / "fred_api_key.txt"
FRTIB_SITEMAP_URL = "https://www.frtib.gov/sitemap.xml"
FRTIB_TSP_CACHE = PROJECT / "data" / "frtib_tsp_participant_allocations.csv"
TREASURY_ISSUANCE_CACHE = PROJECT / "data" / "treasury_issuance_calendar.csv"
FREDDIE_CALENDAR_CACHE_DIR = PROJECT / "data" / "agency_calendars"
OFR_SOFR_URL = "https://data.financialresearch.gov/v1/series/timeseries?mnemonic=FNYR-SOFR-A&remove_nulls=true"
OFR_EFFR_URL = "https://data.financialresearch.gov/v1/series/timeseries?mnemonic=FNYR-EFFR-A&remove_nulls=true"
FED_IORB_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx"
    "?rel=PRATES&series=c27939ee810cb2e929a920a6bd77d9f6&lastObs=&from=&to="
    "&filetype=csv&label=include&layout=seriescolumn&type=package"
)
FED_H8_BANK_TREASURY_AGENCY_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx"
    "?rel=H8&series=fce2318909bacbc8ce268096deddd180&lastObs=&from=&to="
    "&filetype=csv&label=include&layout=seriescolumn&type=package"
)
FED_H8_BANK_ASSETS_URL = FED_H8_BANK_TREASURY_AGENCY_URL
YAHOO_INDEX_PRICE_SERIES = {
    "SP500": "^GSPC",
    "NASDAQ100": "^NDX",
    "VIXCLS": "^VIX",
    "RUT": "^RUT",
    "DJIA": "^DJI",
    "GOLD": "GC=F",
}
TREASURY_XML_URL = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
TREASURY_XML_YEAR_LOOKBACK = 4
TREASURY_XML_SERIES = {
    "DGS3MO": ("daily_treasury_yield_curve", "BC_3MONTH"),
    "DGS2": ("daily_treasury_yield_curve", "BC_2YEAR"),
    "DGS10": ("daily_treasury_yield_curve", "BC_10YEAR"),
    "DGS30": ("daily_treasury_yield_curve", "BC_30YEAR"),
    "DFII5": ("daily_treasury_real_yield_curve", "TC_5YEAR"),
    "DFII10": ("daily_treasury_real_yield_curve", "TC_10YEAR"),
}
TREASURY_XML_CACHE: dict[tuple[str, int], bytes] = {}
TREASURY_AUCTIONS_API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
FREDDIE_CALENDAR_URL_TEMPLATE = "https://capitalmarkets.freddiemac.com/debt/pdf/reference_notes_calendar_{year}.pdf"
FANNIE_DEBT_SECURITIES_URL = "https://capitalmarkets.fanniemae.com/debt-securities"
FANNIE_REMITTANCE_SOURCE_URL = "https://selling-guide.fanniemae.com/sel/c3-2-03/mbs-remittance-type-and-selecting-remittance-cycle"
FREDDIE_REMITTANCE_SOURCE_URL = "https://sf.freddiemac.com/working-with-us/servicing/products-programs/investor-reporting"

FANNIE_BENCHMARK_NOTE_DATES = {
    2026: [
        "2026-01-14", "2026-02-23", "2026-03-19", "2026-03-30",
        "2026-04-01", "2026-04-22", "2026-05-06", "2026-06-04",
        "2026-06-15", "2026-07-01", "2026-07-21", "2026-08-05",
        "2026-08-31", "2026-09-02", "2026-10-01", "2026-10-21",
        "2026-11-17", "2026-12-16",
    ],
}


# =========================
# Static Dashboard Metadata
# =========================

MARKET_LABELS = {
    "sp500": "S&P 500",
    "nq": "NASDAQ-100",
    "vix": "VIX Futures",
    "rty": "Russell 2000",
    "dow": "Dow Jones",
    "gold": "Gold",
}

EXPECTED_CONTRACTS = {
    "sp500": "S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE",
    "nq": "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE",
    "vix": "VIX FUTURES - CBOE FUTURES EXCHANGE",
    "rty": "RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE",
    "dow": "DJIA Consolidated - CHICAGO BOARD OF TRADE",
    "gold": "GOLD - COMMODITY EXCHANGE INC.",
}

DATASET_LABELS = {
    "tff": "TFF Detailed",
    "legacy": "Legacy",
}

TFF_CATEGORIES = {
    "dealer": "Dealer / Intermediary",
    "asset_mgr": "Asset Manager / Institutional",
    "lev_money": "Leveraged Funds",
    "other_reportable": "Other Reportables",
    "non_reportable": "Non-reportable",
}

LEGACY_CATEGORIES = {
    "noncommercial": "Noncommercial",
    "commercial": "Commercial",
    "total_reportable": "Total Reportable",
    "nonreportable": "Nonreportable",
}

COLORS = {
    "dealer": "#4b5563",
    "asset_mgr": "#0ea5e9",
    "lev_money": "#16a34a",
    "other_reportable": "#a855f7",
    "non_reportable": "#dc2626",
    "noncommercial": "#2563eb",
    "commercial": "#16a34a",
    "total_reportable": "#8b5cf6",
    "nonreportable": "#f97316",
    "sp500_price": "#991b1b",
    "nq_price": "#111827",
    "vix_price": "#7c3aed",
    "rty_price": "#b45309",
    "dow_price": "#1d4ed8",
    "gold_price": "#d97706",
    "cnn_fear_greed": "#f59e0b",
    "cnn_vix": "#7c3aed",
    "fred_vix": "#0f766e",
    "real_yield_10y": "#38bdf8",
    "hy_oas": "#ef4444",
    "dollar_index": "#22c55e",
    "net_liquidity": "#0ea5e9",
    "bank_reserves": "#14b8a6",
    "sofr": "#2563eb",
    "effr": "#0891b2",
    "iorb": "#dc2626",
    "sofr_iorb_spread": "#f97316",
    "effr_iorb_spread": "#f59e0b",
    "bank_treasury_agency": "#64748b",
    "macro_score": "#f59e0b",
}

# Shared field layout for dataset exports.
CORE_FIELDS = ("date", "open_interest", "price")
CATEGORY_METRICS = ("long", "short", "net", "net_oi_pct", "short_oi_pct")

DATASET_CONFIGS = {
    "tff": {
        "label_suffix": "TFF detailed categories",
        "categories": TFF_CATEGORIES,
        "glob": "cot_exact_output/{market}_exact_consolidated_data_*.csv",
    },
    "legacy": {
        "label_suffix": "legacy categories",
        "categories": LEGACY_CATEGORIES,
        "glob": "cot_legacy_output/{market}_legacy_data_*.csv",
    },
}

# CFTC publishes these exact contract units in the weekly rows selected above.
# Keeping the unit here makes every notional calculation explicit and auditable.
CONTRACT_SPECS = {
    "sp500": {
        "multiplier": 50.0,
        "unit": "S&P 500 Index x $50",
        "cftc_code": "13874+",
    },
    "nq": {
        "multiplier": 20.0,
        "unit": "NASDAQ-100 Index x $20",
        "cftc_code": "20974+",
    },
    "vix": {
        "multiplier": 1000.0,
        "unit": "$1,000 x VIX Index",
        "cftc_code": "1170E1",
    },
    "rty": {
        "multiplier": 50.0,
        "unit": "Russell 2000 Index x $50",
        "cftc_code": "239742",
    },
    "dow": {
        "multiplier": 5.0,
        "unit": "DJIA x $5",
        "cftc_code": "12460+",
    },
    "gold": {
        "multiplier": 100.0,
        "unit": "100 troy oz",
        "cftc_code": "088691",
    },
}

STRUCTURAL_OFFSET_CATEGORIES = {
    # Dealer / Intermediary is mostly the offset/warehouse leg to customer flow.
    # Treating its long/short balance as standalone direction overstates signal.
    "tff": {"dealer"},
    "legacy": set(),
}

CROSS_MARKET_EXCLUDED_CATEGORIES = {
    "tff": set(STRUCTURAL_OFFSET_CATEGORIES["tff"]),
    # Total Reportable is an aggregate of reportable categories, not a separate player.
    "legacy": {"total_reportable"},
}

PRICE_SERIES = {
    "sp500": {"fred_id": "SP500", "label": "S&P 500"},
    "nq": {"fred_id": "NASDAQ100", "label": "NASDAQ-100"},
    "vix": {"fred_id": "VIXCLS", "label": "VIX"},
    "rty": {"fred_id": "RUT", "label": "Russell 2000"},
    "dow": {"fred_id": "DJIA", "label": "Dow Jones"},
    "gold": {"fred_id": "GOLD", "label": "Gold (GC Futures)"},
}

FACTOR_SERIES = {
    "cnn_fear_greed": {
        "label": "CNN Fear & Greed",
        "source": "CNN",
        "kind": "cnn_csv",
        "format": "score",
    },
    "cnn_vix": {
        "label": "CNN VIX component",
        "source": "CNN",
        "kind": "cnn_json",
        "json_key": "market_volatility_vix",
        "format": "number",
    },
    "fred_vix": {
        "label": "FRED VIX",
        "source": "FRED VIXCLS / Yahoo ^VIX fallback",
        "kind": "fred",
        "fred_id": "VIXCLS",
        "format": "number",
    },
    "real_yield_10y": {
        "label": "10Y real yield",
        "source": "FRED DFII10",
        "kind": "fred",
        "fred_id": "DFII10",
        "format": "number",
        "min_rows": 500,
    },
    "hy_oas": {
        "label": "High-yield OAS",
        "source": "FRED BAMLH0A0HYM2",
        "kind": "fred",
        "fred_id": "BAMLH0A0HYM2",
        "format": "number",
        "min_rows": 500,
    },
    "dollar_index": {
        "label": "Broad dollar index",
        "source": "FRED DTWEXBGS",
        "kind": "fred",
        "fred_id": "DTWEXBGS",
        "format": "number",
        "min_rows": 500,
    },
}

LIQUIDITY_SERIES = {
    "fed_balance_sheet": {
        "fred_id": "WALCL",
        "label": "Fed balance sheet",
        "source": "FRED WALCL",
        "unit": "USD bn",
        "scale_to_bn": 0.001,
        "polarity": "positive",
    },
    "reverse_repo": {
        "fred_id": "RRPONTSYD",
        "label": "Reverse repo",
        "source": "FRED RRPONTSYD",
        "unit": "USD bn",
        "scale_to_bn": 1.0,
        "polarity": "negative",
    },
    "treasury_cash": {
        "fred_id": "WDTGAL",
        "label": "Treasury General Account",
        "source": "FRED WDTGAL",
        "unit": "USD bn",
        "scale_to_bn": 0.001,
        "polarity": "negative",
    },
    "bank_reserves": {
        "fred_id": "WRESBAL",
        "label": "Bank reserves",
        "source": "FRED WRESBAL",
        "unit": "USD bn",
        "scale_to_bn": 0.001,
        "polarity": "positive",
    },
    "bank_treasury_agency": {
        "fred_id": "USGSEC",
        "label": "Bank Treasury/agency securities",
        "source": "Federal Reserve H.8 B1003NCBA",
        "unit": "USD bn",
        "scale_to_bn": 0.001,
        "polarity": "negative",
    },
    "bank_assets": {
        "fred_id": "BANKASSETS",
        "label": "Bank total assets",
        "source": "Federal Reserve H.8 B1058NCBA",
        "unit": "USD bn",
        "scale_to_bn": 0.001,
        "polarity": "neutral",
    },
}

FUNDING_SERIES = {
    "sofr": {
        "series_id": "SOFR",
        "label": "SOFR",
        "source": "OFR STFM FNYR-SOFR-A / NY Fed",
        "unit": "%",
        "polarity": "negative",
    },
    "effr": {
        "series_id": "EFFR",
        "label": "EFFR",
        "source": "OFR STFM FNYR-EFFR-A / NY Fed",
        "unit": "%",
        "polarity": "negative",
    },
    "iorb": {
        "series_id": "IORB",
        "label": "IORB",
        "source": "Federal Reserve DDP PRATES RESBM_N.D",
        "unit": "%",
        "polarity": "negative",
    },
}

FRED_MIN_ROWS = {
    "WALCL": 500,
    "WDTGAL": 500,
    "RRPONTSYD": 500,
    "WRESBAL": 500,
    "SOFR": 500,
    "EFFR": 500,
    "IORB": 500,
    "USGSEC": 500,
    "BANKASSETS": 500,
    "DFII10": 500,
    "BAMLH0A0HYM2": 500,
    "DTWEXBGS": 500,
    "VIXCLS": 500,
    "SP500": 500,
    "NASDAQ100": 500,
    "DFII5": 500,
    "DGS10": 500,
    "DGS2": 500,
    "DGS3MO": 500,
    "DGS30": 500,
    "BAMLC0A0CM": 500,
    "RUT": 500,
    "DJIA": 500,
    "GOLD": 500,
}

MACRO_SERIES = {
    "walcl": {
        "fred_id": "WALCL",
        "label": "Fed total assets",
        "source": "FRED WALCL",
        "frequency": "weekly",
        "unit": "USD bn",
        "scale": 0.001,
        "use": "Fed balance sheet / QE-QT impulse",
    },
    "tga": {
        "fred_id": "WDTGAL",
        "label": "Treasury General Account",
        "source": "FRED WDTGAL",
        "frequency": "weekly",
        "unit": "USD bn",
        "scale": 0.001,
        "use": "Treasury cash drain or drawdown",
    },
    "rrp": {
        "fred_id": "RRPONTSYD",
        "label": "Reverse repo",
        "source": "FRED RRPONTSYD",
        "frequency": "daily",
        "unit": "USD bn",
        "scale": 1.0,
        "use": "Money-market liquidity buffer",
    },
    "bank_reserves": {
        "fred_id": "WRESBAL",
        "label": "Bank reserves",
        "source": "FRED WRESBAL",
        "frequency": "weekly",
        "unit": "USD bn",
        "scale": 0.001,
        "use": "Banking-system liquidity",
    },
    "bank_treasury_agency": {
        "fred_id": "USGSEC",
        "label": "Bank Treasury/agency securities",
        "source": "Federal Reserve H.8 B1003NCBA",
        "frequency": "weekly",
        "unit": "USD bn",
        "scale": 0.001,
        "use": "Bank balance-sheet load tied to SLR/regulatory constraints",
    },
    "bank_assets": {
        "fred_id": "BANKASSETS",
        "label": "Bank total assets",
        "source": "Federal Reserve H.8 B1058NCBA",
        "frequency": "weekly",
        "unit": "USD bn",
        "scale": 0.001,
        "use": "Denominator for reserve abundance relative to the banking system",
    },
    "sofr": {
        "fred_id": "SOFR",
        "label": "SOFR",
        "source": "OFR STFM FNYR-SOFR-A / NY Fed",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Secured overnight repo funding rate",
        "required": False,
    },
    "effr": {
        "fred_id": "EFFR",
        "label": "EFFR",
        "source": "OFR STFM FNYR-EFFR-A / NY Fed",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Effective federal funds rate for unsecured overnight funding",
        "required": False,
    },
    "iorb": {
        "fred_id": "IORB",
        "label": "IORB",
        "source": "Federal Reserve DDP PRATES RESBM_N.D",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Administered reserve-rate floor for banks",
        "required": False,
    },
    "real_yield_10y": {
        "fred_id": "DFII10",
        "label": "10Y real yield",
        "source": "FRED DFII10 / Treasury daily real yield curve",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Discount-rate pressure on growth/NQ",
    },
    "real_yield_5y": {
        "fred_id": "DFII5",
        "label": "5Y real yield",
        "source": "FRED DFII5 / Treasury daily real yield curve",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Front/intermediate real-rate pressure on growth assets",
        "required": False,
    },
    "nominal_yield_10y": {
        "fred_id": "DGS10",
        "label": "10Y nominal yield",
        "source": "FRED DGS10 / Treasury daily par yield curve",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Nominal duration and discount-rate pressure",
        "required": False,
    },
    "nominal_yield_2y": {
        "fred_id": "DGS2",
        "label": "2Y nominal yield",
        "source": "FRED DGS2 / Treasury daily par yield curve",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Fed-policy path pressure",
        "required": False,
    },
    "nominal_yield_3m": {
        "fred_id": "DGS3MO",
        "label": "3M T-bill yield",
        "source": "FRED DGS3MO / Treasury daily par yield curve",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Front-end policy and curve pressure",
        "required": False,
    },
    "nominal_yield_30y": {
        "fred_id": "DGS30",
        "label": "30Y nominal yield",
        "source": "FRED DGS30 / Treasury daily par yield curve",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Long-end duration and term-premium pressure",
        "required": False,
    },
    "hy_oas": {
        "fred_id": "BAMLH0A0HYM2",
        "label": "High-yield OAS",
        "source": "FRED BAMLH0A0HYM2",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Credit stress / risk appetite",
    },
    "ig_oas": {
        "fred_id": "BAMLC0A0CM",
        "label": "Investment-grade OAS",
        "source": "FRED BAMLC0A0CM",
        "frequency": "daily",
        "unit": "%",
        "scale": 1.0,
        "use": "Higher-quality credit stress confirmation",
        "required": False,
    },
    "dollar_index": {
        "fred_id": "DTWEXBGS",
        "label": "Broad dollar index",
        "source": "FRED DTWEXBGS",
        "frequency": "daily",
        "unit": "index",
        "scale": 1.0,
        "use": "Global dollar liquidity pressure",
    },
    "vix": {
        "fred_id": "VIXCLS",
        "label": "VIX",
        "source": "FRED VIXCLS / Yahoo ^VIX fallback",
        "frequency": "daily",
        "unit": "index",
        "scale": 1.0,
        "use": "Volatility / deleveraging pressure",
    },
    "sp500": {
        "fred_id": "SP500",
        "label": "S&P 500",
        "source": "FRED SP500",
        "frequency": "daily",
        "unit": "index",
        "scale": 1.0,
        "use": "Market benchmark and forward-return target",
    },
    "nasdaq": {
        "fred_id": "NASDAQ100",
        "label": "Nasdaq-100",
        "source": "FRED NASDAQ100",
        "frequency": "daily",
        "unit": "index",
        "scale": 1.0,
        "use": "Growth/NQ benchmark and forward-return target",
    },
}

MACRO_SCORE_FACTORS = [
    {
        "key": "net_liquidity_impulse",
        "label": "Fed net liquidity impulse",
        "weight": 26,
        "score_col": "score_net_liquidity",
        "delta_col": "net_liquidity_4w_change",
        "unit": "usd_bn",
    },
    {
        "key": "bank_reserves",
        "label": "Bank reserves",
        "weight": 10,
        "score_col": "score_bank_reserves",
        "delta_col": "bank_reserves_4w_change",
        "unit": "usd_bn",
    },
    {
        "key": "treasury_supply",
        "label": "Treasury supply pressure",
        "weight": 10,
        "score_col": "score_treasury_supply",
        "delta_col": "treasury_issuance_next_7d",
        "unit": "usd_bn",
    },
    {
        "key": "repo_rate_stress",
        "label": "SOFR-IORB repo stress",
        "weight": 8,
        "score_col": "score_repo_spread",
        "delta_col": "sofr_iorb_spread_4w_change",
        "unit": "pp",
    },
    {
        "key": "slr_balance_sheet_load",
        "label": "SLR balance-sheet load",
        "weight": 4,
        "score_col": "score_slr_load",
        "delta_col": "slr_balance_sheet_load_4w_change",
        "unit": "usd_bn",
    },
    {
        "key": "real_yields",
        "label": "Real yields",
        "weight": 14,
        "score_col": "score_real_yield",
        "delta_col": "real_yield_4w_change",
        "unit": "pp",
    },
    {
        "key": "credit_spreads",
        "label": "Credit spreads",
        "weight": 14,
        "score_col": "score_credit",
        "delta_col": "hy_oas_4w_change",
        "unit": "pp",
    },
    {
        "key": "dollar",
        "label": "Dollar",
        "weight": 8,
        "score_col": "score_dollar",
        "delta_col": "dollar_4w_change",
        "unit": "index",
    },
    {
        "key": "vix",
        "label": "VIX",
        "weight": 6,
        "score_col": "score_vix",
        "delta_col": "vix_4w_change",
        "unit": "index",
    },
]

TSP_MACRO_COLUMNS = [
    "tsp_total_assets",
    "tsp_g_fund_assets",
    "tsp_f_fund_assets",
    "tsp_c_fund_assets",
    "tsp_s_fund_assets",
    "tsp_i_fund_assets",
    "tsp_l_fund_assets",
    "tsp_g_fund_share",
    "tsp_equity_share",
    "tsp_g_fund_1m_change",
    "tsp_equity_1m_change",
    "tsp_g_fund_ift_m",
    "tsp_f_fund_ift_m",
    "tsp_c_fund_ift_m",
    "tsp_s_fund_ift_m",
    "tsp_i_fund_ift_m",
    "tsp_l_fund_ift_m",
    "tsp_equity_ift_m",
    "retirement_flow_signal",
]

MACRO_COLUMNS = [
    "date",
    "walcl",
    "tga",
    "rrp",
    "bank_reserves",
    "bank_treasury_agency",
    "bank_assets",
    "reserves_to_bank_assets_pct",
    "slr_balance_sheet_load",
    "net_liquidity",
    "net_liquidity_4w_change",
    "net_liquidity_13w_change",
    "bank_reserves_4w_change",
    "bank_treasury_agency_4w_change",
    "slr_balance_sheet_load_4w_change",
    "reserves_to_bank_assets_4w_change",
    "tga_4w_change",
    "rrp_4w_change",
    "sofr",
    "effr",
    "iorb",
    "sofr_iorb_spread",
    "effr_iorb_spread",
    "sofr_iorb_spread_4w_change",
    "effr_iorb_spread_4w_change",
    "real_yield_10y",
    "real_yield_5y",
    "real_yield_4w_change",
    "real_yield_5y_4w_change",
    "nominal_yield_10y",
    "nominal_yield_2y",
    "nominal_yield_3m",
    "nominal_yield_30y",
    "nominal_yield_30y_4w_change",
    "yield_curve_10y_2y",
    "yield_curve_10y_3m",
    "yield_curve_30y_10y",
    "hy_oas",
    "ig_oas",
    "hy_oas_4w_change",
    "ig_oas_4w_change",
    "dollar_index",
    "dollar_4w_change",
    "vix",
    "vix_4w_change",
    "sp500",
    "nasdaq",
    "sp500_13w_change_pct",
    "sp500_forward_5d",
    "sp500_forward_10d",
    "treasury_issuance_7d",
    "treasury_issuance_28d",
    "treasury_issuance_next_7d",
    "liquidity_plumbing_score",
    "liquidity_score",
    "regime_label",
    "sp500_forward_20d",
    "sp500_forward_60d",
    "nasdaq_forward_5d",
    "nasdaq_forward_10d",
    "nasdaq_forward_20d",
    "nasdaq_forward_60d",
    *TSP_MACRO_COLUMNS,
    "credit_override",
]

FORWARD_WINDOWS = (1, 4, 13, 26, 52)
EXPECTED_RETURN_WINDOWS = (1, 4, 13, 26, 52)
RESEARCH_CATEGORIES = tuple(
    category for category in TFF_CATEGORIES
    if category not in STRUCTURAL_OFFSET_CATEGORIES["tff"]
)
RESEARCH_EXTREME_WINDOWS = (13, 26, 52)
RESEARCH_SIGNAL_LABELS = {
    "dealer": "Dealer",
    "asset_mgr": "Asset Manager",
    "lev_money": "Leveraged Money",
    "other_reportable": "Other Reportable",
    "non_reportable": "Non-reportable",
}
SENTIMENT_RETURN_HORIZONS = (
    ("1d", 1),
    ("2d", 2),
    ("3d", 3),
    ("4d", 4),
    ("5d", 5),
    ("6d", 6),
    ("7d", 7),
    ("2w", 14),
    ("3w", 21),
)

SENTIMENT_BUCKETS = (
    ("ihavetosell_0_7", "IHaveToSell 0-7"),
    ("panican_7_10", "Panican 7-10"),
    ("extreme_fear_10_25", "Extreme Fear 10-25"),
    ("fear_25_45", "Fear 25-45"),
    ("neutral_45_55", "Neutral 45-55"),
    ("greed_55_75", "Greed 55-75"),
    ("extreme_greed_75_100", "Extreme Greed >=75"),
)

# ====================
# Data Loading Helpers
# ====================

def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {path}. Run the COT analysis scripts first.")
    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise KeyError(f"{path} has no date column")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return df


def keep_existing(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    return df[[c for c in columns if c in df.columns]].copy()


def records(df: pd.DataFrame) -> list[dict]:
    return df.astype(object).where(pd.notna(df), None).to_dict(orient="records")


def require_exact_consolidated(df: pd.DataFrame, market: str, path: Path) -> None:
    if "contract" not in df.columns:
        raise KeyError(f"{path} has no contract column; cannot verify consolidated row.")
    expected = EXPECTED_CONTRACTS[market]
    contracts = sorted(str(c).strip() for c in df["contract"].dropna().unique())
    if contracts != [expected]:
        found = "; ".join(contracts[:10])
        raise ValueError(f"{path} is not exact consolidated-only. Expected {expected!r}; found {found!r}")


def latest_file(pattern: str) -> Path:
    matches = sorted(ROOT.glob(pattern), key=lambda p: p.stat().st_mtime)
    if not matches:
        raise FileNotFoundError(f"No files match {ROOT / pattern}")
    return matches[-1]


def dataset_columns(categories: dict[str, str]) -> list[str]:
    cols = list(CORE_FIELDS)
    for key in categories:
        cols.extend(f"{key}_{metric}" for metric in CATEGORY_METRICS)
    return cols


def load_market_dataset(market: str, dataset_key: str) -> dict[str, Any]:
    cfg = DATASET_CONFIGS[dataset_key]
    path = latest_file(cfg["glob"].format(market=market))
    df = read_csv(path)
    require_exact_consolidated(df, market, path)

    categories = cfg["categories"]
    return {
        "label": f"{MARKET_LABELS[market]} {cfg['label_suffix']}",
        "categories": categories,
        "records": records(keep_existing(df, dataset_columns(categories))),
    }


def load_cot_data() -> dict[str, dict[str, dict[str, Any]]]:
    payload: dict[str, dict[str, dict[str, Any]]] = {key: {} for key in DATASET_CONFIGS}
    for dataset_key in DATASET_CONFIGS:
        for market in MARKET_LABELS:
            try:
                payload[dataset_key][market] = load_market_dataset(market, dataset_key)
            except FileNotFoundError:
                # Some markets don't have all datasets (e.g. Gold is not in TFF).
                print(
                    f"INFO: No {dataset_key} data found for {market} — skipping. "
                    f"Run the relevant COT analysis script to generate it."
                )
                payload[dataset_key][market] = None  # type: ignore[assignment]
    return payload


def trailing_z_score(history: list[float], value: float, lookback: int = 156) -> float | None:
    clean = pd.Series(history[-lookback:], dtype="float64").dropna()
    if len(clean) < 26 or not pd.notna(value):
        return None
    std = float(clean.std(ddof=1))
    if not std or not pd.notna(std):
        return 0.0
    return max(-3.0, min(3.0, (float(value) - float(clean.mean())) / std))


def player_market_snapshot(
    rows: list[dict[str, Any]],
    category: str,
    report_date: str,
    market: str,
) -> dict[str, Any] | None:
    history = [row for row in rows if row.get("date") and row["date"] <= report_date]
    if not history or history[-1].get("date") != report_date:
        return None

    latest = history[-1]
    prior = history[-2] if len(history) >= 2 else None
    prior_4w = history[-5] if len(history) >= 5 else None
    price = float(latest.get("price") or 0.0)
    multiplier = float(CONTRACT_SPECS[market]["multiplier"])
    contract_notional = price * multiplier
    long_contracts = float(latest.get(f"{category}_long") or 0.0)
    short_contracts = float(latest.get(f"{category}_short") or 0.0)
    net_contracts = float(latest.get(f"{category}_net") or 0.0)
    net_oi_pct = float(latest.get(f"{category}_net_oi_pct") or 0.0)
    open_interest = float(latest.get("open_interest") or 0.0)

    prior_net = float(prior.get(f"{category}_net") or 0.0) if prior else net_contracts
    prior_4w_net = float(prior_4w.get(f"{category}_net") or 0.0) if prior_4w else net_contracts
    flow_1w_contracts = net_contracts - prior_net
    flow_4w_contracts = net_contracts - prior_4w_net

    net_oi_history: list[float] = []
    flow_1w_history: list[float] = []
    flow_4w_history: list[float] = []
    for index, row in enumerate(history[:-1]):
        value = row.get(f"{category}_net_oi_pct")
        if value is not None:
            net_oi_history.append(float(value))
        if index >= 1:
            current_net = float(row.get(f"{category}_net") or 0.0)
            previous_net = float(history[index - 1].get(f"{category}_net") or 0.0)
            oi = float(row.get("open_interest") or 0.0)
            if oi:
                flow_1w_history.append((current_net - previous_net) / oi * 100.0)
        if index >= 4:
            current_net = float(row.get(f"{category}_net") or 0.0)
            previous_net = float(history[index - 4].get(f"{category}_net") or 0.0)
            oi = float(row.get("open_interest") or 0.0)
            if oi:
                flow_4w_history.append((current_net - previous_net) / oi * 100.0)

    flow_1w_oi_pct = flow_1w_contracts / open_interest * 100.0 if open_interest else 0.0
    flow_4w_oi_pct = flow_4w_contracts / open_interest * 100.0 if open_interest else 0.0
    return {
        "market": market,
        "report_date": report_date,
        "price": price,
        "multiplier": multiplier,
        "contract_unit": CONTRACT_SPECS[market]["unit"],
        "contract_notional_usd": contract_notional,
        "open_interest": open_interest,
        "long_contracts": long_contracts,
        "short_contracts": short_contracts,
        "net_contracts": net_contracts,
        "net_oi_pct": net_oi_pct,
        "long_notional_usd": long_contracts * contract_notional,
        "short_notional_usd": short_contracts * contract_notional,
        "net_notional_usd": net_contracts * contract_notional,
        "flow_1w_contracts": flow_1w_contracts,
        "flow_4w_contracts": flow_4w_contracts,
        "flow_1w_oi_pct": flow_1w_oi_pct,
        "flow_4w_oi_pct": flow_4w_oi_pct,
        "flow_1w_notional_usd": flow_1w_contracts * contract_notional,
        "flow_4w_notional_usd": flow_4w_contracts * contract_notional,
        "position_z": trailing_z_score(net_oi_history, net_oi_pct),
        "flow_1w_z": trailing_z_score(flow_1w_history, flow_1w_oi_pct),
        "flow_4w_z": trailing_z_score(flow_4w_history, flow_4w_oi_pct),
    }


def cross_market_bias_label(score: float | None) -> str:
    if score is None:
        return "Insufficient"
    if score >= 0.50:
        return "Bullish"
    if score <= -0.50:
        return "Bearish"
    return "Mixed"


def market_flow_direction(snapshot: dict[str, Any], neutral_oi_pct: float = 0.10) -> str:
    """Classify one-week net buying/selling while suppressing immaterial changes."""
    flow_oi_pct = float(snapshot.get("flow_1w_oi_pct") or 0.0)
    if flow_oi_pct >= neutral_oi_pct:
        return "Bullish"
    if flow_oi_pct <= -neutral_oi_pct:
        return "Bearish"
    return "Neutral"


def combined_equity_flow_direction(markets: dict[str, dict[str, Any]]) -> tuple[str, float]:
    """Classify summed SP+NQ flow without overstating offsetting market legs."""
    sp_flow = float((markets.get("sp500") or {}).get("flow_1w_notional_usd") or 0.0)
    nq_flow = float((markets.get("nq") or {}).get("flow_1w_notional_usd") or 0.0)
    total = sp_flow + nq_flow
    gross = abs(sp_flow) + abs(nq_flow)
    balance_ratio = total / gross if gross else 0.0
    if gross == 0.0 or abs(balance_ratio) < 0.15:
        return "Mixed", balance_ratio
    return ("Bullish" if total > 0 else "Bearish"), balance_ratio


def combined_risk_flow_direction(markets: dict[str, dict[str, Any]]) -> tuple[str, float]:
    """Classify SP+NQ flow after counting VIX buying as defensive/risk-off."""
    sp_flow = float((markets.get("sp500") or {}).get("flow_1w_notional_usd") or 0.0)
    nq_flow = float((markets.get("nq") or {}).get("flow_1w_notional_usd") or 0.0)
    vix_flow = float((markets.get("vix") or {}).get("flow_1w_notional_usd") or 0.0)
    total = sp_flow + nq_flow - vix_flow
    gross = abs(sp_flow) + abs(nq_flow) + abs(vix_flow)
    balance_ratio = total / gross if gross else 0.0
    if gross == 0.0 or abs(balance_ratio) < 0.15:
        return "Mixed", balance_ratio
    return ("Bullish" if total > 0 else "Bearish"), balance_ratio


def signed_total_direction(value: float | None, neutral_notional_usd: float = 2_000_000_000.0) -> str:
    """Classify a signed total-risk dollar change while suppressing small noise."""
    if value is None or not pd.notna(value):
        return "Insufficient"
    if value >= neutral_notional_usd:
        return "Bullish"
    if value <= -neutral_notional_usd:
        return "Bearish"
    return "Mixed"


def vix_risk_flow_direction(snapshot: dict[str, Any], neutral_oi_pct: float = 0.10) -> str:
    """Classify VIX flow from an equity-risk perspective: VIX buying is bearish."""
    flow_oi_pct = float(snapshot.get("flow_1w_oi_pct") or 0.0)
    if flow_oi_pct >= neutral_oi_pct:
        return "Bearish"
    if flow_oi_pct <= -neutral_oi_pct:
        return "Bullish"
    return "Neutral"


def cross_market_divergence(markets: dict[str, dict[str, Any]]) -> str:
    sp = markets.get("sp500") or {}
    nq = markets.get("nq") or {}
    sp_direction = market_flow_direction(sp)
    nq_direction = market_flow_direction(nq)
    if sp_direction == "Neutral" and nq_direction == "Neutral":
        return "SP and NQ flows neutral"
    if sp_direction == "Neutral":
        return f"SP neutral / {'buying' if nq_direction == 'Bullish' else 'selling'} NQ"
    if nq_direction == "Neutral":
        return f"{'Buying' if sp_direction == 'Bullish' else 'Selling'} SP / NQ neutral"
    if sp_direction == nq_direction:
        return "Buying SP and NQ" if sp_direction == "Bullish" else "Selling SP and NQ"
    return "Buying SP / selling NQ" if sp_direction == "Bullish" else "Selling SP / buying NQ"


def player_total_risk_point(date: str, markets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build one total-risk history point using SP+NQ-VIX notionals."""
    equity_net = sum(markets[m]["net_notional_usd"] for m in ("sp500", "nq"))
    equity_flow_1w = sum(markets[m]["flow_1w_notional_usd"] for m in ("sp500", "nq"))
    equity_flow_4w = sum(markets[m]["flow_4w_notional_usd"] for m in ("sp500", "nq"))
    vix_net = markets["vix"]["net_notional_usd"]
    vix_flow_1w = markets["vix"]["flow_1w_notional_usd"]
    vix_flow_4w = markets["vix"]["flow_4w_notional_usd"]
    risk_flow_direction, risk_flow_balance_ratio = combined_risk_flow_direction(markets)
    return {
        "date": date,
        "equity_net_notional_usd": equity_net,
        "equity_flow_1w_notional_usd": equity_flow_1w,
        "equity_flow_4w_notional_usd": equity_flow_4w,
        "vix_net_notional_usd": vix_net,
        "vix_flow_1w_notional_usd": vix_flow_1w,
        "vix_flow_4w_notional_usd": vix_flow_4w,
        "vix_risk_flow_1w_notional_usd": -vix_flow_1w,
        "vix_risk_flow_4w_notional_usd": -vix_flow_4w,
        "risk_net_notional_usd": equity_net - vix_net,
        "risk_flow_1w_notional_usd": equity_flow_1w - vix_flow_1w,
        "risk_flow_4w_notional_usd": equity_flow_4w - vix_flow_4w,
        "risk_flow_1w_direction": risk_flow_direction,
        "risk_flow_1w_balance_ratio": risk_flow_balance_ratio,
    }


def build_player_total_risk_history(
    market_payloads: dict[str, Any],
    category: str,
    common_dates: set[str],
) -> list[dict[str, Any]]:
    """Build a long-term SP+NQ-VIX net-notional and flow history for one player."""
    history: list[dict[str, Any]] = []
    for report_date in sorted(common_dates):
        markets: dict[str, Any] = {}
        for market in ("sp500", "nq", "vix"):
            rows = (market_payloads.get(market) or {}).get("records") or []
            snapshot = player_market_snapshot(rows, category, report_date, market)
            if snapshot:
                markets[market] = snapshot
        if all(market in markets for market in ("sp500", "nq", "vix")):
            history.append(player_total_risk_point(report_date, markets))
    return history


def build_cross_market_positioning(data: dict[str, Any]) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for dataset_key, market_payloads in data.items():
        available_dates = []
        for market in ("sp500", "nq", "vix"):
            rows = (market_payloads.get(market) or {}).get("records") or []
            available_dates.append({row.get("date") for row in rows if row.get("date")})
        common_dates = set.intersection(*available_dates) if available_dates else set()
        if not common_dates:
            datasets[dataset_key] = {"available": False, "report_date": None, "players": []}
            continue

        sorted_common_dates = sorted(common_dates)
        report_date = sorted_common_dates[-1]
        previous_report_date = sorted_common_dates[-2] if len(sorted_common_dates) >= 2 else None
        category_labels = (market_payloads.get("sp500") or {}).get("categories") or {}
        excluded = CROSS_MARKET_EXCLUDED_CATEGORIES.get(dataset_key, set())
        players = []
        for category, label in category_labels.items():
            if category in excluded:
                continue
            markets: dict[str, Any] = {}
            for market in ("sp500", "nq", "vix"):
                rows = (market_payloads.get(market) or {}).get("records") or []
                snapshot = player_market_snapshot(rows, category, report_date, market)
                if snapshot:
                    markets[market] = snapshot
            if not all(market in markets for market in ("sp500", "nq", "vix")):
                continue

            risk_sign = {"sp500": 1.0, "nq": 1.0, "vix": -1.0}
            flow_1w_scores = [
                risk_sign[market] * float(snapshot["flow_1w_z"])
                for market, snapshot in markets.items()
                if snapshot.get("flow_1w_z") is not None
            ]
            flow_4w_scores = [
                risk_sign[market] * float(snapshot["flow_4w_z"])
                for market, snapshot in markets.items()
                if snapshot.get("flow_4w_z") is not None
            ]
            position_scores = [
                risk_sign[market] * float(snapshot["position_z"])
                for market, snapshot in markets.items()
                if snapshot.get("position_z") is not None
            ]
            flow_1w_score = sum(flow_1w_scores) / len(flow_1w_scores) if flow_1w_scores else None
            flow_4w_score = sum(flow_4w_scores) / len(flow_4w_scores) if flow_4w_scores else None
            position_score = sum(position_scores) / len(position_scores) if position_scores else None
            combined_parts = []
            if flow_1w_score is not None:
                combined_parts.append((0.60, flow_1w_score))
            if flow_4w_score is not None:
                combined_parts.append((0.40, flow_4w_score))
            combined_score = (
                sum(weight * score for weight, score in combined_parts)
                / sum(weight for weight, _ in combined_parts)
                if combined_parts
                else None
            )
            if combined_score is not None:
                combined_score = max(-3.0, min(3.0, combined_score))

            equity_flow_direction, equity_flow_balance_ratio = combined_equity_flow_direction(markets)
            risk_history = build_player_total_risk_history(market_payloads, category, common_dates)
            latest_risk = risk_history[-1] if risk_history else player_total_risk_point(report_date, markets)
            risk_net_13w_change_notional_usd = (
                latest_risk["risk_net_notional_usd"] - risk_history[-14]["risk_net_notional_usd"]
                if len(risk_history) >= 14
                else None
            )
            risk_net_26w_change_notional_usd = (
                latest_risk["risk_net_notional_usd"] - risk_history[-27]["risk_net_notional_usd"]
                if len(risk_history) >= 27
                else None
            )
            equity_net_notional_usd = latest_risk["equity_net_notional_usd"]
            equity_flow_1w_notional_usd = latest_risk["equity_flow_1w_notional_usd"]
            equity_flow_4w_notional_usd = latest_risk["equity_flow_4w_notional_usd"]
            vix_net_notional_usd = latest_risk["vix_net_notional_usd"]
            vix_flow_1w_notional_usd = latest_risk["vix_flow_1w_notional_usd"]
            vix_flow_4w_notional_usd = latest_risk["vix_flow_4w_notional_usd"]

            players.append({
                "key": category,
                "label": label,
                "markets": markets,
                "latest_change_from_date": previous_report_date,
                "latest_change_to_date": report_date,
                "equity_long_notional_usd": sum(markets[m]["long_notional_usd"] for m in ("sp500", "nq")),
                "equity_short_notional_usd": sum(markets[m]["short_notional_usd"] for m in ("sp500", "nq")),
                "equity_net_notional_usd": equity_net_notional_usd,
                "equity_flow_1w_notional_usd": equity_flow_1w_notional_usd,
                "equity_flow_4w_notional_usd": equity_flow_4w_notional_usd,
                "sp500_flow_1w_direction": market_flow_direction(markets["sp500"]),
                "nq_flow_1w_direction": market_flow_direction(markets["nq"]),
                "equity_flow_1w_direction": equity_flow_direction,
                "equity_flow_1w_balance_ratio": equity_flow_balance_ratio,
                "vix_net_notional_usd": vix_net_notional_usd,
                "vix_flow_1w_notional_usd": vix_flow_1w_notional_usd,
                "vix_flow_4w_notional_usd": vix_flow_4w_notional_usd,
                "vix_risk_flow_1w_notional_usd": -vix_flow_1w_notional_usd,
                "vix_risk_flow_4w_notional_usd": -vix_flow_4w_notional_usd,
                "vix_flow_1w_direction": vix_risk_flow_direction(markets["vix"]),
                "risk_net_notional_usd": equity_net_notional_usd - vix_net_notional_usd,
                "risk_flow_1w_notional_usd": equity_flow_1w_notional_usd - vix_flow_1w_notional_usd,
                "risk_flow_4w_notional_usd": equity_flow_4w_notional_usd - vix_flow_4w_notional_usd,
                "risk_flow_1w_direction": latest_risk["risk_flow_1w_direction"],
                "risk_flow_1w_balance_ratio": latest_risk["risk_flow_1w_balance_ratio"],
                "risk_net_13w_change_notional_usd": risk_net_13w_change_notional_usd,
                "risk_net_26w_change_notional_usd": risk_net_26w_change_notional_usd,
                "risk_trend_13w_direction": signed_total_direction(risk_net_13w_change_notional_usd),
                "risk_trend_26w_direction": signed_total_direction(risk_net_26w_change_notional_usd),
                "risk_history": risk_history,
                "position_score": position_score,
                "flow_1w_score": flow_1w_score,
                "flow_4w_score": flow_4w_score,
                "short_term_bias_score": combined_score,
                "short_term_bias": cross_market_bias_label(combined_score),
                "divergence": cross_market_divergence(markets),
            })

        datasets[dataset_key] = {
            "available": bool(players),
            "report_date": report_date,
            "previous_report_date": previous_report_date,
            "players": players,
        }

    return {
        "datasets": datasets,
        "contract_specs": CONTRACT_SPECS,
        "source_links": {
            "tff": "https://www.cftc.gov/dea/newcot/FinFutWk.txt",
            "legacy": "https://www.cftc.gov/dea/newcot/deafut.txt",
            "definitions": "https://www.cftc.gov/MarketReports/CommitmentsofTraders/ExplanatoryNotes/index.htm",
        },
        "methodology": {
            "notional": "Futures-equivalent notional = contracts x report-date index level x the CFTC-published contract multiplier.",
            "equity_total": "S&P 500 and NASDAQ-100 notionals are summed as equity-index exposure; they still overlap economically.",
            "vix": "VIX is counted as an inverse risk leg: buying VIX subtracts from the equity-risk read, while selling VIX adds to it. Raw VIX notional is still shown separately because volatility exposure is not a clean dollar-for-dollar equity beta.",
            "bias": "Short-term bias = 60% one-week flow z-score + 40% four-week flow z-score across S&P 500, NASDAQ-100, and inverse VIX, each normalized against up to 156 prior reports.",
            "market_direction": "SP and NQ direction uses each player's one-week net-position change. Changes within +/-0.10% of market open interest are Neutral.",
            "equity_flow_direction": "Combined SP+NQ direction uses summed futures-equivalent notional. It is Mixed when opposing legs leave less than 15% of gross flow after netting.",
            "risk_flow_direction": "Risk-on exposure direction uses SP+NQ minus VIX flow, so VIX buying is bearish and VIX selling is bullish. It is Mixed when the signed total is less than 15% of gross absolute flow.",
            "risk_trend": "Long-term risk-on exposure trend is the historical net notional of SP+NQ minus VIX. The table also shows the 13-week change in that exposure net.",
            "zero_sum": "Do not add all players together to forecast the market: futures longs and shorts offset by construction. Dealer / Intermediary is excluded from directional risk-on reads because it is treated as structural offset inventory rather than standalone demand.",
        },
        "net_position_predictivity": load_net_position_predictivity_comparison(),
    }


def load_net_position_predictivity_comparison() -> dict[str, Any]:
    path = ROOT / "cot_cross_market_predictivity_output" / "net_position_combined_vs_single_summary.csv"
    if not path.exists():
        return {
            "available": False,
            "rows": [],
            "methodology": "Run cot_cross_market_predictivity.py to compare combined SP+NQ-VIX net direction with single-instrument net direction.",
        }

    df = pd.read_csv(path)
    if df.empty:
        return {
            "available": False,
            "rows": [],
            "methodology": "No valid long/short net-position comparison rows were produced.",
        }

    sort_cols = [
        col for col in ["dataset", "winner_rank", "strongest_abs_edge_pp", "combined_minus_best_single_abs_edge_pp"]
        if col in df.columns
    ]
    ascending = [True, True, False, False][:len(sort_cols)]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=ascending)

    counts = (
        df.groupby(["dataset", "winner"], dropna=False)
        .size()
        .reset_index(name="count")
        .to_dict("records")
    )
    return {
        "available": True,
        "rows": records(df),
        "counts": counts,
        "methodology": (
            "Long/short test uses raw net notional sign. SP and NQ positive net are risk-on; VIX is inverted so "
            "net short VIX is risk-on. Edge is average forward return when the signal is positive minus when it is "
            "negative, with Newey-West HAC p-values for overlapping horizons. TFF Dealer / Intermediary is excluded "
            "from this directional comparison."
        ),
    }


WEEKLY_DESK_TARGET_LABELS = {
    "sp500": "S&P 500",
    "nq": "NASDAQ-100",
    "vix": "VIX Futures",
    "rty": "Russell 2000",
    "dow": "Dow Jones",
    "gold": "Gold",
}

WEEKLY_DESK_RETAIL_KEYS = {
    "tff": "non_reportable",
    "legacy": "nonreportable",
}

WEEKLY_DESK_EXCLUDED_CATEGORIES = {
    "tff": set(STRUCTURAL_OFFSET_CATEGORIES["tff"]),
    "legacy": {"total_reportable", "commercial"},
}


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) else None


def finite_series(values: list[Any]) -> pd.Series:
    return pd.Series([finite_float(value) for value in values], dtype="float64").dropna()


def direction_from_signed(value: float | None, neutral: float = 0.0) -> str:
    if value is None:
        return "Mixed"
    if value > neutral:
        return "Bullish"
    if value < -neutral:
        return "Bearish"
    return "Mixed"


def compact_round(value: float | None, digits: int = 2) -> float | None:
    if value is None or not pd.notna(value):
        return None
    return round(float(value), digits)


def bounded_score(value: float | None, low: float = 0.0, high: float = 100.0) -> float:
    if value is None or not pd.notna(value):
        return low
    return max(low, min(high, float(value)))


def evidence_confidence_multiplier(
    evidence: str,
    n: float | None,
    hac_p: float | None,
    shrink_k: float = 75.0,
) -> float:
    """Shrink noisy historical edge toward zero before it reaches the UI score."""
    evidence_mult = {
        "supported": 1.0,
        "tentative": 0.70,
        "weak/mixed": 0.35,
        "none": 0.0,
    }.get(evidence, 0.0)
    if n is None or n <= 0:
        sample_mult = 0.0
    else:
        sample_mult = n / (n + shrink_k)
    if hac_p is None:
        p_mult = 0.50 if evidence in {"supported", "tentative"} else 0.20
    elif hac_p <= 0.05:
        p_mult = 1.0
    elif hac_p <= 0.10:
        p_mult = 0.75
    elif hac_p <= 0.20:
        p_mult = 0.45
    else:
        p_mult = 0.20
    return bounded_score(evidence_mult * sample_mult * p_mult, 0.0, 1.0)


def score_grade(score: float | None) -> str:
    if score is None:
        return "n/a"
    if score >= 70:
        return "Strong"
    if score >= 55:
        return "Elevated"
    if score >= 40:
        return "Watch"
    return "Context"


def confidence_grade(score: float | None) -> str:
    if score is None:
        return "Unknown"
    if score >= 70:
        return "High"
    if score >= 50:
        return "Medium"
    if score >= 35:
        return "Low"
    return "Weak"


def classify_position_change(
    direction: str,
    long_change: float | None,
    short_change: float | None,
    net_change: float | None,
) -> str:
    if long_change is None or short_change is None or net_change is None:
        return "Flow split n/a"
    if abs(net_change) < 1e-9:
        return "Net unchanged"
    if net_change > 0:
        if long_change > 0 and short_change >= 0:
            return "Long accumulation"
        if short_change < 0 and long_change <= 0:
            return "Short covering"
        if long_change > 0 and short_change < 0:
            return "Long add + short cover"
        return "Net bullish rotation"
    if short_change > 0 and long_change <= 0:
        return "Short accumulation"
    if long_change < 0 and short_change >= 0:
        return "Long liquidation"
    if long_change < 0 and short_change > 0:
        return "Long liquidate + shorts add"
    return "Net bearish rotation" if direction == "Bearish" else "Net flow rotation"


def price_record_at_or_before(price_records: list[dict[str, Any]], report_date: str) -> dict[str, Any] | None:
    eligible = [
        row for row in price_records
        if row.get("date") and row.get("date") <= report_date and finite_float(row.get("price")) is not None
    ]
    return eligible[-1] if eligible else None


def price_confirmation_payload(
    prices: dict[str, Any],
    market: str,
    report_date: str,
    direction: str,
) -> dict[str, Any]:
    price_records = (prices.get(market) or {}).get("records") or []
    latest = next((row for row in reversed(price_records) if finite_float(row.get("price")) is not None), None)
    report = price_record_at_or_before(price_records, report_date)
    if not latest or not report:
        return {"available": False}

    latest_price = finite_float(latest.get("price"))
    report_price = finite_float(report.get("price"))
    if latest_price is None or report_price is None or report_price == 0:
        return {"available": False}

    change_pct = (latest_price / report_price - 1.0) * 100.0
    anchored_records = [
        row for row in price_records
        if row.get("date")
        and report.get("date")
        and latest.get("date")
        and report.get("date") <= row.get("date") <= latest.get("date")
        and finite_float(row.get("price")) is not None
    ]
    anchored_prices = [finite_float(row.get("price")) for row in anchored_records]
    anchored_prices = [price for price in anchored_prices if price is not None]
    anchor_mean_price = sum(anchored_prices) / len(anchored_prices) if anchored_prices else None
    anchor_distance_pct = (
        (latest_price / anchor_mean_price - 1.0) * 100.0
        if anchor_mean_price not in (None, 0)
        else None
    )
    high_price = max(anchored_prices) if anchored_prices else None
    low_price = min(anchored_prices) if anchored_prices else None
    high_change_pct = (high_price / report_price - 1.0) * 100.0 if high_price not in (None, 0) else None
    low_change_pct = (low_price / report_price - 1.0) * 100.0 if low_price not in (None, 0) else None
    confirms = (
        direction == "Bullish" and change_pct > 0
        or direction == "Bearish" and change_pct < 0
    )
    contradicts = (
        direction == "Bullish" and change_pct < 0
        or direction == "Bearish" and change_pct > 0
    )
    return {
        "available": True,
        "report_date": report.get("date"),
        "latest_date": latest.get("date"),
        "report_price": compact_round(report_price, 2),
        "latest_price": compact_round(latest_price, 2),
        "change_pct": compact_round(change_pct, 2),
        "anchor_mean_price": compact_round(anchor_mean_price, 2),
        "anchor_distance_pct": compact_round(anchor_distance_pct, 2),
        "post_report_high_price": compact_round(high_price, 2),
        "post_report_low_price": compact_round(low_price, 2),
        "post_report_high_pct": compact_round(high_change_pct, 2),
        "post_report_low_pct": compact_round(low_change_pct, 2),
        "post_report_observations": len(anchored_prices),
        "confirms": confirms,
        "contradicts": contradicts,
    }


def load_predictivity_edge_maps() -> tuple[dict[tuple[str, str, str], dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    out_dir = ROOT / "cot_cross_market_predictivity_output"
    top_path = out_dir / "risk_exposure_predictivity_top_findings.csv"
    latest_path = out_dir / "latest_risk_exposure_signals.csv"
    edge_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    latest_map: dict[tuple[str, str], dict[str, Any]] = {}

    if latest_path.exists():
        latest = pd.read_csv(latest_path)
        label_to_key = {
            dataset: {label: key for key, label in cfg["categories"].items()}
            for dataset, cfg in DATASET_CONFIGS.items()
        }
        for row in records(latest):
            dataset = str(row.get("dataset") or "")
            player = str(row.get("player") or "")
            player_key = label_to_key.get(dataset, {}).get(player)
            if player_key:
                latest_map[(dataset, player_key)] = row

    if not top_path.exists():
        return edge_map, latest_map

    top = pd.read_csv(top_path)
    if top.empty:
        return edge_map, latest_map

    sort_cols = [col for col in ["evidence_rank", "hac_p", "top_minus_bottom_abs"] if col in top.columns]
    ascending = [True, True, False][:len(sort_cols)]
    if sort_cols:
        top = top.sort_values(sort_cols, ascending=ascending)

    for row in records(top):
        dataset = str(row.get("dataset") or "")
        player_key = str(row.get("player_key") or "")
        target = str(row.get("target") or "")
        signal = str(row.get("signal") or "")
        evidence = str(row.get("evidence") or "")
        if not dataset or not player_key or not target:
            continue
        if signal != "net_z":
            continue
        if evidence not in {"supported", "tentative"}:
            continue
        key = (dataset, player_key, target)
        edge_map.setdefault(key, row)

    return edge_map, latest_map


def predictive_edge_for_row(
    dataset: str,
    player_key: str,
    market: str,
    edge_map: dict[tuple[str, str, str], dict[str, Any]],
    latest_map: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    target = WEEKLY_DESK_TARGET_LABELS.get(market)
    if not target:
        return {"available": False}

    edge = edge_map.get((dataset, player_key, target))
    latest = latest_map.get((dataset, player_key), {})
    if not edge:
        return {"available": False}

    top_minus_bottom = finite_float(edge.get("bucket_top_minus_bottom"))
    hac_p = finite_float(edge.get("hac_p"))
    n = finite_float(edge.get("n"))
    top_drawdown = finite_float(edge.get("bucket_top_avg_drawdown"))
    bottom_drawdown = finite_float(edge.get("bucket_bottom_avg_drawdown"))
    risk_net_z = finite_float(latest.get("risk_net_z"))
    if top_minus_bottom is None:
        return {"available": False}

    current_bucket = "middle"
    if risk_net_z is not None and risk_net_z >= 1.0:
        current_bucket = "top"
    elif risk_net_z is not None and risk_net_z <= -1.0:
        current_bucket = "bottom"

    top_is_better = top_minus_bottom > 0
    if current_bucket == "middle":
        tone = "neutral"
    elif (current_bucket == "top" and top_is_better) or (current_bucket == "bottom" and not top_is_better):
        tone = "supportive"
    else:
        tone = "warning"

    evidence = str(edge.get("evidence") or "unknown")
    confidence_mult = evidence_confidence_multiplier(evidence, n, hac_p)
    drawdown_penalty = 0.0
    if top_drawdown is not None and bottom_drawdown is not None:
        drawdown_penalty = abs(top_drawdown) - abs(bottom_drawdown)
    utility_spread = top_minus_bottom - 0.35 * drawdown_penalty
    score = 0.0
    if current_bucket != "middle":
        raw_edge_score = min(abs(utility_spread), 6.0) / 6.0 * 24.0
        score = raw_edge_score * confidence_mult

    return {
        "available": True,
        "tone": tone,
        "score": compact_round(score, 1),
        "target": target,
        "horizon": edge.get("horizon"),
        "evidence": evidence,
        "hac_p": compact_round(hac_p, 4),
        "n": compact_round(n, 0),
        "top_minus_bottom": compact_round(top_minus_bottom, 2),
        "utility_spread": compact_round(utility_spread, 2),
        "confidence_multiplier": compact_round(confidence_mult, 2),
        "risk_net_z": compact_round(risk_net_z, 2),
        "current_bucket": current_bucket,
    }


def weekly_desk_peer_confirmation(
    data: dict[str, Any],
    dataset: str,
    market: str,
    player_key: str,
    current_direction: str,
) -> dict[str, Any]:
    if current_direction == "Mixed":
        return {"support": 0, "total": 0, "label": "Mixed", "peers": []}

    equity_markets = {"sp500", "nq", "rty", "dow"}
    if market in equity_markets or market == "vix":
        peer_markets = ["sp500", "nq", "rty", "dow", "vix"]
    else:
        peer_markets = [p for p in MARKET_LABELS if p != market]
    peers = []
    for peer_market in peer_markets:
        if peer_market == market:
            continue
        rows = ((data.get(dataset) or {}).get(peer_market) or {}).get("records") or []
        if not rows or f"{player_key}_net" not in rows[-1]:
            continue
        peer_net = finite_float(rows[-1].get(f"{player_key}_net"))
        peer_direction = direction_from_signed(peer_net)
        if peer_direction == "Mixed":
            continue
        # VIX is an inverse risk leg for equity index desk read.
        confirms = peer_direction == current_direction
        if peer_market == "vix" and market in equity_markets:
            confirms = peer_direction != current_direction
        elif market == "vix" and peer_market in equity_markets:
            confirms = peer_direction != current_direction
        peers.append({
            "market": peer_market,
            "label": MARKET_LABELS[peer_market],
            "direction": peer_direction,
            "confirms": confirms,
        })

    support = sum(1 for peer in peers if peer["confirms"])
    total = len(peers)
    if total == 0:
        label = "No peers"
    elif support == total:
        label = "Confirmed"
    elif support >= total / 2:
        label = "Partial"
    else:
        label = "Divergent"
    return {"support": support, "total": total, "label": label, "peers": peers}


def build_weekly_desk_payload(data: dict[str, Any], prices: dict[str, Any]) -> dict[str, Any]:
    edge_map, latest_edge_map = load_predictivity_edge_maps()
    rows: list[dict[str, Any]] = []

    for dataset, market_payloads in data.items():
        retail_key = WEEKLY_DESK_RETAIL_KEYS.get(dataset)
        for market, payload in market_payloads.items():
            if payload is None:
                continue
            records_ = payload.get("records") or []
            if len(records_) < 2:
                continue
            latest = records_[-1]
            previous = records_[-2]
            prior_4w = records_[-5] if len(records_) >= 5 else None
            prior_13w = records_[-14] if len(records_) >= 14 else None
            report_date = latest.get("date")
            retail_net = finite_float(latest.get(f"{retail_key}_net")) if retail_key else None
            excluded_players = WEEKLY_DESK_EXCLUDED_CATEGORIES.get(dataset, set())

            for player_key, player_label in (payload.get("categories") or {}).items():
                if player_key in excluded_players:
                    continue
                latest_net = finite_float(latest.get(f"{player_key}_net"))
                latest_net_oi = finite_float(latest.get(f"{player_key}_net_oi_pct"))
                previous_net = finite_float(previous.get(f"{player_key}_net"))
                latest_long = finite_float(latest.get(f"{player_key}_long"))
                latest_short = finite_float(latest.get(f"{player_key}_short"))
                previous_long = finite_float(previous.get(f"{player_key}_long"))
                previous_short = finite_float(previous.get(f"{player_key}_short"))
                if latest_net is None or latest_net_oi is None or previous_net is None:
                    continue

                net_history = finite_series([row.get(f"{player_key}_net_oi_pct") for row in records_])
                percentile = percentile_rank(net_history, latest_net_oi)
                z26 = trailing_z_score(
                    [float(value) for value in net_history.iloc[:-1].tail(26).tolist()],
                    latest_net_oi,
                    lookback=26,
                )
                weekly_change = latest_net - previous_net
                prior_4w_net = finite_float(prior_4w.get(f"{player_key}_net")) if prior_4w else None
                four_week_change = latest_net - prior_4w_net if prior_4w_net is not None else None
                abs_changes = []
                signed_changes = []
                for index in range(1, len(records_)):
                    current = finite_float(records_[index].get(f"{player_key}_net"))
                    prior = finite_float(records_[index - 1].get(f"{player_key}_net"))
                    if current is not None and prior is not None:
                        change = current - prior
                        signed_changes.append(change)
                        abs_changes.append(abs(change))
                gas = percentile_rank(pd.Series(abs_changes[:-1], dtype="float64"), abs(weekly_change)) if len(abs_changes) > 2 else None
                weekly_change_percentile = (
                    percentile_rank(pd.Series(signed_changes[:-1], dtype="float64"), weekly_change)
                    if len(signed_changes) > 2
                    else None
                )

                price_4w = None
                if prior_4w and finite_float(prior_4w.get("price")) not in (None, 0):
                    price_4w = (float(latest.get("price")) / float(prior_4w.get("price")) - 1.0) * 100.0
                price_13w = None
                if prior_13w and finite_float(prior_13w.get("price")) not in (None, 0):
                    price_13w = (float(latest.get("price")) / float(prior_13w.get("price")) - 1.0) * 100.0

                direction = direction_from_signed(latest_net)
                price_divergence = (
                    direction == "Bullish" and price_13w is not None and price_13w < 0
                    or direction == "Bearish" and price_13w is not None and price_13w > 0
                )
                retail_divergence = (
                    player_key != retail_key
                    and retail_net is not None
                    and latest_net * retail_net < 0
                )
                peer = weekly_desk_peer_confirmation(data, dataset, market, player_key, direction)
                edge = predictive_edge_for_row(dataset, player_key, market, edge_map, latest_edge_map)
                price_confirmation = price_confirmation_payload(prices, market, str(report_date), direction)

                long_change = (
                    latest_long - previous_long
                    if latest_long is not None and previous_long is not None
                    else None
                )
                short_change = (
                    latest_short - previous_short
                    if latest_short is not None and previous_short is not None
                    else None
                )
                movement_type = classify_position_change(direction, long_change, short_change, weekly_change)

                rank_distance = abs((percentile or 50.0) - 50.0) / 50.0
                robust_rank_score = (float(percentile) / 50.0 - 1.0) if percentile is not None else None
                stat_extreme = min(max((abs(z26 or 0.0) - 0.50) / 1.75, 0.0), 1.0)
                edge_score = finite_float(edge.get("score")) or 0.0
                edge_confidence = finite_float(edge.get("confidence_multiplier")) or 0.0
                sample_n = finite_float(edge.get("n"))
                sample_score = sample_n / (sample_n + 75.0) * 100.0 if sample_n else 25.0
                peer_score = (
                    14.0 if peer.get("label") == "Confirmed"
                    else 8.0 if peer.get("label") == "Partial"
                    else -8.0 if peer.get("label") == "Divergent"
                    else 0.0
                )
                price_score = (
                    14.0 if price_confirmation.get("confirms")
                    else -10.0 if price_confirmation.get("contradicts")
                    else 0.0
                )
                retail_score = 8.0 if retail_divergence else 0.0
                is_retail = player_key == retail_key
                if is_retail:
                    # Non-reportable is contrarian: retail bullish → bearish, retail bearish → bullish
                    # Use signed inverse rank (lower weight to avoid dominating the score)
                    inverted_rank = -(robust_rank_score or 0.0)
                    rank_contrib = inverted_rank * 30.0
                    z26_contrib = -(z26 or 0.0) * 12.0
                else:
                    rank_contrib = rank_distance * 44.0
                    z26_contrib = stat_extreme * 22.0
                timing_score = bounded_score(
                    (gas or 0.0) * 0.42
                    + (12.0 if abs(weekly_change) > 0 else 0.0)
                    + price_score
                    + max(peer_score, 0.0)
                    + edge_score * 0.35
                )
                positioning_regime_score = bounded_score(
                    rank_contrib
                    + z26_contrib
                    + edge_score
                    + retail_score
                    + (8.0 if price_divergence else 0.0)
                )
                latest_risk_edge = latest_edge_map.get((dataset, player_key), {})
                risk_net_z = finite_float(latest_risk_edge.get("risk_net_z"))
                risk_trend13_z = finite_float(latest_risk_edge.get("risk_trend13_z"))
                risk_trend26_z = finite_float(latest_risk_edge.get("risk_trend26_z"))
                risk_on_exposure_score = bounded_score(
                    50.0
                    + 13.0 * (risk_net_z or 0.0)
                    + 7.0 * (risk_trend13_z or 0.0)
                    + 4.0 * (risk_trend26_z or 0.0)
                )
                evidence_base = 25.0 + sample_score * 0.24 + edge_confidence * 30.0
                confidence_score = bounded_score(
                    evidence_base
                    + (10.0 if price_confirmation.get("confirms") else 0.0)
                    + (8.0 if peer.get("label") in {"Confirmed", "Partial"} else 0.0)
                    - (12.0 if price_confirmation.get("contradicts") else 0.0)
                    - (12.0 if peer.get("label") == "Divergent" else 0.0)
                )
                raw_action_score = (
                    0.24 * timing_score
                    + 0.38 * positioning_regime_score
                    + 0.20 * risk_on_exposure_score
                    + 0.18 * confidence_score
                )
                confidence_gate = 0.45 + min(confidence_score, 100.0) / 100.0 * 0.55
                composite = bounded_score(raw_action_score * confidence_gate)
                if confidence_score < 35.0:
                    composite = min(composite, 39.0)
                signal = score_grade(composite)
                evidence_grade = confidence_grade(confidence_score)
                score_components = [
                    {
                        "key": "timing",
                        "label": "Timing",
                        "score": compact_round(timing_score, 1),
                        "detail": "1w impulse, price response, peer confirmation, and any short-horizon edge.",
                    },
                    {
                        "key": "regime",
                        "label": "Regime",
                        "score": compact_round(positioning_regime_score, 1),
                        "detail": "Current net/OI rank, 26w z-score, and medium-horizon edge.",
                    },
                    {
                        "key": "exposure",
                        "label": "Risk-on exposure",
                        "score": compact_round(risk_on_exposure_score, 1),
                        "detail": "SP+NQ-VIX net/trend exposure for the same player; VIX is inverted.",
                    },
                    {
                        "key": "confidence",
                        "label": "Confidence",
                        "score": compact_round(confidence_score, 1),
                        "detail": "Sample size, HAC evidence, price confirmation, and peer agreement.",
                    },
                ]
                top_contributors = [
                    {"label": "Net/OI rank distance", "value": compact_round(rank_distance * 44.0, 1)},
                    {"label": "Weekly impulse", "value": compact_round((gas or 0.0) * 0.42, 1)},
                    {"label": "Backtested edge", "value": compact_round(edge_score, 1)},
                    {"label": "Price confirmation", "value": compact_round(price_score, 1)},
                    {"label": "Peer confirmation", "value": compact_round(peer_score, 1)},
                ]

                rows.append({
                    "dataset": dataset,
                    "dataset_label": DATASET_LABELS.get(dataset, dataset),
                    "market": market,
                    "market_label": MARKET_LABELS.get(market, market),
                    "player_key": player_key,
                    "player_label": player_label,
                    "report_date": report_date,
                    "composite": compact_round(composite, 1),
                    "raw_action_score": compact_round(raw_action_score, 1),
                    "signal": signal,
                    "evidence_grade": evidence_grade,
                    "direction": direction,
                    "latest_net": compact_round(latest_net, 0),
                    "latest_net_oi_pct": compact_round(latest_net_oi, 2),
                    "weekly_change": compact_round(weekly_change, 0),
                    "weekly_change_percentile": compact_round(weekly_change_percentile, 1),
                    "four_week_change": compact_round(four_week_change, 0),
                    "long_change": compact_round(long_change, 0),
                    "short_change": compact_round(short_change, 0),
                    "movement_type": movement_type,
                    "percentile": compact_round(percentile, 1),
                    "robust_rank_score": compact_round(robust_rank_score, 2),
                    "z26": compact_round(z26, 2),
                    "gas": compact_round(gas, 1),
                    "weekly_change_magnitude_percentile": compact_round(gas, 1),
                    "timing_score": compact_round(timing_score, 1),
                    "positioning_regime_score": compact_round(positioning_regime_score, 1),
                    "risk_on_exposure_score": compact_round(risk_on_exposure_score, 1),
                    "confidence_score": compact_round(confidence_score, 1),
                    "score_components": score_components,
                    "top_contributors": top_contributors,
                    "price_4w_pct": compact_round(price_4w, 2),
                    "price_13w_pct": compact_round(price_13w, 2),
                    "price_divergence": bool(price_divergence),
                    "retail_divergence": bool(retail_divergence),
                    "peer_confirmation": peer,
                    "predictive_edge": edge,
                    "price_confirmation": price_confirmation,
                })

    sorted_rows = sorted(rows, key=lambda row: float(row.get("composite") or 0.0), reverse=True)
    strong = sum(1 for row in sorted_rows if row.get("signal") == "Strong")
    elevated = sum(1 for row in sorted_rows if row.get("signal") == "Elevated")
    return {
        "available": bool(sorted_rows),
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "headline": f"{strong} strong and {elevated} elevated local COT setups",
        "rows": sorted_rows,
        "methodology": {
            "score": "Local 0-100 setup score is now evidence-weighted: Timing, Regime, Risk-on Exposure, and Confidence are scored separately, then confidence-gated. Weak or stale evidence is shrunk toward Context instead of forced into Bullish/Bearish.",
            "scope": "Built from the local consolidated CFTC pipeline for S&P 500, NASDAQ-100, and VIX. BSS was used only as workflow inspiration; Dealer / Intermediary holdings are ignored for directional setup ranking.",
            "predictivity": "Backtested edge uses analysis/cot_cross_market_predictivity_output/risk_exposure_predictivity_top_findings.csv when present, with sample-size shrinkage, HAC p-value penalty, and drawdown-aware utility.",
            "price": "Anchored price response uses the mean of available daily price observations from the COT report date through the latest price date; it is an anchored mean, not VWAP.",
        },
    }


def load_price(path: Path, series_id: str) -> list[dict]:
    df = pd.read_csv(path)
    df.columns = [c.strip().lstrip("\ufeff") for c in df.columns]
    date_col = "observation_date" if "observation_date" in df.columns else "date"
    value_col = series_id if series_id in df.columns else [c for c in df.columns if c != date_col][0]
    parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
    out = pd.DataFrame({
        "date": parsed_dates,
        "price": pd.to_numeric(df[value_col].replace(".", pd.NA), errors="coerce"),
    }).dropna()
    out = out.loc[out["date"] <= pd.Timestamp(datetime.now(UTC).date())]
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return records(out)


def latest_price_file(series_id: str) -> Path:
    return ensure_fred_factor_file(series_id, min_rows=FRED_MIN_ROWS.get(series_id, 0))


def load_prices() -> dict[str, dict[str, Any]]:
    return {
        market: {
            "label": cfg["label"],
            "records": load_price(latest_price_file(cfg["fred_id"]), cfg["fred_id"]),
        }
        for market, cfg in PRICE_SERIES.items()
    }


def write_series_csv(dest: Path, series_id: str, rows: list[tuple[str, Any]]) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["observation_date", series_id])
        for observation_date, value in rows:
            writer.writerow([observation_date, value])


def load_fred_api_key() -> str | None:
    env_key = os.environ.get("FRED_API_KEY", "").strip()
    if env_key:
        return env_key
    try:
        file_key = FRED_API_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return file_key or None


def cached_csv_latest_date(path: Path) -> str | None:
    try:
        last_data_line = ""
        with path.open("r", encoding="utf-8-sig", errors="replace") as fh:
            next(fh, None)
            for line in fh:
                if line.strip():
                    last_data_line = line
        return last_data_line.split(",", 1)[0].strip() or None
    except OSError:
        return None


def merge_series_csv(dest: Path, series_id: str, rows: list[tuple[str, Any]]) -> None:
    merged: dict[str, Any] = {}
    if dest.exists():
        with dest.open("r", newline="", encoding="utf-8-sig", errors="replace") as fh:
            reader = csv.DictReader(fh)
            if reader.fieldnames:
                date_col = "observation_date" if "observation_date" in reader.fieldnames else "date"
                value_col = series_id if series_id in reader.fieldnames else next(
                    (field for field in reader.fieldnames if field != date_col),
                    None,
                )
                if value_col:
                    for row in reader:
                        observation_date = str(row.get(date_col, "")).strip()
                        value = str(row.get(value_col, "")).strip()
                        if observation_date and value and value != ".":
                            merged[observation_date] = value
    for observation_date, value in rows:
        if observation_date and value is not None:
            merged[str(observation_date)] = value
    write_series_csv(dest, series_id, sorted(merged.items()))


def fetch_fred_api_csv(series_id: str, dest: Path, timeout: int = 60) -> bool:
    if requests is None:
        return False
    api_key = load_fred_api_key()
    if not api_key:
        return False
    params: dict[str, Any] = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
    }
    latest = cached_csv_latest_date(dest)
    if latest:
        params["observation_start"] = latest
    url = f"https://api.stlouisfed.org/fred/series/observations?{urllib.parse.urlencode(params)}"
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
    response.raise_for_status()
    observations = response.json().get("observations") or []
    rows = [
        (str(item.get("date", "")).strip(), str(item.get("value", "")).strip())
        for item in observations
        if str(item.get("date", "")).strip() and str(item.get("value", "")).strip() not in {"", "."}
    ]
    if not rows:
        return False
    merge_series_csv(dest, series_id, rows)
    return True


def fetch_yahoo_index_price_csv(dest: Path, series_id: str) -> None:
    if requests is None:
        raise RuntimeError("requests is required to fetch Yahoo index price data.")
    symbol = YAHOO_INDEX_PRICE_SERIES[series_id]
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=10y&interval=1d"
    response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
    response.raise_for_status()
    payload = response.json()
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart returned no data for {symbol}.")
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    rows: list[tuple[str, Any]] = []
    for timestamp, close_value in zip(timestamps, closes):
        if close_value is None:
            continue
        observation_date = datetime.fromtimestamp(int(timestamp), UTC).date().isoformat()
        rows.append((observation_date, round(float(close_value), 3)))
    meta = result.get("meta") or {}
    current_price = meta.get("regularMarketPrice")
    current_time = meta.get("regularMarketTime")
    if current_price is not None and current_time is not None:
        observation_date = datetime.fromtimestamp(int(current_time), UTC).date().isoformat()
        rows.append((observation_date, round(float(current_price), 3)))
    if not rows:
        raise RuntimeError(f"Yahoo chart returned no usable close values for {symbol}.")
    merge_series_csv(dest, series_id, rows)


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def fetch_treasury_xml_bytes(data_key: str, year: int) -> bytes:
    cache_key = (data_key, year)
    if cache_key in TREASURY_XML_CACHE:
        return TREASURY_XML_CACHE[cache_key]
    query = urllib.parse.urlencode({"data": data_key, "field_tdr_date_value": str(year)})
    url = f"{TREASURY_XML_URL}?{query}"
    if requests is not None:
        response = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
        response.raise_for_status()
        payload = response.content
    else:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    TREASURY_XML_CACHE[cache_key] = payload
    return payload


def parse_treasury_xml_series(data_key: str, value_field: str) -> list[tuple[str, Any]]:
    current_year = datetime.now(UTC).year
    rows: dict[str, Any] = {}
    for year in range(current_year - TREASURY_XML_YEAR_LOOKBACK + 1, current_year + 1):
        root = ET.fromstring(fetch_treasury_xml_bytes(data_key, year))
        for entry in root.iter():
            if xml_local_name(entry.tag) != "entry":
                continue
            properties = next((node for node in entry.iter() if xml_local_name(node.tag) == "properties"), None)
            if properties is None:
                continue
            values = {xml_local_name(child.tag): (child.text or "").strip() for child in list(properties)}
            observation_date = values.get("NEW_DATE", "").split("T", 1)[0]
            value = values.get(value_field)
            if observation_date and value:
                rows[observation_date] = value
    return sorted(rows.items())


def fetch_treasury_yield_csv(dest: Path, series_id: str) -> None:
    data_key, value_field = TREASURY_XML_SERIES[series_id]
    rows = parse_treasury_xml_series(data_key, value_field)
    if not rows:
        raise RuntimeError(f"Treasury XML returned no usable rows for {series_id}.")
    merge_series_csv(dest, series_id, rows)


def fetch_ofr_rate_csv(dest: Path, series_id: str, url: str) -> None:
    if requests is None:
        raise RuntimeError("requests is required to fetch OFR rate data.")
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
    response.raise_for_status()
    payload = response.json()
    rows = [
        (str(item[0]), item[1])
        for item in payload
        if isinstance(item, list) and len(item) >= 2 and item[1] is not None
    ]
    write_series_csv(dest, series_id, rows)


def fetch_ofr_sofr_csv(dest: Path) -> None:
    fetch_ofr_rate_csv(dest, "SOFR", OFR_SOFR_URL)


def fetch_ofr_effr_csv(dest: Path) -> None:
    fetch_ofr_rate_csv(dest, "EFFR", OFR_EFFR_URL)


def fetch_fed_ddp_series_csv(dest: Path, series_id: str, source_url: str, value_column: str) -> None:
    if requests is None:
        raise RuntimeError("requests is required to fetch Federal Reserve DDP data.")
    response = requests.get(source_url, timeout=60, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
    response.raise_for_status()
    reader = csv.reader(io.StringIO(response.text))
    rows: list[tuple[str, Any]] = []
    header: list[str] | None = None
    value_index: int | None = None
    for row in reader:
        if not row:
            continue
        if row[0].strip().lower() == "time period":
            header = [item.strip() for item in row]
            if value_column not in header:
                raise KeyError(f"{value_column} was not found in Federal Reserve DDP output.")
            value_index = header.index(value_column)
            continue
        if header is None or value_index is None:
            continue
        if len(row) <= value_index:
            continue
        value = row[value_index].strip()
        if not value:
            continue
        rows.append((row[0].strip(), value))
    write_series_csv(dest, series_id, rows)


def fetch_fed_iorb_csv(dest: Path) -> None:
    fetch_fed_ddp_series_csv(dest, "IORB", FED_IORB_URL, "RESBM_N.D")


def fetch_fed_h8_bank_treasury_agency_csv(dest: Path) -> None:
    fetch_fed_ddp_series_csv(dest, "USGSEC", FED_H8_BANK_TREASURY_AGENCY_URL, "B1003NCBA")


def fetch_fed_h8_bank_assets_csv(dest: Path) -> None:
    fetch_fed_ddp_series_csv(dest, "BANKASSETS", FED_H8_BANK_ASSETS_URL, "B1058NCBA")


SPECIAL_SERIES_FETCHERS = {
    "SOFR": fetch_ofr_sofr_csv,
    "EFFR": fetch_ofr_effr_csv,
    "IORB": fetch_fed_iorb_csv,
    "USGSEC": fetch_fed_h8_bank_treasury_agency_csv,
    "BANKASSETS": fetch_fed_h8_bank_assets_csv,
}


def fetch_fred_csv(series_id: str, dest: Path, timeout: int = 60) -> None:
    special_fetcher = SPECIAL_SERIES_FETCHERS.get(series_id)
    if special_fetcher is not None:
        special_fetcher(dest)
        return
    if series_id in TREASURY_XML_SERIES:
        try:
            fetch_treasury_yield_csv(dest, series_id)
            return
        except Exception:
            pass
    dest.parent.mkdir(parents=True, exist_ok=True)
    if series_id in YAHOO_INDEX_PRICE_SERIES:
        fetch_yahoo_index_price_csv(dest, series_id)
        return

    try:
        if fetch_fred_api_csv(series_id, dest, timeout=timeout):
            return
    except Exception:
        pass

    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    if requests is not None:
        try:
            response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
            response.raise_for_status()
            dest.write_bytes(response.content)
        except Exception:
            raise
        return
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 COT dashboard builder"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            dest.write_bytes(response.read())
    except Exception:
        raise


def csv_data_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return max(sum(1 for _line in fh) - 1, 0)
    except OSError:
        return 0


def ensure_fred_factor_file(series_id: str, min_rows: int = 0, timeout: int = 60) -> Path:
    data_dir = PROJECT / "data"
    matches = sorted(data_dir.glob(f"{series_id}*.csv"), key=lambda p: p.stat().st_mtime)
    if matches and (not min_rows or csv_data_rows(matches[-1]) >= min_rows):
        if series_id in YAHOO_INDEX_PRICE_SERIES:
            try:
                fetch_yahoo_index_price_csv(matches[-1], series_id)
            except Exception:
                pass
        if series_id in TREASURY_XML_SERIES:
            try:
                fetch_treasury_yield_csv(matches[-1], series_id)
            except Exception:
                pass
        return matches[-1]

    dest = data_dir / f"{series_id}.csv"
    try:
        fetch_fred_csv(series_id, dest, timeout=timeout)
    except Exception:
        if matches:
            return matches[-1]
        raise
    return dest


def factor_records_from_frame(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = pd.DataFrame({
        "date": pd.to_datetime(df["date"], errors="coerce"),
        "value": pd.to_numeric(df["value"], errors="coerce"),
    }).dropna()
    out = out.sort_values("date")
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return records(out)


def load_cnn_fear_greed() -> list[dict[str, Any]]:
    path = PROJECT / "fear-greed-data-main" / "fear-greed-data-main" / "fear-greed.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing CNN Fear & Greed CSV: {path}")
    df = pd.read_csv(path)
    return factor_records_from_frame(df.rename(columns={"Date": "date", "Fear Greed": "value"}))


def load_cnn_json_factor(json_key: str) -> list[dict[str, Any]]:
    path = PROJECT / "fear-greed-data-main" / "fear-greed-data-main" / "json" / "cnn_output.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing CNN JSON output: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get(json_key, {}).get("data") or []
    if not rows:
        raise ValueError(f"CNN JSON output has no data for {json_key}")
    df = pd.DataFrame({
        "date": pd.to_datetime([row.get("x") for row in rows], unit="ms", errors="coerce"),
        "value": [row.get("y") for row in rows],
    })
    return factor_records_from_frame(df)


def load_fred_factor(series_id: str) -> list[dict[str, Any]]:
    return [
        {"date": row["date"], "value": row["price"]}
        for row in load_price(ensure_fred_factor_file(series_id, min_rows=FRED_MIN_ROWS.get(series_id, 0)), series_id)
    ]


def load_factor_data() -> dict[str, dict[str, Any]]:
    payload: dict[str, dict[str, Any]] = {}
    for key, cfg in FACTOR_SERIES.items():
        kind = cfg["kind"]
        if kind == "cnn_csv":
            factor_records = load_cnn_fear_greed()
        elif kind == "cnn_json":
            factor_records = load_cnn_json_factor(str(cfg["json_key"]))
        elif kind == "fred":
            factor_records = [
                {"date": row["date"], "value": row["price"]}
                for row in load_price(
                    ensure_fred_factor_file(
                        str(cfg["fred_id"]),
                        min_rows=int(cfg.get("min_rows") or FRED_MIN_ROWS.get(str(cfg["fred_id"]), 0)),
                    ),
                    str(cfg["fred_id"]),
                )
            ]
        else:
            raise ValueError(f"Unknown factor kind: {kind}")

        payload[key] = {
            "label": cfg["label"],
            "source": cfg["source"],
            "format": cfg["format"],
            "records": factor_records,
        }
    return payload


def load_liquidity_series(series_id: str, scale_to_bn: float) -> list[dict[str, Any]]:
    rows = load_price(ensure_fred_factor_file(series_id, min_rows=FRED_MIN_ROWS.get(series_id, 0)), series_id)
    out = []
    for row in rows:
        value = row.get("price")
        if value is None:
            continue
        out.append({"date": row["date"], "value": round(float(value) * scale_to_bn, 3)})
    return out


def records_by_date(record_list: list[dict[str, Any]]) -> dict[str, float]:
    return {
        str(row["date"]): float(row["value"])
        for row in record_list
        if row.get("date") and row.get("value") is not None
    }


def build_net_liquidity_records(series_payload: dict[str, Any]) -> list[dict[str, Any]]:
    sources = {key: records_by_date(payload["records"]) for key, payload in series_payload.items()}
    dates = sorted({date for rows in sources.values() for date in rows})
    latest: dict[str, float | None] = {key: None for key in sources}
    out = []
    for date in dates:
        for key, rows in sources.items():
            if date in rows:
                latest[key] = rows[date]
        fed = latest.get("fed_balance_sheet")
        rrp = latest.get("reverse_repo")
        tga = latest.get("treasury_cash")
        if fed is None or rrp is None or tga is None:
            continue
        out.append({
            "date": date,
            "value": round(float(fed) - float(rrp) - float(tga), 3),
            "fed_balance_sheet": round(float(fed), 3),
            "reverse_repo": round(float(rrp), 3),
            "treasury_cash": round(float(tga), 3),
        })
    return out


def build_rate_spread_records(left_records: list[dict[str, Any]], right_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = {"left": records_by_date(left_records), "right": records_by_date(right_records)}
    dates = sorted({date for rows in sources.values() for date in rows})
    latest: dict[str, float | None] = {"left": None, "right": None}
    out = []
    for date_ in dates:
        for key, rows in sources.items():
            if date_ in rows:
                latest[key] = rows[date_]
        if latest["left"] is None or latest["right"] is None:
            continue
        out.append({
            "date": date_,
            "value": round(float(latest["left"]) - float(latest["right"]), 4),
            "sofr": round(float(latest["left"]), 4),
            "iorb": round(float(latest["right"]), 4),
        })
    return out


def load_funding_data() -> dict[str, Any]:
    definitions: dict[str, Any] = {}
    for key, cfg in FUNDING_SERIES.items():
        series_id = str(cfg["series_id"])
        definitions[key] = {
            "label": cfg["label"],
            "source": cfg["source"],
            "unit": cfg["unit"],
            "polarity": cfg["polarity"],
            "records": [
                {"date": row["date"], "value": round(float(row["price"]), 4)}
                for row in load_price(ensure_fred_factor_file(series_id, min_rows=FRED_MIN_ROWS.get(series_id, 0)), series_id)
            ],
        }
    definitions["sofr_iorb_spread"] = {
        "label": "SOFR - IORB spread",
        "source": "OFR SOFR minus Fed DDP IORB",
        "unit": "percentage points",
        "polarity": "negative",
        "records": build_rate_spread_records(definitions["sofr"]["records"], definitions["iorb"]["records"]),
    }
    definitions["effr_iorb_spread"] = {
        "label": "EFFR - IORB spread",
        "source": "OFR EFFR minus Fed DDP IORB",
        "unit": "percentage points",
        "polarity": "negative",
        "records": build_rate_spread_records(definitions["effr"]["records"], definitions["iorb"]["records"]),
    }
    return {"definitions": definitions}


def load_liquidity_data() -> dict[str, Any]:
    definitions = {}
    for key, cfg in LIQUIDITY_SERIES.items():
        definitions[key] = {
            "label": cfg["label"],
            "source": cfg["source"],
            "unit": cfg["unit"],
            "polarity": cfg["polarity"],
            "records": load_liquidity_series(str(cfg["fred_id"]), float(cfg["scale_to_bn"])),
        }
    definitions["net_liquidity"] = {
        "label": "Net liquidity proxy",
        "source": "WALCL - WDTGAL - RRPONTSYD",
        "unit": "USD bn",
        "polarity": "positive",
        "records": build_net_liquidity_records(definitions),
    }
    return {"definitions": definitions, "funding": load_funding_data()}


def macro_regime_label(score: float | None) -> str:
    if score is None or pd.isna(score):
        return "n/a"
    if score >= 70:
        return "Strong risk-on"
    if score >= 55:
        return "Supportive"
    if score >= 45:
        return "Neutral"
    if score >= 30:
        return "Defensive"
    return "Risk-off"


def load_macro_series(column: str, spec: dict[str, Any]) -> pd.DataFrame:
    empty = pd.DataFrame({
        "date": pd.Series(dtype="datetime64[ns]"),
        column: pd.Series(dtype="float64"),
    })
    series_id = str(spec["fred_id"])
    try:
        fetch_timeout = 15 if not spec.get("required", True) else 60
        rows = load_price(
            ensure_fred_factor_file(series_id, min_rows=FRED_MIN_ROWS.get(series_id, 0), timeout=fetch_timeout),
            series_id,
        )
    except Exception:
        if not spec.get("required", True):
            return empty
        raise
    if not rows:
        return empty
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "date": pd.to_datetime(df["date"], errors="coerce"),
        column: pd.to_numeric(df["price"], errors="coerce") * float(spec.get("scale", 1.0)),
    }).dropna()
    return out.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def calendar_delta(df: pd.DataFrame, column: str, days: int) -> pd.Series:
    history = (
        df[["date", column]]
        .dropna()
        .rename(columns={"date": "history_date", column: "history_value"})
        .sort_values("history_date")
    )
    if history.empty:
        return pd.Series(index=df.index, dtype="float64")
    targets = pd.DataFrame({
        "row_index": df.index,
        "target_date": df["date"] - pd.Timedelta(days=days),
    }).sort_values("target_date")
    matched = pd.merge_asof(
        targets,
        history,
        left_on="target_date",
        right_on="history_date",
        direction="backward",
    )
    current = pd.to_numeric(df.loc[matched["row_index"], column], errors="coerce").reset_index(drop=True)
    prior = pd.to_numeric(matched["history_value"], errors="coerce").reset_index(drop=True)
    delta = current - prior
    out = pd.Series(index=df.index, dtype="float64")
    out.loc[matched["row_index"].to_numpy()] = delta.to_numpy()
    return out


def calendar_pct_change(df: pd.DataFrame, column: str, days: int) -> pd.Series:
    history = (
        df[["date", column]]
        .dropna()
        .rename(columns={"date": "history_date", column: "history_value"})
        .sort_values("history_date")
    )
    if history.empty:
        return pd.Series(index=df.index, dtype="float64")
    targets = pd.DataFrame({
        "row_index": df.index,
        "target_date": df["date"] - pd.Timedelta(days=days),
    }).sort_values("target_date")
    matched = pd.merge_asof(
        targets,
        history,
        left_on="target_date",
        right_on="history_date",
        direction="backward",
    )
    current = pd.to_numeric(df.loc[matched["row_index"], column], errors="coerce").reset_index(drop=True)
    prior = pd.to_numeric(matched["history_value"], errors="coerce").reset_index(drop=True)
    pct = (current / prior - 1.0) * 100.0
    pct = pct.where(prior != 0)
    out = pd.Series(index=df.index, dtype="float64")
    out.loc[matched["row_index"].to_numpy()] = pct.to_numpy()
    return out


def rolling_z_score_to_score(signal: pd.Series, window: int = 252, min_periods: int = 60) -> pd.Series:
    values = pd.to_numeric(signal, errors="coerce")
    mean = values.rolling(window, min_periods=min_periods).mean()
    std = values.rolling(window, min_periods=min_periods).std().mask(lambda s: s == 0)
    z = (values - mean) / std
    return (50.0 + z.clip(-3, 3) / 3.0 * 50.0).clip(0, 100).fillna(50.0)


def parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "null":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fiscaldata_get(path: str, params: dict[str, str]) -> dict[str, Any]:
    encoded = urllib.parse.urlencode(params)
    url = f"{path}?{encoded}"
    text = fetch_url_text(url, timeout=90)
    return json.loads(text)


def fetch_treasury_issuance_frame(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DataFrame:
    fields = "issue_date,auction_date,security_type,security_term,cusip,offering_amt"
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = fiscaldata_get(TREASURY_AUCTIONS_API, {
            "filter": f"issue_date:gte:{start_date.date()},issue_date:lte:{end_date.date()}",
            "fields": fields,
            "sort": "issue_date",
            "page[size]": "10000",
            "page[number]": str(page),
        })
        data = payload.get("data") or []
        if not data:
            break
        rows.extend(data)
        meta = payload.get("meta") or {}
        total_pages = int(meta.get("total-pages") or meta.get("total_pages") or page)
        if page >= total_pages:
            break
        page += 1

    out_rows = []
    for row in rows:
        amount = parse_numeric(row.get("offering_amt"))
        issue_date = pd.to_datetime(row.get("issue_date"), errors="coerce")
        if pd.isna(issue_date) or amount is None:
            continue
        out_rows.append({
            "date": issue_date.normalize(),
            "auction_date": row.get("auction_date"),
            "security_type": row.get("security_type"),
            "security_term": row.get("security_term"),
            "cusip": row.get("cusip"),
            "amount_bn": round(amount / 1_000_000_000.0, 3),
        })
    return pd.DataFrame(out_rows)


def load_treasury_issuance_frame(
    start_date: pd.Timestamp | None = None,
    end_date: pd.Timestamp | None = None,
) -> pd.DataFrame:
    start = pd.to_datetime(start_date if start_date is not None else "2016-01-01").normalize()
    end = pd.to_datetime(end_date if end_date is not None else (datetime.now(UTC) + timedelta(days=90))).normalize()
    try:
        df = fetch_treasury_issuance_frame(start, end)
        if not df.empty:
            if TREASURY_ISSUANCE_CACHE.exists():
                cached = pd.read_csv(TREASURY_ISSUANCE_CACHE)
                cached["date"] = pd.to_datetime(cached["date"], errors="coerce")
                cached["amount_bn"] = pd.to_numeric(cached["amount_bn"], errors="coerce")
                df = pd.concat([cached, df], ignore_index=True)
                df = df.dropna(subset=["date", "amount_bn"])
                df = df.drop_duplicates(["date", "cusip", "security_type", "security_term"], keep="last")
                df = df.sort_values("date").reset_index(drop=True)
            TREASURY_ISSUANCE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            cache = df.copy()
            cache["date"] = cache["date"].dt.strftime("%Y-%m-%d")
            cache.to_csv(TREASURY_ISSUANCE_CACHE, index=False)
            return df.loc[(df["date"] >= start) & (df["date"] <= end)].reset_index(drop=True)
    except Exception:
        pass

    if not TREASURY_ISSUANCE_CACHE.exists():
        return pd.DataFrame(columns=["date", "auction_date", "security_type", "security_term", "cusip", "amount_bn"])
    cached = pd.read_csv(TREASURY_ISSUANCE_CACHE)
    cached["date"] = pd.to_datetime(cached["date"], errors="coerce")
    cached["amount_bn"] = pd.to_numeric(cached["amount_bn"], errors="coerce")
    return cached.dropna(subset=["date", "amount_bn"]).loc[
        lambda frame: (frame["date"] >= start) & (frame["date"] <= end)
    ].reset_index(drop=True)


def observed_fixed_holiday(year: int, month: int, day: int) -> set[date]:
    actual = date(year, month, day)
    if actual.weekday() == 5:
        return {actual - timedelta(days=1)}
    if actual.weekday() == 6:
        return {actual + timedelta(days=1)}
    return {actual}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    current = date(year, month, 1)
    while current.weekday() != weekday:
        current += timedelta(days=1)
    return current + timedelta(days=7 * (n - 1))


def last_weekday(year: int, month: int, weekday: int) -> date:
    current = date(year, month, calendar_lib.monthrange(year, month)[1])
    while current.weekday() != weekday:
        current -= timedelta(days=1)
    return current


def us_federal_holidays(year: int) -> set[date]:
    holidays: set[date] = set()
    holidays |= observed_fixed_holiday(year, 1, 1)
    holidays.add(nth_weekday(year, 1, 0, 3))
    holidays.add(nth_weekday(year, 2, 0, 3))
    holidays.add(last_weekday(year, 5, 0))
    holidays |= observed_fixed_holiday(year, 6, 19)
    holidays |= observed_fixed_holiday(year, 7, 4)
    holidays.add(nth_weekday(year, 9, 0, 1))
    holidays.add(nth_weekday(year, 10, 0, 2))
    holidays |= observed_fixed_holiday(year, 11, 11)
    holidays.add(nth_weekday(year, 11, 3, 4))
    holidays |= observed_fixed_holiday(year, 12, 25)
    return holidays


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in us_federal_holidays(day.year)


def previous_business_day(day: date) -> date:
    current = day
    while not is_business_day(current):
        current -= timedelta(days=1)
    return current


def next_business_day(day: date) -> date:
    current = day
    while not is_business_day(current):
        current += timedelta(days=1)
    return current


def add_business_days(day: date, count: int) -> date:
    current = day
    added = 0
    while added < count:
        current += timedelta(days=1)
        if is_business_day(current):
            added += 1
    return current


def daterange(start: date, end: date) -> list[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def event_record(day: date, kind: str, issuer: str, label: str, source: str, source_url: str, amount_bn: float | None = None) -> dict[str, Any]:
    return {
        "date": day.isoformat(),
        "kind": kind,
        "issuer": issuer,
        "label": label,
        "source": source,
        "source_url": source_url,
        "amount_bn": round(float(amount_bn), 3) if amount_bn is not None and pd.notna(amount_bn) else None,
    }


def build_gse_cash_flow_events(start: date, end: date) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for year in range(start.year, end.year + 1):
        for month in range(1, 13):
            fannie_day = previous_business_day(date(year, month, 18))
            freddie_determination = next_business_day(date(year, month, 15))
            freddie_draft = add_business_days(freddie_determination, 2)
            events.append(event_record(
                fannie_day,
                "gse_cash_flow",
                "Fannie Mae",
                "Scheduled MBS P&I remittance",
                "Fannie Mae Selling Guide C3-2-03",
                FANNIE_REMITTANCE_SOURCE_URL,
            ))
            events.append(event_record(
                freddie_draft,
                "gse_cash_flow",
                "Freddie Mac",
                "Monthly P&I draft date",
                "Freddie Mac Investor Reporting",
                FREDDIE_REMITTANCE_SOURCE_URL,
            ))
    return [row for row in events if start.isoformat() <= row["date"] <= end.isoformat()]


def normalize_month_header(value: str) -> str:
    return re.sub(r"[^A-Z]", "", value.upper())


def parse_freddie_calendar_page(text: str, year: int, event_kind: str, issuer: str, label: str) -> list[dict[str, Any]]:
    month_lookup = {name.upper(): index for index, name in enumerate(calendar_lib.month_name) if name}
    current_month: int | None = None
    current_day = 1
    seen_week_header = False
    events: list[dict[str, Any]] = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().upper().split())
        normalized = normalize_month_header(line)
        if normalized in month_lookup:
            current_month = month_lookup[normalized]
            current_day = 1
            seen_week_header = False
            continue
        if current_month is None:
            continue
        if line == "S M T W T F S":
            seen_week_header = True
            continue
        if not seen_week_header:
            continue
        tokens = line.split()
        if not tokens or any(not (token.isdigit() or token in {"A", "H"}) for token in tokens):
            continue
        month_days = calendar_lib.monthrange(year, current_month)[1]
        for token in tokens:
            if current_day > month_days:
                break
            if token == "A":
                events.append(event_record(
                    date(year, current_month, current_day),
                    event_kind,
                    issuer,
                    label,
                    "Freddie Mac debt funding calendar",
                    FREDDIE_CALENDAR_URL_TEMPLATE.format(year=year),
                ))
                current_day += 1
            elif token == "H":
                current_day += 1
            else:
                parsed_day = int(token)
                current_day = max(current_day, parsed_day) + 1
    return events


def load_freddie_calendar_events(year: int) -> list[dict[str, Any]]:
    if PdfReader is None:
        return []
    FREDDIE_CALENDAR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = FREDDIE_CALENDAR_CACHE_DIR / f"freddie_reference_calendar_{year}.pdf"
    if not cache.exists():
        try:
            cache.write_bytes(fetch_url_bytes(FREDDIE_CALENDAR_URL_TEMPLATE.format(year=year), timeout=60))
        except Exception:
            return []
    try:
        reader = PdfReader(str(cache))
        notes_text = reader.pages[0].extract_text() if len(reader.pages) >= 1 else ""
        bills_text = reader.pages[1].extract_text() if len(reader.pages) >= 2 else ""
    except Exception:
        return []
    return [
        *parse_freddie_calendar_page(notes_text or "", year, "agency_issuance", "Freddie Mac", "Optional Reference Notes announcement"),
        *parse_freddie_calendar_page(bills_text or "", year, "agency_issuance", "Freddie Mac", "Optional Reference Bills auction"),
    ]


def build_fannie_calendar_events(start: date, end: date) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for day in daterange(start, end):
        if day.weekday() == 2 and is_business_day(day):
            events.append(event_record(
                day,
                "agency_issuance",
                "Fannie Mae",
                "Optional Benchmark Bills auction",
                "Fannie Mae Benchmark Securities calendar rule",
                FANNIE_DEBT_SECURITIES_URL,
            ))
    for year, dates in FANNIE_BENCHMARK_NOTE_DATES.items():
        for date_text in dates:
            day = datetime.strptime(date_text, "%Y-%m-%d").date()
            if start <= day <= end:
                events.append(event_record(
                    day,
                    "agency_issuance",
                    "Fannie Mae",
                    "Benchmark Notes announcement",
                    "Fannie Mae Benchmark Securities issuance calendar",
                    FANNIE_DEBT_SECURITIES_URL,
                ))
    return events


def build_agency_issuance_events(start: date, end: date) -> list[dict[str, Any]]:
    events = build_fannie_calendar_events(start, end)
    for year in range(start.year, end.year + 1):
        events.extend(load_freddie_calendar_events(year))
    return [row for row in events if start.isoformat() <= row["date"] <= end.isoformat()]


def grouped_treasury_events(treasury: pd.DataFrame, start: date, end: date) -> list[dict[str, Any]]:
    if treasury.empty:
        return []
    frame = treasury.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"])
    frame = frame.loc[(frame["date"].dt.date >= start) & (frame["date"].dt.date <= end)].copy()
    if frame.empty:
        return []
    grouped = (
        frame.groupby([frame["date"].dt.date, "security_type"], dropna=False)["amount_bn"]
        .sum()
        .reset_index(name="amount_bn")
    )
    events = []
    for _, row in grouped.iterrows():
        security_type = str(row.get("security_type") or "securities")
        events.append(event_record(
            row["date"],
            "treasury_issuance",
            "U.S. Treasury",
            f"{security_type} issue settlement",
            "Treasury Fiscal Data Auctions Query",
            "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/",
            row["amount_bn"],
        ))
    return events


def build_calendar_daily_records(events: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    by_date: dict[str, dict[str, float]] = {}
    for day in daterange(start, end):
        by_date[day.isoformat()] = {
            "date": day.isoformat(),
            "treasury_issuance_bn": 0.0,
            "agency_event_count": 0.0,
            "gse_cash_event_count": 0.0,
        }
    for event in events:
        row = by_date.get(str(event["date"]))
        if row is None:
            continue
        if event["kind"] == "treasury_issuance":
            row["treasury_issuance_bn"] += float(event.get("amount_bn") or 0.0)
        elif event["kind"] == "agency_issuance":
            row["agency_event_count"] += 1.0
        elif event["kind"] == "gse_cash_flow":
            row["gse_cash_event_count"] += 1.0
    return [
        {
            "date": row["date"],
            "treasury_issuance_bn": round(row["treasury_issuance_bn"], 3),
            "agency_event_count": int(row["agency_event_count"]),
            "gse_cash_event_count": int(row["gse_cash_event_count"]),
            "total_event_count": int(row["agency_event_count"] + row["gse_cash_event_count"]),
        }
        for row in by_date.values()
    ]


def build_funding_calendar_payload(as_of: str | pd.Timestamp | None = None) -> dict[str, Any]:
    anchor = pd.to_datetime(as_of if as_of is not None else datetime.now(UTC).date(), errors="coerce")
    if pd.isna(anchor):
        anchor = pd.Timestamp(datetime.now(UTC).date())
    start = (anchor - pd.Timedelta(days=45)).date()
    end = (anchor + pd.Timedelta(days=45)).date()
    treasury = load_treasury_issuance_frame(pd.Timestamp(start), pd.Timestamp(end))
    events = [
        *grouped_treasury_events(treasury, start, end),
        *build_agency_issuance_events(start, end),
        *build_gse_cash_flow_events(start, end),
    ]
    events = sorted(events, key=lambda row: (row["date"], row["kind"], row["issuer"], row["label"]))
    upcoming_end = (anchor + pd.Timedelta(days=14)).date().isoformat()
    anchor_text = anchor.date().isoformat()
    upcoming = [row for row in events if anchor_text <= row["date"] <= upcoming_end]
    return {
        "as_of": anchor_text,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "events": events,
        "daily": build_calendar_daily_records(events, start, end),
        "upcoming": upcoming[:24],
        "source_notes": [
            "Treasury issue-date amounts come from the Treasury Fiscal Data Auctions Query API.",
            "Agency issuance dates are scheduled/optional Fannie Mae and Freddie Mac debt calendar events; no dollar amount is inferred.",
            "GSE cash-flow dates are rule-based Fannie Mae and Freddie Mac P&I remittance/draft dates; no dollar amount is inferred.",
        ],
    }


def normalize_report_url(url: str) -> str:
    return urllib.parse.quote(unescape(str(url).strip()), safe=":/?&=%")


def fetch_url_bytes(url: str, timeout: int = 60) -> bytes:
    normalized = normalize_report_url(url)
    headers = {"User-Agent": "Mozilla/5.0 COT dashboard builder"}
    if requests is not None:
        response = requests.get(normalized, timeout=timeout, headers=headers)
        response.raise_for_status()
        return response.content
    request = urllib.request.Request(normalized, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_url_text(url: str, timeout: int = 60) -> str:
    return fetch_url_bytes(url, timeout=timeout).decode("utf-8", errors="replace")


def discover_frtib_tsp_report_urls() -> list[str]:
    sitemap = fetch_url_text(FRTIB_SITEMAP_URL, timeout=60)
    urls = []
    for raw_url in re.findall(r"<loc>(.*?)</loc>", sitemap, flags=re.IGNORECASE):
        url = normalize_report_url(raw_url)
        lower = url.lower()
        if lower.endswith(".pdf") and "investment" in lower and "program" in lower and "review" in lower:
            urls.append(url)
    return sorted(set(urls))


def parse_money_text(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"n/a", "na"}:
        return None
    negative = "(" in text and ")" in text
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned:
        return None
    parsed = float(cleaned)
    return -parsed if negative else parsed


def tsp_report_month_from_url(url: str) -> pd.Timestamp | None:
    match = re.search(r"/pdf/minutes/(\d{4})/([A-Za-z]+)/", urllib.parse.unquote(url))
    if not match:
        return None
    year = int(match.group(1))
    month_name = match.group(2)
    month_aliases = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "sept": 9,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = month_aliases.get(month_name.lower())
    if month is None:
        return None
    return pd.Timestamp(year=year, month=month, day=1)


def parse_frtib_tsp_report(url: str) -> dict[str, Any]:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed; cannot parse FRTIB TSP PDFs.")

    data = fetch_url_bytes(url, timeout=60)
    reader = PdfReader(io.BytesIO(data))
    text = " ".join((page.extract_text() or "") for page in reader.pages)
    text = re.sub(r"\s+", " ", text)

    date_match = re.search(r"Asset Allocation as of ([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not date_match:
        date_match = re.search(r"\bas of ([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not date_match:
        raise ValueError("No asset-allocation date found in FRTIB report.")
    report_date = pd.to_datetime(date_match.group(1), errors="raise")

    row: dict[str, Any] = {
        "date": report_date,
        "source_url": normalize_report_url(url),
    }

    def parse_asset_row(label: str, key: str, required: bool = True) -> None:
        pattern = (
            rf"{re.escape(label)}\s+\$([0-9,.]+)\s+([0-9.]+)%\s+"
            rf"(?:\$([0-9,.]+)\s+([0-9.]+)%|n/a\s+n/a)"
        )
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            if required:
                raise ValueError(f"No {label} asset row found in FRTIB report.")
            return
        row[f"{key}_assets"] = parse_money_text(match.group(1))
        row[f"{key}_share"] = float(match.group(2))
        if match.group(3):
            row[f"{key}_underlying_assets"] = parse_money_text(match.group(3))
            row[f"{key}_underlying_share"] = float(match.group(4))

    for label, key in (
        ("G Fund", "g_fund"),
        ("F Fund", "f_fund"),
        ("C Fund", "c_fund"),
        ("S Fund", "s_fund"),
        ("I Fund", "i_fund"),
        ("Total", "total"),
    ):
        parse_asset_row(label, key, required=True)
    parse_asset_row("L Funds", "l_fund", required=False)
    parse_asset_row("MFW", "mfw", required=False)

    start = text.find("Interfund Transfer Activity")
    if start >= 0:
        block = text[start:start + 1000]
        block = block.split("G Fund F Fund")[0]
        transfers = re.findall(r"\(?\$[0-9,]+\)?", block)
        transfer_keys = (
            "g_fund_ift_m",
            "f_fund_ift_m",
            "c_fund_ift_m",
            "s_fund_ift_m",
            "i_fund_ift_m",
            "l_fund_ift_m",
            "mfw_ift_m",
        )
        for key, value in zip(transfer_keys, transfers[:len(transfer_keys)]):
            row[key] = parse_money_text(value)

    return row


def load_cached_tsp_reports() -> pd.DataFrame:
    if not FRTIB_TSP_CACHE.exists():
        return pd.DataFrame()
    df = pd.read_csv(FRTIB_TSP_CACHE)
    if df.empty or "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)


def finalize_tsp_reports(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out = out.dropna(subset=["date"]).sort_values("date")
    out = out.drop_duplicates("date", keep="last").reset_index(drop=True)

    numeric_columns = [column for column in out.columns if column not in {"date", "source_url"}]
    for column in numeric_columns:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    for column in (
        "g_fund_assets",
        "f_fund_assets",
        "c_fund_assets",
        "s_fund_assets",
        "i_fund_assets",
        "g_fund_share",
        "f_fund_share",
        "c_fund_share",
        "s_fund_share",
        "i_fund_share",
        "g_fund_ift_m",
        "f_fund_ift_m",
        "c_fund_ift_m",
        "s_fund_ift_m",
        "i_fund_ift_m",
    ):
        if column not in out.columns:
            out[column] = pd.NA

    out["equity_assets"] = out[["c_fund_assets", "s_fund_assets", "i_fund_assets"]].sum(axis=1, min_count=1)
    out["equity_share"] = out[["c_fund_share", "s_fund_share", "i_fund_share"]].sum(axis=1, min_count=1)
    out["safe_assets"] = out[["g_fund_assets", "f_fund_assets"]].sum(axis=1, min_count=1)
    out["safe_share"] = out[["g_fund_share", "f_fund_share"]].sum(axis=1, min_count=1)
    out["g_fund_1m_change"] = out["g_fund_share"].diff()
    out["equity_1m_change"] = out["equity_share"].diff()
    out["equity_ift_m"] = out[["c_fund_ift_m", "s_fund_ift_m", "i_fund_ift_m"]].sum(axis=1, min_count=1)
    out["safe_ift_m"] = out[["g_fund_ift_m", "f_fund_ift_m"]].sum(axis=1, min_count=1)
    out["retirement_flow_signal"] = out["equity_ift_m"] - out["g_fund_ift_m"]
    out["score_retirement_proxy"] = rolling_z_score_to_score(
        out["retirement_flow_signal"],
        window=24,
        min_periods=12,
    )
    return out


def write_tsp_cache(df: pd.DataFrame) -> None:
    if df.empty:
        return
    FRTIB_TSP_CACHE.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out.to_csv(FRTIB_TSP_CACHE, index=False)


def load_tsp_retirement_proxy_frame() -> pd.DataFrame:
    cached = load_cached_tsp_reports()
    try:
        urls = discover_frtib_tsp_report_urls()
    except Exception:
        return finalize_tsp_reports(cached)

    known_urls = set(cached.get("source_url", pd.Series(dtype="object")).dropna().astype(str))
    missing_urls = [url for url in urls if url not in known_urls]
    if not cached.empty and missing_urls:
        latest_cached_date = pd.to_datetime(cached["date"], errors="coerce").max()
        cutoff = latest_cached_date - pd.DateOffset(months=3)
        missing_urls = [
            url for url in missing_urls
            if (tsp_report_month_from_url(url) is None or tsp_report_month_from_url(url) >= cutoff)
        ]

    parsed_rows: list[dict[str, Any]] = []
    if missing_urls:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(parse_frtib_tsp_report, url): url for url in missing_urls}
            for future in as_completed(futures):
                try:
                    parsed_rows.append(future.result())
                except Exception:
                    continue

    parsed = pd.DataFrame(parsed_rows)
    combined = pd.concat([cached, parsed], ignore_index=True) if not parsed.empty else cached
    finalized = finalize_tsp_reports(combined)
    if not parsed.empty:
        write_tsp_cache(finalized)
    return finalized


def tsp_macro_frame(tsp_reports: pd.DataFrame) -> pd.DataFrame:
    if tsp_reports.empty:
        return pd.DataFrame(columns=["date", *TSP_MACRO_COLUMNS, "score_retirement_proxy"])

    rename_map = {
        "total_assets": "tsp_total_assets",
        "g_fund_assets": "tsp_g_fund_assets",
        "f_fund_assets": "tsp_f_fund_assets",
        "c_fund_assets": "tsp_c_fund_assets",
        "s_fund_assets": "tsp_s_fund_assets",
        "i_fund_assets": "tsp_i_fund_assets",
        "l_fund_assets": "tsp_l_fund_assets",
        "g_fund_share": "tsp_g_fund_share",
        "equity_share": "tsp_equity_share",
        "g_fund_1m_change": "tsp_g_fund_1m_change",
        "equity_1m_change": "tsp_equity_1m_change",
        "g_fund_ift_m": "tsp_g_fund_ift_m",
        "f_fund_ift_m": "tsp_f_fund_ift_m",
        "c_fund_ift_m": "tsp_c_fund_ift_m",
        "s_fund_ift_m": "tsp_s_fund_ift_m",
        "i_fund_ift_m": "tsp_i_fund_ift_m",
        "l_fund_ift_m": "tsp_l_fund_ift_m",
        "equity_ift_m": "tsp_equity_ift_m",
    }
    keep = ["date", *rename_map.keys(), "retirement_flow_signal", "score_retirement_proxy"]
    out = tsp_reports[[column for column in keep if column in tsp_reports.columns]].copy()
    out = out.rename(columns=rename_map)
    for column in [*TSP_MACRO_COLUMNS, "score_retirement_proxy"]:
        if column not in out.columns:
            out[column] = pd.NA
    return out[["date", *TSP_MACRO_COLUMNS, "score_retirement_proxy"]].sort_values("date").reset_index(drop=True)


def build_retirement_proxy_payload(tsp_reports: pd.DataFrame) -> dict[str, Any]:
    if tsp_reports.empty:
        return {
            "available": False,
            "source": "FRTIB monthly Investment Program Review PDFs",
            "sitemap_url": FRTIB_SITEMAP_URL,
            "records": [],
            "latest": {},
        }

    columns = [
        "date",
        "source_url",
        "g_fund_assets",
        "f_fund_assets",
        "c_fund_assets",
        "s_fund_assets",
        "i_fund_assets",
        "l_fund_assets",
        "total_assets",
        "g_fund_share",
        "equity_share",
        "g_fund_1m_change",
        "equity_1m_change",
        "g_fund_ift_m",
        "f_fund_ift_m",
        "c_fund_ift_m",
        "s_fund_ift_m",
        "i_fund_ift_m",
        "l_fund_ift_m",
        "equity_ift_m",
        "retirement_flow_signal",
        "score_retirement_proxy",
    ]
    export = tsp_reports[[column for column in columns if column in tsp_reports.columns]].copy()
    export["date"] = pd.to_datetime(export["date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for column in export.columns:
        if column in {"date", "source_url"}:
            continue
        export[column] = pd.to_numeric(export[column], errors="coerce").round(3)
    return {
        "available": True,
        "source": "FRTIB monthly Investment Program Review PDFs",
        "sitemap_url": FRTIB_SITEMAP_URL,
        "cache_path": str(FRTIB_TSP_CACHE),
        "records": records(export),
        "latest": records(export.tail(1))[0],
    }


def macro_forward_returns(df: pd.DataFrame, column: str, steps: int) -> pd.Series:
    values = pd.to_numeric(df[column], errors="coerce")
    return (values.shift(-steps) / values - 1.0) * 100.0


def build_macro_base_frame(tsp_reports: pd.DataFrame | None = None) -> pd.DataFrame:
    frames = {column: load_macro_series(column, spec) for column, spec in MACRO_SERIES.items()}
    date_parts = [frame["date"] for frame in frames.values() if not frame.empty]
    if not date_parts:
        return pd.DataFrame(columns=MACRO_COLUMNS)
    date_values = pd.concat(date_parts, ignore_index=True)
    # Scheduled policy/calendar rows can extend beyond today. They belong in
    # the forward calendar, not in the current observed regime time series.
    as_of_today = pd.Timestamp(datetime.now(UTC).date())
    date_values = date_values[pd.to_datetime(date_values, errors="coerce") <= as_of_today]
    if date_values.empty:
        return pd.DataFrame(columns=MACRO_COLUMNS)

    base = pd.DataFrame({"date": sorted(date_values.dropna().unique())})
    for column, frame in frames.items():
        if frame.empty:
            base[column] = pd.NA
            continue
        base = pd.merge_asof(
            base.sort_values("date"),
            frame.sort_values("date"),
            on="date",
            direction="backward",
        )

    required = [column for column, spec in MACRO_SERIES.items() if spec.get("required", True)]
    base = base.dropna(subset=required).reset_index(drop=True)
    if base.empty:
        return base

    tsp_frame = tsp_macro_frame(tsp_reports if tsp_reports is not None else load_tsp_retirement_proxy_frame())
    if not tsp_frame.empty:
        base = pd.merge_asof(
            base.sort_values("date"),
            tsp_frame.sort_values("date"),
            on="date",
            direction="backward",
        )
    for column in [*TSP_MACRO_COLUMNS, "score_retirement_proxy"]:
        if column not in base.columns:
            base[column] = pd.NA

    base["net_liquidity"] = base["walcl"] - base["tga"] - base["rrp"]
    base["slr_balance_sheet_load"] = base["bank_reserves"] + base["bank_treasury_agency"]
    base["reserves_to_bank_assets_pct"] = (base["bank_reserves"] / base["bank_assets"] * 100.0).where(base["bank_assets"] != 0)
    base["sofr_iorb_spread"] = base["sofr"] - base["iorb"]
    base["effr_iorb_spread"] = base["effr"] - base["iorb"]
    base["yield_curve_10y_2y"] = base["nominal_yield_10y"] - base["nominal_yield_2y"]
    base["yield_curve_10y_3m"] = base["nominal_yield_10y"] - base["nominal_yield_3m"]
    base["yield_curve_30y_10y"] = base["nominal_yield_30y"] - base["nominal_yield_10y"]

    treasury = load_treasury_issuance_frame(base["date"].min() - pd.Timedelta(days=35), base["date"].max() + pd.Timedelta(days=35))
    if not treasury.empty:
        daily_issuance = treasury.groupby("date", as_index=False)["amount_bn"].sum().sort_values("date")
        for label, days, forward in (
            ("treasury_issuance_7d", 7, False),
            ("treasury_issuance_28d", 28, False),
            ("treasury_issuance_next_7d", 7, True),
        ):
            values = []
            for current_date in base["date"]:
                if forward:
                    mask = (daily_issuance["date"] > current_date) & (daily_issuance["date"] <= current_date + pd.Timedelta(days=days))
                else:
                    mask = (daily_issuance["date"] <= current_date) & (daily_issuance["date"] > current_date - pd.Timedelta(days=days))
                values.append(round(float(daily_issuance.loc[mask, "amount_bn"].sum()), 3))
            base[label] = values
    else:
        base["treasury_issuance_7d"] = pd.NA
        base["treasury_issuance_28d"] = pd.NA
        base["treasury_issuance_next_7d"] = pd.NA

    for column in (
        "net_liquidity",
        "bank_reserves",
        "bank_treasury_agency",
        "slr_balance_sheet_load",
        "reserves_to_bank_assets_pct",
        "tga",
        "rrp",
        "sofr",
        "effr",
        "iorb",
        "sofr_iorb_spread",
        "effr_iorb_spread",
        "real_yield_10y",
        "real_yield_5y",
        "nominal_yield_10y",
        "nominal_yield_2y",
        "nominal_yield_3m",
        "nominal_yield_30y",
        "yield_curve_10y_2y",
        "yield_curve_10y_3m",
        "yield_curve_30y_10y",
        "hy_oas",
        "ig_oas",
        "dollar_index",
        "vix",
    ):
        base[f"{column}_4w_change"] = calendar_delta(base, column, 28)
        base[f"{column}_13w_change"] = calendar_delta(base, column, 91)
    base = base.rename(columns={
        "real_yield_10y_4w_change": "real_yield_4w_change",
        "real_yield_10y_13w_change": "real_yield_13w_change",
        "real_yield_5y_4w_change": "real_yield_5y_4w_change",
        "hy_oas_4w_change": "hy_oas_4w_change",
        "ig_oas_4w_change": "ig_oas_4w_change",
        "dollar_index_4w_change": "dollar_4w_change",
        "dollar_index_13w_change": "dollar_13w_change",
        "reserves_to_bank_assets_pct_4w_change": "reserves_to_bank_assets_4w_change",
    })
    base["sp500_13w_change_pct"] = calendar_pct_change(base, "sp500", 91)
    base["nasdaq_13w_change_pct"] = calendar_pct_change(base, "nasdaq", 91)
    base["sp500_forward_5d"] = macro_forward_returns(base, "sp500", 5)
    base["sp500_forward_10d"] = macro_forward_returns(base, "sp500", 10)
    base["sp500_forward_20d"] = macro_forward_returns(base, "sp500", 20)
    base["sp500_forward_60d"] = macro_forward_returns(base, "sp500", 60)
    base["nasdaq_forward_5d"] = macro_forward_returns(base, "nasdaq", 5)
    base["nasdaq_forward_10d"] = macro_forward_returns(base, "nasdaq", 10)
    base["nasdaq_forward_20d"] = macro_forward_returns(base, "nasdaq", 20)
    base["nasdaq_forward_60d"] = macro_forward_returns(base, "nasdaq", 60)
    return base


def score_macro_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["score_net_liquidity"] = rolling_z_score_to_score(out["net_liquidity_4w_change"])
    out["score_bank_reserves"] = rolling_z_score_to_score(out["bank_reserves_4w_change"])
    out["score_rrp"] = rolling_z_score_to_score(-out["rrp_4w_change"])
    out["score_tga"] = rolling_z_score_to_score(-out["tga_4w_change"])
    repo_pressure = pd.to_numeric(out["sofr_iorb_spread"], errors="coerce") + (
        pd.to_numeric(out["sofr_iorb_spread_4w_change"], errors="coerce") * 0.5
    )
    if "effr_iorb_spread" in out.columns:
        repo_pressure = repo_pressure.fillna(0) + (
            pd.to_numeric(out["effr_iorb_spread"], errors="coerce").fillna(0) * 0.5
        )
    out["score_repo_spread"] = rolling_z_score_to_score(-repo_pressure)
    out["score_slr_load"] = rolling_z_score_to_score(-out["slr_balance_sheet_load_4w_change"])
    real_yield_pressure = pd.to_numeric(out["real_yield_4w_change"], errors="coerce")
    if "real_yield_5y_4w_change" in out.columns:
        real_yield_pressure = real_yield_pressure.fillna(0) + (
            pd.to_numeric(out["real_yield_5y_4w_change"], errors="coerce").fillna(0) * 0.5
        )
    out["score_real_yield"] = rolling_z_score_to_score(-real_yield_pressure)
    credit_pressure = pd.to_numeric(out["hy_oas_4w_change"], errors="coerce")
    if "ig_oas_4w_change" in out.columns:
        credit_pressure = credit_pressure.fillna(0) + pd.to_numeric(out["ig_oas_4w_change"], errors="coerce").fillna(0) * 0.5
    out["score_credit"] = rolling_z_score_to_score(-credit_pressure)
    out["score_dollar"] = rolling_z_score_to_score(-out["dollar_4w_change"])
    out["score_vix"] = rolling_z_score_to_score(-out["vix_4w_change"])
    out["score_market_trend"] = rolling_z_score_to_score(out["sp500_13w_change_pct"])
    if "score_retirement_proxy" in out.columns:
        out["score_retirement_proxy"] = pd.to_numeric(out["score_retirement_proxy"], errors="coerce").fillna(50.0)
    else:
        out["score_retirement_proxy"] = 50.0

    next_7d = pd.to_numeric(out["treasury_issuance_next_7d"], errors="coerce")
    trailing_28d = pd.to_numeric(out["treasury_issuance_28d"], errors="coerce")
    supply_pressure = ((next_7d - 175.0) / 325.0).clip(-0.6, 1.0).fillna(0.0)
    supply_pressure += ((trailing_28d - 900.0) / 1500.0).clip(-0.4, 0.8).fillna(0.0)
    out["score_treasury_supply"] = (50.0 - supply_pressure * 28.0).clip(0.0, 100.0)
    out["score_treasury_supply"] = out["score_treasury_supply"].where(next_7d.notna() | trailing_28d.notna())

    # Dedicated Fed/bank plumbing read. This intentionally excludes market-price
    # confirmation factors (rates, credit, dollar, and VIX) used by the broader
    # composite regime. The weights are the normalized core-liquidity and
    # money-market-plumbing weights from the unified model (48 points total).
    plumbing_weighted = (
        26.0 * pd.to_numeric(out["score_net_liquidity"], errors="coerce").fillna(50.0)
        + 10.0 * pd.to_numeric(out["score_bank_reserves"], errors="coerce").fillna(50.0)
        + 8.0 * pd.to_numeric(out["score_repo_spread"], errors="coerce").fillna(50.0)
        + 4.0 * pd.to_numeric(out["score_slr_load"], errors="coerce").fillna(50.0)
    )
    out["liquidity_plumbing_score"] = (plumbing_weighted / 48.0).clip(0.0, 100.0)

    weighted = pd.Series(0.0, index=out.index)
    for factor in MACRO_SCORE_FACTORS:
        weighted += float(factor["weight"]) * pd.to_numeric(out[factor["score_col"]], errors="coerce").fillna(50.0)
    raw_score = weighted / 100.0
    out["credit_override"] = pd.to_numeric(out["hy_oas_4w_change"], errors="coerce") > 0.50
    out["liquidity_score"] = raw_score.where(~out["credit_override"], raw_score.clip(upper=55.0)).clip(0, 100)
    out["regime_label"] = out["liquidity_score"].apply(lambda value: macro_regime_label(float(value)) if pd.notna(value) else "n/a")
    return out


def macro_bucket_rows() -> list[dict[str, Any]]:
    return [
        {"key": "risk_off", "label": "0-30 Risk-off", "low": 0, "high": 30},
        {"key": "defensive", "label": "30-45 Defensive", "low": 30, "high": 45},
        {"key": "neutral", "label": "45-55 Neutral", "low": 45, "high": 55},
        {"key": "supportive", "label": "55-70 Supportive", "low": 55, "high": 70},
        {"key": "strong_risk_on", "label": "70-100 Strong risk-on", "low": 70, "high": 100.0001},
    ]


def bucket_mask_for_score(scores: pd.Series, bucket: dict[str, Any]) -> pd.Series:
    low = float(bucket["low"])
    high = float(bucket["high"])
    if low == 0:
        return (scores >= low) & (scores <= high)
    return (scores > low) & (scores <= high)


def build_macro_backtest(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"buckets": macro_bucket_rows(), "rows": []}

    rows: list[dict[str, Any]] = []
    markets = [
        ("sp500", "S&P 500"),
        ("nasdaq", "Nasdaq-100"),
    ]
    for market, label in markets:
        for horizon in (20, 60):
            col = f"{market}_forward_{horizon}d"
            for bucket in macro_bucket_rows():
                mask = bucket_mask_for_score(pd.to_numeric(df["liquidity_score"], errors="coerce"), bucket)
                values = pd.to_numeric(df.loc[mask, col], errors="coerce").dropna()
                rows.append({
                    "market": market,
                    "market_label": label,
                    "horizon": f"{horizon}d",
                    "bucket": bucket["label"],
                    "observations": int(values.shape[0]),
                    "avg_forward_return": round(float(values.mean()), 2) if not values.empty else None,
                    "median_forward_return": round(float(values.median()), 2) if not values.empty else None,
                    "win_rate": round(float((values > 0).mean() * 100), 1) if not values.empty else None,
                    "worst_forward_return": round(float(values.min()), 2) if not values.empty else None,
                })
    return {"buckets": macro_bucket_rows(), "rows": rows}


def macro_driver_rows(latest: dict[str, Any]) -> list[dict[str, Any]]:
    drivers = []
    for factor in MACRO_SCORE_FACTORS:
        score = latest.get(str(factor["score_col"]))
        if score is None:
            score = 50.0
        score_value = float(score)
        contribution = float(factor["weight"]) * (score_value - 50.0) / 50.0
        delta_col = factor.get("delta_col")
        delta = latest.get(str(delta_col)) if delta_col else None
        drivers.append({
            "key": factor["key"],
            "label": factor["label"],
            "weight": factor["weight"],
            "score": round(score_value, 1),
            "contribution": round(contribution, 2),
            "delta": round(float(delta), 3) if delta is not None and pd.notna(delta) else None,
            "delta_label": factor.get("delta_label", "4w"),
            "unit": factor["unit"],
        })
    return sorted(drivers, key=lambda row: abs(float(row["contribution"])), reverse=True)


def build_macro_alerts(df: pd.DataFrame) -> list[dict[str, Any]]:
    if df.empty:
        return []
    latest = df.iloc[-1]
    previous = df.iloc[-2] if len(df) >= 2 else latest

    def alert(label: str, actual: Any, threshold: str, triggered: bool, severity: str, unit: str, detail: str) -> dict[str, Any]:
        return {
            "label": label,
            "actual": round(float(actual), 3) if actual is not None and pd.notna(actual) else None,
            "threshold": threshold,
            "triggered": bool(triggered),
            "severity": severity,
            "unit": unit,
            "detail": detail,
        }

    score = float(latest["liquidity_score"])
    prev_score = float(previous["liquidity_score"])
    return [
        alert(
            "Net liquidity drawdown",
            latest.get("net_liquidity_4w_change"),
            "< -$150bn over 4w",
            latest.get("net_liquidity_4w_change") < -150,
            "red",
            "usd_bn",
            "Fed net liquidity is falling fast enough to become a market headwind.",
        ),
        alert(
            "TGA rebuild drain",
            latest.get("tga_4w_change"),
            "> +$150bn over 4w",
            latest.get("tga_4w_change") > 150,
            "amber",
            "usd_bn",
            "Treasury cash rising drains reserves/liquidity from the private sector.",
        ),
        alert(
            "Reserve drain",
            latest.get("bank_reserves_4w_change"),
            "< -$200bn over 4w",
            latest.get("bank_reserves_4w_change") < -200,
            "red",
            "usd_bn",
            "Fast reserve declines can signal funding pressure.",
        ),
        alert(
            "Repo funding pressure",
            latest.get("sofr_iorb_spread"),
            "> +10 bps",
            pd.notna(latest.get("sofr_iorb_spread")) and latest.get("sofr_iorb_spread") > 0.10,
            "red",
            "pp",
            "SOFR trading above IORB can signal repo cash scarcity or balance-sheet pressure.",
        ),
        alert(
            "Repo liquidity loose",
            latest.get("sofr_iorb_spread"),
            "< -10 bps",
            pd.notna(latest.get("sofr_iorb_spread")) and latest.get("sofr_iorb_spread") < -0.10,
            "green",
            "pp",
            "SOFR below IORB points to abundant cash in secured funding markets.",
        ),
        alert(
            "Repo normalization jump",
            latest.get("sofr_iorb_spread_4w_change"),
            "> +10 bps over 4w",
            pd.notna(latest.get("sofr_iorb_spread_4w_change")) and latest.get("sofr_iorb_spread_4w_change") > 0.10,
            "amber",
            "pp",
            "A fast rise in SOFR versus IORB shows funding conditions moving less loose.",
        ),
        alert(
            "SLR load rising",
            latest.get("slr_balance_sheet_load_4w_change"),
            "> +$150bn over 4w",
            pd.notna(latest.get("slr_balance_sheet_load_4w_change")) and latest.get("slr_balance_sheet_load_4w_change") > 150,
            "amber",
            "usd_bn",
            "Rising reserves plus bank Treasury/agency holdings can increase leverage-ratio balance-sheet load.",
        ),
        alert(
            "Treasury settlement wall",
            latest.get("treasury_issuance_next_7d"),
            "> $250bn next 7d",
            pd.notna(latest.get("treasury_issuance_next_7d")) and latest.get("treasury_issuance_next_7d") > 250,
            "amber",
            "usd_bn",
            "Large Treasury settlement windows can absorb cash from money markets.",
        ),
        alert(
            "HY spread widening",
            latest.get("hy_oas_4w_change"),
            "> +50 bps over 4w",
            latest.get("hy_oas_4w_change") > 0.50,
            "red",
            "pp",
            "Credit widening caps the score at neutral even if liquidity is improving.",
        ),
        alert(
            "Real-yield shock",
            latest.get("real_yield_4w_change"),
            "> +30 bps over 4w",
            latest.get("real_yield_4w_change") > 0.30,
            "amber",
            "pp",
            "Rising real yields pressure long-duration/growth equities.",
        ),
        alert(
            "VIX stress",
            latest.get("vix"),
            "> 25",
            latest.get("vix") > 25,
            "amber",
            "index",
            "Higher volatility can force deleveraging and weaker dip-buying.",
        ),
        alert(
            "Score crossed below 45",
            score,
            "cross below 45",
            prev_score >= 45 and score < 45,
            "red",
            "score",
            "Regime moved from neutral/supportive into defensive.",
        ),
        alert(
            "Score crossed above 55",
            score,
            "cross above 55",
            prev_score <= 55 and score > 55,
            "green",
            "score",
            "Regime moved from neutral/defensive into supportive.",
        ),
    ]


def build_macro_prediction(latest: dict[str, Any], drivers: list[dict[str, Any]]) -> dict[str, Any]:
    score = float(latest.get("liquidity_score") or 50.0)
    regime = str(latest.get("regime_label") or macro_regime_label(score))
    negative = [row for row in drivers if float(row["contribution"]) < 0]
    positive = [row for row in drivers if float(row["contribution"]) > 0]
    confidence = "medium"
    if 45 <= score <= 55:
        confidence = "low"
    elif score >= 70 or score < 30:
        confidence = "high"
    if latest.get("credit_override"):
        confidence = "medium"

    if score >= 70:
        bias = "positive"
        implication = "Strong risk-on. Favor equities, high beta, Nasdaq, and crypto while credit remains calm."
    elif score >= 55:
        bias = "positive"
        implication = "Supportive. Buy-dip behavior is more likely to work if credit and VIX do not deteriorate."
    elif score >= 45:
        bias = "mixed"
        implication = "Mixed. Price action and earnings matter more than liquidity."
    elif score >= 30:
        bias = "negative"
        implication = "Defensive. Rallies are more vulnerable to fading."
    else:
        bias = "negative"
        implication = "Risk-off. Liquidity stress and drawdown risk are elevated."

    real_yield_delta = latest.get("real_yield_4w_change")
    best_asset = "Nasdaq / growth" if real_yield_delta is not None and pd.notna(real_yield_delta) and real_yield_delta < 0 and score >= 55 else "S&P 500 / broad risk"
    return {
        "current_regime": regime,
        "equity_bias_1m": bias,
        "confidence": confidence,
        "main_risk": negative[0]["label"] if negative else "No dominant macro headwind",
        "main_support": positive[0]["label"] if positive else "No dominant macro tailwind",
        "best_affected_asset": best_asset,
        "worst_scenario": "Credit spreads widen while the liquidity score drops below 45.",
        "trading_implication": implication,
    }


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def score_to_regime_points(score: Any) -> float | None:
    if score is None or not pd.notna(score):
        return None
    return round(clamp((float(score) - 50.0) / 25.0, -2.0, 2.0), 2)


def regime_points_label(points: float | None) -> str:
    if points is None:
        return "n/a"
    if points >= 1.5:
        return "Strongly supportive"
    if points >= 0.5:
        return "Supportive"
    if points > -0.5:
        return "Neutral / transition"
    if points > -1.5:
        return "Restrictive"
    return "Strongly restrictive"


def latest_score_value(latest: dict[str, Any], column: str) -> float | None:
    value = latest.get(column)
    if value is None or not pd.notna(value):
        return None
    return float(value)


def weighted_group_score(latest: dict[str, Any], items: list[tuple[str, float]]) -> float | None:
    total_weight = 0.0
    weighted = 0.0
    for column, weight in items:
        value = latest_score_value(latest, column)
        if value is None:
            continue
        total_weight += float(weight)
        weighted += float(weight) * value
    if total_weight == 0:
        return None
    return round(weighted / total_weight, 1)


def treasury_supply_score(latest: dict[str, Any]) -> float | None:
    next_7d = latest.get("treasury_issuance_next_7d")
    trailing_28d = latest.get("treasury_issuance_28d")
    if (next_7d is None or not pd.notna(next_7d)) and (trailing_28d is None or not pd.notna(trailing_28d)):
        return None
    pressure = 0.0
    if next_7d is not None and pd.notna(next_7d):
        pressure += clamp((float(next_7d) - 175.0) / 325.0, -0.6, 1.0)
    if trailing_28d is not None and pd.notna(trailing_28d):
        pressure += clamp((float(trailing_28d) - 900.0) / 1500.0, -0.4, 0.8)
    return round(clamp(50.0 - pressure * 28.0, 0.0, 100.0), 1)


def build_score_groups(latest: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [
        ("liquidity", "Core Fed Liquidity", 36, [("score_net_liquidity", 26.0), ("score_bank_reserves", 10.0)]),
        ("plumbing", "Money-Market Plumbing", 12, [("score_repo_spread", 8.0), ("score_slr_load", 4.0)]),
        ("treasury_supply", "Treasury Supply", 10, [("score_treasury_supply", 10.0)]),
        ("rates", "Rates", 14, [("score_real_yield", 14.0)]),
        ("credit", "Credit", 14, [("score_credit", 14.0)]),
        ("dollar", "Dollar", 8, [("score_dollar", 8.0)]),
        ("volatility", "Volatility", 6, [("score_vix", 6.0)]),
    ]
    groups = []
    for key, label, weight, items in specs:
        score = weighted_group_score(latest, items)
        points = score_to_regime_points(score)
        groups.append({
            "key": key,
            "label": label,
            "weight": weight,
            "score": score,
            "regime_points": points,
            "label_state": regime_points_label(points),
        })
    return groups


def build_confidence(
    latest: dict[str, Any],
    groups: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scores = [float(row["score"]) for row in groups if row.get("score") is not None and pd.notna(row.get("score"))]
    if not scores:
        return {"score": 0, "label": "n/a", "detail": "No component scores are available."}
    signed = [(score - 50.0) / 50.0 for score in scores]
    agreement = abs(sum(signed) / len(signed))
    conviction = sum(abs(value) for value in signed) / len(signed)
    triggered_penalty = sum(1 for row in alerts if row.get("triggered") and row.get("severity") in {"red", "amber"}) * 3
    freshness_rows = (freshness or {}).get("rows") or []
    freshness_penalty = min(
        30,
        sum(8 if row.get("status") == "missing" else 5 if row.get("status") == "stale" else 0 for row in freshness_rows),
    )
    confidence = int(round(
        clamp(35.0 + agreement * 45.0 + conviction * 20.0 - triggered_penalty - freshness_penalty, 20.0, 95.0)
    ))
    label = "high" if confidence >= 70 else "medium" if confidence >= 45 else "low"
    return {
        "score": confidence,
        "label": label,
        "agreement": round(agreement, 3),
        "conviction": round(conviction, 3),
        "freshness_penalty": freshness_penalty,
        "detail": "Higher when component scores point in the same direction; lower when drivers conflict, alerts fire, or sources are stale/missing.",
    }


def impulse_label(value: float | None) -> str:
    if value is None or not pd.notna(value):
        return "unknown"
    if value >= 100:
        return "supportive"
    if value >= 25:
        return "mildly supportive"
    if value > -25:
        return "neutral"
    if value > -100:
        return "mild tightening"
    return "tightening"


def build_forward_path(latest: dict[str, Any], drivers: list[dict[str, Any]]) -> dict[str, Any]:
    net_4w = float(latest.get("net_liquidity_4w_change") or 0.0)
    net_13w = float(latest.get("net_liquidity_13w_change") or 0.0)
    issuance_7d = float(latest.get("treasury_issuance_next_7d") or 0.0)
    issuance_28d = float(latest.get("treasury_issuance_28d") or 0.0)
    repo_spread = float(latest.get("sofr_iorb_spread") or 0.0)
    credit = float(latest.get("hy_oas_4w_change") or 0.0)

    one_week = net_4w / 4.0 - max(issuance_7d - 175.0, 0.0) * 0.12
    one_month = net_4w - max(issuance_28d - 900.0, 0.0) * 0.08
    three_month = net_13w - max(issuance_28d - 900.0, 0.0) * 0.12
    if repo_spread > 0.10:
        one_week -= 25
        one_month -= 50
    if credit > 0.50:
        one_month -= 75
        three_month -= 125

    horizons = [
        {
            "horizon": "1 week",
            "expected_liquidity_impulse_bn": round(one_week, 1),
            "state": impulse_label(one_week),
            "main_driver": "Treasury settlement load versus recent net-liquidity impulse",
        },
        {
            "horizon": "1 month",
            "expected_liquidity_impulse_bn": round(one_month, 1),
            "state": impulse_label(one_month),
            "main_driver": "4-week net liquidity, Treasury supply, repo spread, and credit confirmation",
        },
        {
            "horizon": "3 months",
            "expected_liquidity_impulse_bn": round(three_month, 1),
            "state": impulse_label(three_month),
            "main_driver": "13-week net-liquidity trend and sustained Treasury/credit pressure",
        },
    ]
    positive = [row["label"] for row in drivers if float(row["contribution"]) > 0][:4]
    negative = [row["label"] for row in drivers if float(row["contribution"]) < 0][:4]
    return {
        "horizons": horizons,
        "bullish_drivers": positive,
        "bearish_drivers": negative,
        "improves_if": [
            "SOFR and EFFR stay at or below IORB while credit spreads remain calm.",
            "TGA stops rebuilding or RRP/reserve dynamics offset Treasury settlement pressure.",
            "Real yields and the dollar stop rising while market breadth confirms the index trend.",
        ],
        "deteriorates_if": [
            "SOFR-IORB moves above +10 bps or rises quickly into Treasury settlement windows.",
            "Bank reserves fall more than $200bn over four weeks or HY OAS widens more than 50 bps.",
            "Net liquidity falls below the 45 score zone while COT positioning is crowded.",
        ],
        "release_risks": [
            "Weekly H.4.1 reserves/TGA/RRP update",
            "Treasury auction announcements and issue settlements",
            "CPI/FOMC repricing through real yields and the dollar",
            "Credit-spread widening that invalidates equity strength",
        ],
        "caveat": "These are liquidity-impulse proxies, not deterministic forecasts.",
    }


def build_historical_analogs(export: pd.DataFrame, latest: dict[str, Any], max_rows: int = 40) -> dict[str, Any]:
    score_cols = [
        "score_net_liquidity",
        "score_bank_reserves",
        "score_repo_spread",
        "score_slr_load",
        "score_real_yield",
        "score_credit",
        "score_dollar",
        "score_vix",
        "score_market_trend",
    ]
    available = [col for col in score_cols if col in export.columns and latest.get(col) is not None]
    if len(available) < 4:
        return {"available": False, "reason": "Not enough score dimensions for analog matching.", "rows": []}
    frame = export.copy()
    for col in available:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    latest_vector = pd.Series({col: float(latest[col]) for col in available})
    frame["analog_distance"] = ((frame[available] - latest_vector) ** 2).mean(axis=1) ** 0.5
    frame = frame.loc[pd.to_datetime(frame["date"], errors="coerce") < pd.to_datetime(latest.get("date"), errors="coerce")]
    analogs = frame.sort_values("analog_distance").head(max_rows)
    rows = []
    horizons = [
        ("1w", "5d"),
        ("2w", "10d"),
        ("1m", "20d"),
        ("3m", "60d"),
    ]
    for market, label in (("sp500", "S&P 500"), ("nasdaq", "Nasdaq-100")):
        for horizon_label, suffix in horizons:
            values = pd.to_numeric(analogs.get(f"{market}_forward_{suffix}"), errors="coerce").dropna()
            rows.append({
                "market": market,
                "market_label": label,
                "horizon": horizon_label,
                "observations": int(values.shape[0]),
                "avg_return_pct": round(float(values.mean()), 2) if not values.empty else None,
                "median_return_pct": round(float(values.median()), 2) if not values.empty else None,
                "hit_rate_pct": round(float((values > 0).mean() * 100), 1) if not values.empty else None,
            })
    closest = analogs[["date", "analog_distance", "liquidity_score", "regime_label"]].head(8).copy()
    return {
        "available": True,
        "method": "Nearest historical rows by component-score distance; excludes current row.",
        "dimensions": available,
        "closest": records(closest),
        "rows": rows,
    }


def build_data_freshness(
    df: pd.DataFrame,
    source_map: list[dict[str, Any]],
    calendar_payload: dict[str, Any],
    tsp_reports: pd.DataFrame | None = None,
) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    thresholds = {"daily": 5, "weekly": 14, "monthly": 45, "daily/scheduled": 5}
    rows = []
    for source in source_map:
        column = source.get("column")
        frequency = str(source.get("frequency") or "daily")
        last_date = None
        if column in MACRO_SERIES:
            raw_series = load_macro_series(str(column), MACRO_SERIES[str(column)])
            if not raw_series.empty:
                last_date = pd.to_datetime(raw_series["date"].max(), errors="coerce")
        elif column == "retirement_flow_signal" and tsp_reports is not None and not tsp_reports.empty:
            last_date = pd.to_datetime(tsp_reports["date"].max(), errors="coerce")
        elif column == "funding_calendar" and calendar_payload.get("as_of"):
            last_date = pd.to_datetime(calendar_payload.get("as_of"), errors="coerce")
        if last_date is None or pd.isna(last_date):
            age = None
            status = "missing"
        else:
            age = (today - last_date.date()).days
            status = "fresh" if age <= thresholds.get(frequency, 14) else "stale"
        rows.append({
            "column": column,
            "label": source.get("label"),
            "source": source.get("source"),
            "frequency": frequency,
            "last_date": last_date.strftime("%Y-%m-%d") if last_date is not None and pd.notna(last_date) else None,
            "age_days": age,
            "status": status,
        })
    stale = [row for row in rows if row["status"] in {"stale", "missing"}]
    return {
        "rows": rows,
        "stale_count": len(stale),
        "status": "warning" if stale else "fresh",
        "warning": f"{len(stale)} source(s) stale or missing." if stale else "All tracked sources are within freshness thresholds.",
    }


def build_macro_monitor() -> dict[str, Any]:
    tsp_reports = load_tsp_retirement_proxy_frame()
    retirement_proxy = build_retirement_proxy_payload(tsp_reports)
    df = score_macro_frame(build_macro_base_frame(tsp_reports))
    if df.empty:
        return {"available": False, "error": "No macro data was available from local/FRED CSV inputs."}

    export = df[MACRO_COLUMNS + [factor["score_col"] for factor in MACRO_SCORE_FACTORS]].copy()
    export["date"] = export["date"].dt.strftime("%Y-%m-%d")
    for column in export.columns:
        if column == "date" or column == "regime_label":
            continue
        if column == "credit_override":
            export[column] = export[column].astype(bool)
            continue
        export[column] = pd.to_numeric(export[column], errors="coerce").round(3)

    latest = records(export.tail(1))[0]
    drivers = macro_driver_rows(latest)
    source_map = [
        {
            "column": column,
            "label": spec["label"],
            "source": spec["source"],
            "frequency": spec["frequency"],
            "unit": spec["unit"],
            "use": spec["use"],
        }
        for column, spec in MACRO_SERIES.items()
    ]
    source_map.append({
        "column": "retirement_flow_signal",
        "label": "TSP participant allocations and interfund transfers",
        "source": "FRTIB Investment Program Review PDFs",
        "url": FRTIB_SITEMAP_URL,
        "frequency": "monthly",
        "unit": "USD mn / score",
        "use": "Retirement-flow proxy for cash/equity risk appetite",
    })
    source_map.append({
        "column": "funding_calendar",
        "label": "Treasury/GSE/agency funding calendar",
        "source": "Treasury Fiscal Data, Fannie Mae, Freddie Mac",
        "url": "https://fiscaldata.treasury.gov/datasets/treasury-securities-auctions-data/",
        "frequency": "daily/scheduled",
        "unit": "USD bn / event dates",
        "use": "Settlement and GSE cash-flow windows that can absorb or redistribute money-market cash",
    })
    funding_calendar = build_funding_calendar_payload(latest.get("date"))
    alerts = build_macro_alerts(export)
    score_groups = build_score_groups(latest)
    freshness = build_data_freshness(df, source_map, funding_calendar, tsp_reports)
    confidence = build_confidence(latest, score_groups, alerts, freshness)
    latest["macro_regime_score"] = score_to_regime_points(latest.get("liquidity_score"))
    latest["macro_regime_score_label"] = regime_points_label(latest.get("macro_regime_score"))
    latest["confidence_score"] = confidence["score"]
    latest["confidence_label"] = confidence["label"]
    forward_path = build_forward_path(latest, drivers)
    analogs = build_historical_analogs(export, latest)
    return {
        "available": True,
        "columns": MACRO_COLUMNS,
        "records": records(export[MACRO_COLUMNS]),
        "latest": latest,
        "retirement_proxy": retirement_proxy,
        "drivers": drivers,
        "positive_drivers": [row for row in drivers if row["contribution"] > 0][:3],
        "negative_drivers": [row for row in drivers if row["contribution"] < 0][:3],
        "weights": [
            {key: factor[key] for key in ("key", "label", "weight")}
            for factor in MACRO_SCORE_FACTORS
        ],
        "score_groups": score_groups,
        "confidence": confidence,
        "backtest": build_macro_backtest(export),
        "historical_analogs": analogs,
        "alerts": alerts,
        "prediction": build_macro_prediction(latest, drivers),
        "forward_path": forward_path,
        "source_map": source_map,
        "funding_calendar": funding_calendar,
        "freshness": freshness,
        "notes": [
            "Fed net liquidity is calculated in USD billions as WALCL/1000 - WDTGAL/1000 - RRPONTSYD.",
            "The unified score uses one reconciled 100% weighting: core Fed liquidity 36%, money-market plumbing 12%, Treasury supply 10%, rates 14%, credit 14%, dollar 8%, and volatility 6%.",
            "The dedicated liquidity-plumbing score normalizes only net liquidity (26), bank reserves (10), repo stress (8), and SLR load (4) to 0-100; it excludes market-price confirmation factors.",
            "TGA and RRP remain visible as net-liquidity components but are not separately reweighted because they are already embedded in WALCL - TGA - RRP.",
            "Index price trend, COT positioning, and retirement flows are confirmation layers; none can change the unified liquidity score.",
            "SOFR is pulled from OFR's open STFM API and IORB from the Federal Reserve DDP policy-rates package; SOFR - IORB is the repo funding-pressure spread.",
            "SLR balance-sheet load is proxied as bank reserves plus bank Treasury/agency securities; it is an observable proxy, not a legal capital calculation.",
            "Treasury issuance amounts use Fiscal Data issue-date offering amounts; agency/GSE calendar entries are scheduled dates without inferred dollar amounts.",
            "Each factor score maps a rolling 1-year z-score to 0-100, with bearish factors inverted.",
            "The TSP retirement-flow proxy is automatically parsed from FRTIB monthly Investment Program Review PDFs; the CSV upload remains an override for the panel.",
            "If HY OAS widens more than 50 bps over 4 weeks, the final score is capped at neutral.",
        ],
    }


def as_dataframe(record_list: list[dict[str, Any]], value_col: str) -> pd.DataFrame:
    df = pd.DataFrame(record_list)
    if df.empty:
        return pd.DataFrame(columns=["date", value_col])
    out = pd.DataFrame({
        "date": pd.to_datetime(df["date"], errors="coerce"),
        value_col: pd.to_numeric(df[value_col], errors="coerce"),
    }).dropna()
    return out.sort_values("date").reset_index(drop=True)


def percentile_rank(values: pd.Series, latest_value: float) -> float | None:
    clean = values.dropna().sort_values()
    if clean.empty or not pd.notna(latest_value):
        return None
    less = int((clean < latest_value).sum())
    equal = int((clean == latest_value).sum())
    avg_rank = ((less + 1) + (less + max(equal, 1))) / 2
    return float(avg_rank / len(clean) * 100)


def percentile_bucket(percentile: float | None) -> dict[str, str] | None:
    if percentile is None:
        return None
    if percentile >= 90:
        return {"key": "top_10", "label": "Top 10%", "cls": "high"}
    if percentile <= 10:
        return {"key": "bottom_10", "label": "Bottom 10%", "cls": "low"}
    if percentile >= 80:
        return {"key": "top_20", "label": "Top 20%", "cls": "high"}
    if percentile <= 20:
        return {"key": "bottom_20", "label": "Bottom 20%", "cls": "low"}
    return {"key": "middle_60", "label": "Middle 60%", "cls": ""}


def bucket_mask(percentiles: pd.Series, bucket_key: str) -> pd.Series:
    if bucket_key == "top_10":
        return percentiles >= 90
    if bucket_key == "bottom_10":
        return percentiles <= 10
    if bucket_key == "top_20":
        return percentiles >= 80
    if bucket_key == "bottom_20":
        return percentiles <= 20
    return (percentiles > 20) & (percentiles < 80)


def pct_or_none(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value) * 100, 2)


def corr_or_none(left: pd.Series, right: pd.Series) -> float | None:
    value = left.corr(right)
    if pd.isna(value):
        return None
    return round(float(value), 3)


def sentiment_mask(values: pd.Series, bucket_key: str) -> pd.Series:
    if bucket_key == "ihavetosell_0_7":
        return values < 7
    if bucket_key == "panican_7_10":
        return (values >= 7) & (values < 10)
    if bucket_key == "extreme_fear_10_25":
        return (values >= 10) & (values < 25)
    if bucket_key == "fear_25_45":
        return (values >= 25) & (values < 45)
    if bucket_key == "neutral_45_55":
        return (values >= 45) & (values < 55)
    if bucket_key == "greed_55_75":
        return (values >= 55) & (values < 75)
    if bucket_key == "extreme_greed_75_100":
        return values >= 75
    raise ValueError(f"Unknown sentiment bucket: {bucket_key}")


def market_sentiment_return_buckets(
    market_records: list[dict[str, Any]],
    sentiment_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    market_df = as_dataframe(market_records, "price")
    factor_df = as_dataframe(sentiment_records, "value")
    if market_df.empty or factor_df.empty:
        return []

    priced = market_df[["date", "price"]].copy()
    priced["price_date"] = priced["date"]
    aligned = pd.merge_asof(
        factor_df.sort_values("date"),
        priced.sort_values("date"),
        on="date",
        direction="backward",
    ).dropna(subset=["price", "value"]).reset_index(drop=True)

    if aligned.empty:
        return []

    for label, days in SENTIMENT_RETURN_HORIZONS:
        targets = aligned[["date"]].copy()
        targets["target_date"] = targets["date"] + pd.Timedelta(days=days)
        future = pd.merge_asof(
            targets.sort_values("target_date"),
            market_df[["date", "price"]]
            .rename(columns={"date": f"future_date_{label}", "price": f"future_price_{label}"})
            .sort_values(f"future_date_{label}"),
            left_on="target_date",
            right_on=f"future_date_{label}",
            direction="forward",
        ).sort_index()
        aligned[f"future_date_{label}"] = future[f"future_date_{label}"].to_numpy()
        aligned[f"future_price_{label}"] = future[f"future_price_{label}"].to_numpy()
        aligned[f"forward_return_{label}"] = aligned[f"future_price_{label}"] / aligned["price"] - 1.0
        aligned[f"drawdown_{label}"] = [
            forward_drawdown_between_dates(
                market_df,
                row["price_date"],
                row[f"future_date_{label}"],
                row["price"],
            )
            for _, row in aligned.iterrows()
        ]

    baselines: dict[str, dict[str, float | None]] = {}
    for horizon, _days in SENTIMENT_RETURN_HORIZONS:
        returns = aligned[f"forward_return_{horizon}"].dropna()
        drawdowns = aligned[f"drawdown_{horizon}"].dropna()
        baselines[horizon] = {
            "avg": pct_or_none(returns.mean()) if not returns.empty else None,
            "win_rate": round(float((returns > 0).mean() * 100), 1) if not returns.empty else None,
            "avg_drawdown": pct_or_none(drawdowns.mean()) if not drawdowns.empty else None,
        }

    baseline_row: dict[str, Any] = {
        "key": "baseline_all",
        "label": "Baseline all readings",
        "observations": int(aligned.shape[0]),
        "episodes": None,
    }
    for horizon, _days in SENTIMENT_RETURN_HORIZONS:
        baseline_row[f"avg_{horizon}"] = baselines[horizon]["avg"]
        baseline_row[f"win_rate_{horizon}"] = baselines[horizon]["win_rate"]
        baseline_row[f"avg_drawdown_{horizon}"] = baselines[horizon]["avg_drawdown"]
        baseline_row[f"avg_edge_{horizon}"] = 0.0
        baseline_row[f"win_edge_{horizon}"] = 0.0
        baseline_row[f"drawdown_edge_{horizon}"] = 0.0

    rows: list[dict[str, Any]] = []
    rows.append(baseline_row)
    for bucket_key, label in SENTIMENT_BUCKETS:
        mask = sentiment_mask(aligned["value"], bucket_key)
        row: dict[str, Any] = {
            "key": bucket_key,
            "label": label,
            "observations": int(mask.sum()),
            "episodes": count_true_episodes(mask),
        }
        for horizon, _days in SENTIMENT_RETURN_HORIZONS:
            returns = aligned.loc[mask, f"forward_return_{horizon}"].dropna()
            drawdowns = aligned.loc[mask, f"drawdown_{horizon}"].dropna()
            avg_return = pct_or_none(returns.mean()) if not returns.empty else None
            win_rate = round(float((returns > 0).mean() * 100), 1) if not returns.empty else None
            avg_drawdown = pct_or_none(drawdowns.mean()) if not drawdowns.empty else None
            baseline = baselines[horizon]
            row[f"avg_{horizon}"] = avg_return
            row[f"win_rate_{horizon}"] = win_rate
            row[f"avg_drawdown_{horizon}"] = avg_drawdown
            row[f"avg_edge_{horizon}"] = (
                round(avg_return - baseline["avg"], 2)
                if avg_return is not None and baseline["avg"] is not None
                else None
            )
            row[f"win_edge_{horizon}"] = (
                round(win_rate - baseline["win_rate"], 1)
                if win_rate is not None and baseline["win_rate"] is not None
                else None
            )
            row[f"drawdown_edge_{horizon}"] = (
                round(avg_drawdown - baseline["avg_drawdown"], 2)
                if avg_drawdown is not None and baseline["avg_drawdown"] is not None
                else None
            )
        rows.append(row)

    return rows


def count_true_episodes(mask: pd.Series) -> int:
    if mask.empty:
        return 0
    values = mask.fillna(False).astype(bool)
    return int((values & ~values.shift(fill_value=False)).sum())


def forward_drawdown_between_dates(
    market_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
    start_price: float,
) -> float | None:
    if pd.isna(start_date) or pd.isna(end_date) or pd.isna(start_price) or start_price == 0:
        return None
    window = market_df[(market_df["date"] >= start_date) & (market_df["date"] <= end_date)]["price"]
    window = pd.to_numeric(window, errors="coerce").dropna()
    if window.empty:
        return None
    return float(window.min() / float(start_price) - 1.0)


def forward_drawdown_pct(prices: pd.Series, index: int, weeks: int) -> float | None:
    end = index + weeks
    if end >= len(prices):
        return None
    start_price = float(prices.iloc[index])
    if pd.isna(start_price) or start_price == 0:
        return None
    window = pd.to_numeric(prices.iloc[index : end + 1], errors="coerce").dropna()
    if window.empty:
        return None
    return float(window.min() / start_price - 1)


def average_drawdown_for_mask(aligned: pd.DataFrame, mask: pd.Series, weeks: int) -> float | None:
    values = [
        forward_drawdown_pct(aligned["price"], index, weeks)
        for index in aligned.index[mask]
    ]
    clean = pd.Series(values, dtype="float64").dropna()
    if clean.empty:
        return None
    return pct_or_none(clean.mean())


def worst_drawdown_for_mask(aligned: pd.DataFrame, mask: pd.Series, weeks: int) -> float | None:
    values = [
        forward_drawdown_pct(aligned["price"], index, weeks)
        for index in aligned.index[mask]
    ]
    clean = pd.Series(values, dtype="float64").dropna()
    if clean.empty:
        return None
    return pct_or_none(clean.min())


def factor_predictivity_for_market(
    market: str,
    factor_key: str,
    factor_payload: dict[str, Any],
    market_records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    market_df = as_dataframe(market_records, "price")
    factor_df = as_dataframe(factor_payload["records"], "value")
    if market_df.empty or factor_df.empty:
        return None

    aligned = pd.merge_asof(market_df, factor_df, on="date", direction="backward")
    aligned = aligned.dropna(subset=["price", "value"]).reset_index(drop=True)
    if aligned.empty:
        return None

    for weeks in FORWARD_WINDOWS:
        steps = weeks * 5
        aligned[f"forward_{weeks}w"] = aligned["price"].shift(-steps) / aligned["price"] - 1

    percentiles = aligned["value"].rank(method="average", pct=True) * 100
    latest = aligned.iloc[-1]
    latest_pct = percentile_rank(aligned["value"], float(latest["value"]))
    bucket = percentile_bucket(latest_pct)
    bucket_key = bucket["key"] if bucket else "middle_60"
    current_bucket_mask = bucket_mask(percentiles, bucket_key)

    expected = {}
    drawdown = {}
    worst_drawdown = {}
    for weeks in EXPECTED_RETURN_WINDOWS:
        steps = weeks * 5
        series = aligned.loc[current_bucket_mask, f"forward_{weeks}w"].dropna()
        expected[f"{weeks}w"] = pct_or_none(series.mean()) if not series.empty else None
        drawdown[f"{weeks}w"] = average_drawdown_for_mask(aligned, current_bucket_mask, steps)
        worst_drawdown[f"{weeks}w"] = worst_drawdown_for_mask(aligned, current_bucket_mask, steps)

    expected["n"] = int(aligned.loc[current_bucket_mask, "forward_26w"].dropna().shape[0])
    drawdown["n"] = expected["n"]
    worst_drawdown["n"] = expected["n"]

    extremes = {}
    for extreme_key in ("bottom_10", "top_10"):
        mask = bucket_mask(percentiles, extreme_key)
        extremes[extreme_key] = {
            f"{weeks}w": pct_or_none(aligned.loc[mask, f"forward_{weeks}w"].dropna().mean())
            for weeks in EXPECTED_RETURN_WINDOWS
        }
        extremes[extreme_key]["drawdown"] = {
            f"{weeks}w": average_drawdown_for_mask(aligned, mask, weeks * 5)
            for weeks in EXPECTED_RETURN_WINDOWS
        }
        extremes[extreme_key]["worst_drawdown"] = {
            f"{weeks}w": worst_drawdown_for_mask(aligned, mask, weeks * 5)
            for weeks in EXPECTED_RETURN_WINDOWS
        }
        extremes[extreme_key]["n"] = int(aligned.loc[mask, "forward_26w"].dropna().shape[0])

    return {
        "key": factor_key,
        "label": factor_payload["label"],
        "source": factor_payload["source"],
        "format": factor_payload["format"],
        "latest_date": latest["date"].strftime("%Y-%m-%d"),
        "latest_value": round(float(latest["value"]), 2),
        "percentile": round(latest_pct, 1) if latest_pct is not None else None,
        "bucket": bucket,
        "sample_start": aligned["date"].iloc[0].strftime("%Y-%m-%d"),
        "sample_end": aligned["date"].iloc[-1].strftime("%Y-%m-%d"),
        "n": int(aligned.shape[0]),
        "forward_corr": {
            f"{weeks}w": corr_or_none(aligned["value"], aligned[f"forward_{weeks}w"])
            for weeks in FORWARD_WINDOWS
        },
        "expected_return": expected,
        "expected_drawdown": drawdown,
        "expected_worst_drawdown": worst_drawdown,
        "extreme_returns": extremes,
    }


def build_factor_stats(prices: dict[str, Any], factors: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for market in MARKET_LABELS:
        stats[market] = {}
        records_ = prices[market]["records"]
        for factor_key, factor_payload in factors.items():
            result = factor_predictivity_for_market(market, factor_key, factor_payload, records_)
            if result:
                stats[market][factor_key] = result
    return stats


def build_sentiment_return_stats(prices: dict[str, Any], factors: dict[str, Any]) -> dict[str, Any]:
    sentiment = factors.get("cnn_fear_greed")
    if not sentiment:
        return {"horizons": [], "markets": {}}

    return {
        "horizons": [label for label, _days in SENTIMENT_RETURN_HORIZONS],
        "buckets": [{"key": key, "label": label} for key, label in SENTIMENT_BUCKETS],
        "markets": {
            market: market_sentiment_return_buckets(
                prices[market]["records"],
                sentiment["records"],
            )
            for market in MARKET_LABELS
        },
    }


def prepare_research_frame(records_: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(records_)
    if df.empty:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["price_return_1w"] = df["price"].pct_change()
    for category in RESEARCH_CATEGORIES:
        df[f"{category}_net_oi_pct"] = pd.to_numeric(df[f"{category}_net_oi_pct"], errors="coerce")
        df[f"{category}_net_oi_pct_change"] = df[f"{category}_net_oi_pct"].diff()
    for weeks in FORWARD_WINDOWS:
        df[f"forward_return_{weeks}w"] = df["price"].shift(-weeks) / df["price"] - 1
    return df


def research_percentile_rank(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return float(clean.rank(method="average", pct=True).iloc[-1] * 100)


def research_bucket_average(df: pd.DataFrame, category: str, side: str, weeks: int) -> float | None:
    series = df[f"{category}_net_oi_pct"]
    threshold = series.quantile(0.9 if side == "top" else 0.1)
    bucket = df[series >= threshold] if side == "top" else df[series <= threshold]
    value = bucket[f"forward_return_{weeks}w"].mean()
    if pd.isna(value):
        return None
    return round(float(value) * 100, 2)


def build_research_extreme_rows(df: pd.DataFrame, side: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category in RESEARCH_CATEGORIES:
        label = RESEARCH_SIGNAL_LABELS.get(category, category)
        row: dict[str, Any] = {
            "signal": f"{label} {side} 10% net/OI",
            "category": category,
            "side": side,
        }
        for weeks in RESEARCH_EXTREME_WINDOWS:
            row[f"{weeks}w"] = research_bucket_average(df, category, side, weeks)
        rows.append(row)
    return rows


def non_structural_research_takeaways(existing: dict[str, Any]) -> list[str]:
    blocked_terms = {
        RESEARCH_SIGNAL_LABELS.get(category, category).lower()
        for category in STRUCTURAL_OFFSET_CATEGORIES["tff"]
    }
    blocked_terms.update(STRUCTURAL_OFFSET_CATEGORIES["tff"])
    return [
        str(takeaway)
        for takeaway in existing.get("takeaways", [])
        if not any(term and term in str(takeaway).lower() for term in blocked_terms)
    ]


def recompute_market_research(market: str, records_: list[dict[str, Any]], existing: dict[str, Any]) -> dict[str, Any]:
    df = prepare_research_frame(records_)
    if df.empty:
        raise ValueError(f"No TFF research records are available for {market}.")

    same_week = {
        category: corr_or_none(df[f"{category}_net_oi_pct_change"], df["price_return_1w"])
        for category in RESEARCH_CATEGORIES
    }
    forward = {
        category: {
            f"{weeks}w": corr_or_none(df[f"{category}_net_oi_pct"], df[f"forward_return_{weeks}w"])
            for weeks in FORWARD_WINDOWS
        }
        for category in RESEARCH_CATEGORIES
    }

    extreme_rows = build_research_extreme_rows(df, "bottom") + build_research_extreme_rows(df, "top")
    ranked_extremes = sorted(
        extreme_rows,
        key=lambda row: (
            float("-inf") if row.get("13w") is None or pd.isna(row.get("13w")) else float(row["13w"])
        ),
        reverse=True,
    )

    latest = df.iloc[-1]
    current = {}
    for category in RESEARCH_CATEGORIES:
        percentile = research_percentile_rank(df[f"{category}_net_oi_pct"])
        current[category] = {
            "net_oi_pct": round(float(latest[f"{category}_net_oi_pct"]), 2),
            "percentile": round(float(percentile), 1) if percentile is not None else None,
        }

    return {
        "same_week": same_week,
        "forward": forward,
        "extremes": {
            "best": ranked_extremes[:4],
            "worst": sorted(
                extreme_rows,
                key=lambda row: (
                    float("inf") if row.get("13w") is None or pd.isna(row.get("13w")) else float(row["13w"])
                ),
            )[:3],
        },
        "current": current,
        "takeaways": non_structural_research_takeaways(existing),
        "bottom_line": existing.get("bottom_line", ""),
        "_meta": {
            "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "sample_start": df["date"].iloc[0].strftime("%Y-%m-%d"),
            "sample_end": df["date"].iloc[-1].strftime("%Y-%m-%d"),
            "rows": int(df.shape[0]),
            "source": "auto-generated from current TFF exact consolidated records",
        },
    }


def build_research_findings(data: dict[str, Any]) -> dict[str, Any]:
    existing = load_json_config("research_findings.json")
    research: dict[str, Any] = {}
    for market in ("nq", "sp500"):
        records_ = (((data.get("tff") or {}).get(market) or {}).get("records") or [])
        research[market] = recompute_market_research(market, records_, existing.get(market, {}))
    CONFIG_DIR.mkdir(exist_ok=True)
    CONFIG_DIR.joinpath("research_findings.json").write_text(
        json.dumps(research, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    return research


def load_json_config(name: str) -> dict[str, Any]:
    return json.loads((CONFIG_DIR / name).read_text(encoding="utf-8"))


def latest_date(records_: list[dict[str, Any]]) -> str | None:
    return records_[-1].get("date") if records_ else None


def cot_source_latest_metadata() -> dict[str, dict[str, str | None]]:
    payload: dict[str, dict[str, str | None]] = {}
    patterns = {
        "tff": "cot_exact_output/cot_exact_summary_*.csv",
        "legacy": "cot_legacy_output/cot_legacy_summary_*.csv",
    }
    for dataset_key, pattern in patterns.items():
        summary = pd.read_csv(latest_file(pattern))
        payload[dataset_key] = {
            str(row["market"]): str(row.get("source_latest_date") or row.get("latest_date") or "")[:10] or None
            for row in records(summary)
        }
    return payload


def build_metadata(
    data: dict[str, Any],
    prices: dict[str, Any],
    factors: dict[str, Any],
    liquidity: dict[str, Any],
    macro_monitor: dict[str, Any],
) -> dict[str, Any]:
    return {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "cot_latest": {
            dataset_key: {
                market: latest_date(payload["records"]) if payload else None
                for market, payload in markets.items()
            }
            for dataset_key, markets in data.items()
        },
        "cot_source_latest": cot_source_latest_metadata(),
        "fred_latest": {
            market: latest_date(payload["records"])
            for market, payload in prices.items()
        },
        "factor_latest": {
            factor_key: latest_date(payload["records"])
            for factor_key, payload in factors.items()
        },
        "liquidity_latest": {
            key: latest_date(payload["records"])
            for key, payload in (liquidity.get("definitions") or {}).items()
        },
        "funding_latest": {
            key: latest_date(payload["records"])
            for key, payload in ((liquidity.get("funding") or {}).get("definitions") or {}).items()
        },
        "macro_latest": macro_monitor.get("latest", {}).get("date") if macro_monitor.get("available") else None,
        "retirement_proxy_latest": (
            macro_monitor.get("retirement_proxy", {}).get("latest", {}).get("date")
            if macro_monitor.get("available") else None
        ),
    }


def load_regime_backtest_payload(
    data: dict[str, Any], prices: dict[str, Any]
) -> dict[str, Any]:
    dataset_dirs = {
        "tff": ROOT / "cot_regime_backtest_output",
        "legacy": ROOT / "cot_legacy_regime_backtest_output",
    }
    datasets: dict[str, Any] = {}
    for dataset_key, out_dir in dataset_dirs.items():
        history_path = out_dir / "regime_score_history.csv"
        bucket_path = out_dir / "regime_bucket_summary.csv"
        predictivity_path = out_dir / "regime_predictivity_summary.csv"
        if not history_path.exists() or not bucket_path.exists() or not predictivity_path.exists():
            datasets[dataset_key] = {
                "available": False,
                "latest": {},
                "bucket_summary": [],
                "predictivity_summary": [],
            }
            continue

        history = pd.read_csv(history_path)
        bucket = pd.read_csv(bucket_path)
        predictivity = pd.read_csv(predictivity_path)
        latest: dict[str, Any] = {}
        if not history.empty:
            history = history.sort_values(["market", "report_date", "signal_date"])
            for market, rows in history.groupby("market", sort=False):
                latest[str(market)] = records(rows.tail(1))[0]

        for market, snapshot in latest.items():
            cot_records = ((data.get(dataset_key) or {}).get(market) or {}).get("records") or []
            price_records = (prices.get(market) or {}).get("records") or []
            price_dates = [row.get("date") for row in price_records if row.get("date")]
            last_price_date = max(price_dates) if price_dates else None
            actionable_reports = []
            if last_price_date:
                last_price = pd.Timestamp(last_price_date)
                actionable_reports = [
                    row.get("date")
                    for row in cot_records
                    if row.get("date") and pd.Timestamp(row["date"]) + pd.Timedelta(days=3) <= last_price
                ]
            expected_report_date = max(actionable_reports) if actionable_reports else None
            snapshot["expected_report_date"] = expected_report_date
            snapshot["is_stale"] = bool(
                expected_report_date and snapshot.get("report_date") != expected_report_date
            )

        regime_bucket = bucket[bucket["bucket_type"] == "regime"].copy() if "bucket_type" in bucket else bucket
        datasets[dataset_key] = {
            "available": True,
            "latest": latest,
            "bucket_summary": records(regime_bucket),
            "predictivity_summary": records(predictivity),
        }

    return {
        "available": any(payload.get("available") for payload in datasets.values()),
        "datasets": datasets,
    }


def load_macro_lens_payload() -> dict[str, Any]:
    return {
        "name": "Herman Jin-inspired macro lens",
        "source_note": (
            "Built from public Herman Jin / @ShanghaoJin themes plus local COT, VIX, "
            "sentiment, price, and backtest data. The shared ChatGPT link was not accessible "
            "from this environment, so it is not quoted or treated as a source."
        ),
        "principles": [
            "Start from liquidity and positioning before valuation.",
            "Do not chase a straight-line rally; prefer pullback or negative-news entries when the thesis remains intact.",
            "Treat COT as a slow context filter, not a fast timing trigger.",
            "When the market prices a theme for perfection, look for yield, ramp, capacity, or implementation risk.",
            "Translate the setup into posture: add, hold, wait, trim, or hedge.",
        ],
        "source_links": [
            {
                "label": "PANews / 168X interview summary",
                "url": "https://www.panewslab.com/en/articles/019e2b09-164f-772d-8835-a4a1cfc0bb2f",
            },
            {
                "label": "Bitget / BlockBeats CPO caution summary",
                "url": "https://www.bitget.com/news/detail/12560605434006",
            },
            {
                "label": "Phemex CPO caution summary",
                "url": "https://phemex.com/news/article/herman-jin-cautions-against-overoptimism-in-cpo-market-86390",
            },
        ],
    }


def frontend_json_payloads(
    data: dict[str, Any],
    prices: dict[str, Any],
    factors: dict[str, Any],
    liquidity: dict[str, Any],
    macro_monitor: dict[str, Any],
    factor_stats: dict[str, Any],
    sentiment_return_stats: dict[str, Any],
    research: dict[str, Any],
    regime_rules: dict[str, Any],
    metadata: dict[str, Any],
) -> dict[str, str]:
    return {
        "DATA_JSON": json.dumps(data, separators=(",", ":")),
        "PRICES_JSON": json.dumps(prices, separators=(",", ":")),
        "COLORS_JSON": json.dumps(COLORS, separators=(",", ":")),
        "MARKET_LABELS_JSON": json.dumps(MARKET_LABELS, separators=(",", ":")),
        "DATASET_LABELS_JSON": json.dumps(DATASET_LABELS, separators=(",", ":")),
        "FACTORS_JSON": json.dumps(
            {
                "definitions": {
                    key: {
                        "label": value["label"],
                        "source": value["source"],
                        "format": value["format"],
                        "records": value["records"],
                    }
                    for key, value in factors.items()
                },
                "stats": factor_stats,
                "sentiment_return_stats": sentiment_return_stats,
            },
            separators=(",", ":"),
        ),
        "LIQUIDITY_JSON": json.dumps(liquidity, separators=(",", ":")),
        "MACRO_MONITOR_JSON": json.dumps(macro_monitor, separators=(",", ":")),
        "RESEARCH_JSON": json.dumps(research, separators=(",", ":")),
        "REGIME_RULES_JSON": json.dumps(regime_rules, separators=(",", ":")),
        "METADATA_JSON": json.dumps(metadata, separators=(",", ":")),
        "REGIME_BACKTEST_JSON": json.dumps(load_regime_backtest_payload(data, prices), separators=(",", ":")),
        "CROSS_MARKET_JSON": json.dumps(build_cross_market_positioning(data), separators=(",", ":")),
        "WEEKLY_DESK_JSON": json.dumps(build_weekly_desk_payload(data, prices), separators=(",", ":")),
        "MACRO_LENS_JSON": json.dumps(load_macro_lens_payload(), separators=(",", ":")),
    }


# ========================
# Dashboard HTML Template
# ========================

def read_template(name: str) -> str:
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")


def render_template(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
        out = out.replace(f"{{{key}}}", value)
    return out


def build_html(
    data: dict[str, Any],
    prices: dict[str, Any],
    factors: dict[str, Any],
    liquidity: dict[str, Any],
    macro_monitor: dict[str, Any],
) -> str:
    research = build_research_findings(data)
    regime_rules = {
        "tff": load_json_config("regime_rules.json"),
        "legacy": load_json_config("regime_rules_legacy.json"),
    }
    factor_stats = build_factor_stats(prices, factors)
    sentiment_return_stats = build_sentiment_return_stats(prices, factors)
    payload = frontend_json_payloads(
        data,
        prices,
        factors,
        liquidity,
        macro_monitor,
        factor_stats,
        sentiment_return_stats,
        research,
        regime_rules,
        build_metadata(data, prices, factors, liquidity, macro_monitor),
    )
    css = read_template("dashboard.css")
    script = render_template(read_template("dashboard.js"), payload)
    return render_template(
        read_template("dashboard_template.html"),
        {
            "DASHBOARD_CSS": css,
            "DASHBOARD_JS": script,
        },
    )


# ==========
# Entrypoint
# ==========

def main() -> None:
    data = load_cot_data()
    prices = load_prices()
    factors = load_factor_data()
    liquidity = load_liquidity_data()
    macro_monitor = build_macro_monitor()
    OUT.write_text(build_html(data, prices, factors, liquidity, macro_monitor), encoding="utf-8")
    print(f"Saved {OUT}")


if __name__ == "__main__":
    main()




