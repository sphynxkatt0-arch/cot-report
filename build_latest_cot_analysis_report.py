from __future__ import annotations

import html
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import nbformat as nbf
from nbclient import NotebookClient


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "analysis"

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
}

BLUE = {"light": "#CEDFFE", "base": "#A3BEFA", "dark": "#2E4780"}
ORANGE = {"light": "#FFBDA1", "base": "#F0986E", "dark": "#804126"}


SOURCE_FILES = {
    ("S&P 500", "TFF"): ANALYSIS / "cot_exact_output" / "sp500_exact_consolidated_data_2016_2026.csv",
    ("NASDAQ-100", "TFF"): ANALYSIS / "cot_exact_output" / "nq_exact_consolidated_data_2016_2026.csv",
    ("S&P 500", "Legacy"): ANALYSIS / "cot_legacy_output" / "sp500_legacy_data_2016_2026.csv",
    ("NASDAQ-100", "Legacy"): ANALYSIS / "cot_legacy_output" / "nq_legacy_data_2016_2026.csv",
}

TFF_GROUPS = {
    "Asset Manager": ("asset_mgr_long", "asset_mgr_short", "asset_mgr_net", "asset_mgr_net_oi_pct"),
    "Dealer": ("dealer_long", "dealer_short", "dealer_net", "dealer_net_oi_pct"),
    "Leveraged Money": ("lev_money_long", "lev_money_short", "lev_money_net", "lev_money_net_oi_pct"),
    "Other Reportable": ("other_reportable_long", "other_reportable_short", "other_reportable_net", "other_reportable_net_oi_pct"),
    "Non-reportable": ("non_reportable_long", "non_reportable_short", "non_reportable_net", "non_reportable_net_oi_pct"),
}

LEGACY_GROUPS = {
    "Non-commercial": ("noncommercial_long", "noncommercial_short", "noncommercial_net", "noncommercial_net_oi_pct"),
    "Commercial": ("commercial_long", "commercial_short", "commercial_net", "commercial_net_oi_pct"),
    "Non-reportable": ("nonreportable_long", "nonreportable_short", "nonreportable_net", "nonreportable_net_oi_pct"),
}


def use_chart_theme() -> None:
    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": TOKENS["surface"],
            "figure.edgecolor": "none",
            "savefig.facecolor": TOKENS["surface"],
            "savefig.edgecolor": "none",
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "axes.labelcolor": TOKENS["ink"],
            "grid.color": TOKENS["grid"],
            "grid.linewidth": 0.8,
            "font.family": "sans-serif",
            "font.sans-serif": ["Aptos", "Inter", "Segoe UI", "DejaVu Sans", "Arial"],
            "font.monospace": ["Consolas", "DejaVu Sans Mono"],
            "patch.linewidth": 1.0,
        },
    )


def add_chart_header(fig, axes, title: str, subtitle: str) -> None:
    first_ax = np.asarray(axes).flat[0]
    left = first_ax.get_position().x0
    fig.text(left, 0.985, title, ha="left", va="top", fontsize=16, fontweight="semibold", color=TOKENS["ink"])
    fig.text(left, 0.952, subtitle, ha="left", va="top", fontsize=10, color=TOKENS["muted"])
    fig.subplots_adjust(top=0.88, hspace=0.48, wspace=0.36)


def load_position_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    market_meta: list[dict] = []
    for (market, report), path in SOURCE_FILES.items():
        df = pd.read_csv(path)
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
        previous, current = df.iloc[-2], df.iloc[-1]
        groups = TFF_GROUPS if report == "TFF" else LEGACY_GROUPS
        market_meta.append(
            {
                "market": market,
                "report": report,
                "date": current["date"],
                "previous_date": previous["date"],
                "open_interest": float(current["open_interest"]),
                "open_interest_change": float(current["open_interest"] - previous["open_interest"]),
                "open_interest_change_pct": float((current["open_interest"] / previous["open_interest"] - 1) * 100),
                "price": float(current["price"]),
                "price_return_1w_pct": float(current["price_return_1w"] * 100),
                "source_path": str(path),
            }
        )
        for group, (long_col, short_col, net_col, net_oi_col) in groups.items():
            rows.append(
                {
                    "market": market,
                    "report": report,
                    "date": current["date"],
                    "group": group,
                    "long": float(current[long_col]),
                    "short": float(current[short_col]),
                    "net": float(current[net_col]),
                    "net_oi_pct": float(current[net_oi_col]),
                    "long_change": float(current[long_col] - previous[long_col]),
                    "short_change": float(current[short_col] - previous[short_col]),
                    "net_change": float(current[net_col] - previous[net_col]),
                    "net_oi_pct_change": float(current[net_oi_col] - previous[net_oi_col]),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(market_meta)


def load_percentiles(position_rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    tff_regime = pd.read_csv(ANALYSIS / "cot_regime_backtest_output" / "regime_score_history.csv")
    legacy_regime = pd.read_csv(ANALYSIS / "cot_legacy_regime_backtest_output" / "regime_score_history.csv")
    market_key = {"S&P 500": "sp500", "NASDAQ-100": "nq"}
    tff_pct_cols = {
        "Asset Manager": "asset_mgr_percentile",
        "Dealer": "dealer_percentile",
        "Leveraged Money": "lev_money_percentile",
        "Other Reportable": "other_reportable_percentile",
        "Non-reportable": "non_reportable_percentile",
    }
    legacy_pct_cols = {
        "Non-commercial": "noncommercial_percentile",
        "Commercial": "commercial_percentile",
        "Non-reportable": "nonreportable_percentile",
    }
    percentile_rows: list[dict] = []
    regime_rows: list[dict] = []
    for market, key in market_key.items():
        for report, regime_df, pct_cols in (
            ("TFF", tff_regime, tff_pct_cols),
            ("Legacy", legacy_regime, legacy_pct_cols),
        ):
            current = regime_df.loc[regime_df["market"] == key].sort_values("report_date").iloc[-1]
            regime_rows.append(
                {
                    "market": market,
                    "report": report,
                    "report_date": current["report_date"],
                    "score": float(current["score"]),
                    "bucket": current["bucket"],
                    "trigger_detail": current.get("trigger_detail", "") if pd.notna(current.get("trigger_detail", "")) else "",
                }
            )
            for group, pct_col in pct_cols.items():
                net_oi = position_rows.loc[
                    (position_rows["market"] == market)
                    & (position_rows["report"] == report)
                    & (position_rows["group"] == group),
                    "net_oi_pct",
                ].iloc[0]
                percentile_rows.append(
                    {
                        "market": market,
                        "report": report,
                        "group": group,
                        "net_oi_pct": float(net_oi),
                        "percentile": float(current[pct_col]),
                    }
                )
    return pd.DataFrame(percentile_rows), pd.DataFrame(regime_rows)


def render_net_oi_chart(position_rows: pd.DataFrame, out_dir: Path) -> None:
    use_chart_theme()
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    panels = [
        ("S&P 500", "TFF"),
        ("NASDAQ-100", "TFF"),
        ("S&P 500", "Legacy"),
        ("NASDAQ-100", "Legacy"),
    ]
    for ax, (market, report) in zip(axes.flat, panels):
        part = position_rows.loc[(position_rows["market"] == market) & (position_rows["report"] == report)].copy()
        part = part.sort_values("net_oi_pct")
        colors = [BLUE["base"] if v >= 0 else ORANGE["base"] for v in part["net_oi_pct"]]
        edges = [BLUE["dark"] if v >= 0 else ORANGE["dark"] for v in part["net_oi_pct"]]
        bars = ax.barh(part["group"], part["net_oi_pct"], color=colors, edgecolor=edges, linewidth=1.0)
        ax.axvline(0, color=TOKENS["ink"], linewidth=1.0)
        bound = max(10, np.ceil(part["net_oi_pct"].abs().max() / 10) * 10)
        ax.set_xlim(-bound * 1.15, bound * 1.15)
        ax.set_title(f"{market} — {report}", loc="left", fontsize=11, fontweight="semibold", color=TOKENS["ink"])
        ax.set_xlabel("Net position as % of open interest")
        ax.set_ylabel("")
        ax.xaxis.grid(True)
        ax.yaxis.grid(False)
        for bar, value in zip(bars, part["net_oi_pct"]):
            x = value + (bound * 0.025 if value >= 0 else -bound * 0.025)
            ax.text(x, bar.get_y() + bar.get_height() / 2, f"{value:+.1f}%", ha="left" if value >= 0 else "right", va="center", fontsize=8, color=TOKENS["ink"], family="monospace")
        sns.despine(ax=ax)
    add_chart_header(
        fig,
        axes,
        "Current COT positioning by participant",
        "Futures-only consolidated positions as of June 16, 2026; positive values are net long, negative values are net short.",
    )
    for suffix in ("png", "svg"):
        fig.savefig(out_dir / f"current_net_oi.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def render_percentile_chart(percentiles: pd.DataFrame, out_dir: Path) -> None:
    use_chart_theme()
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    panels = [
        ("S&P 500", "TFF"),
        ("NASDAQ-100", "TFF"),
        ("S&P 500", "Legacy"),
        ("NASDAQ-100", "Legacy"),
    ]
    for ax, (market, report) in zip(axes.flat, panels):
        part = percentiles.loc[(percentiles["market"] == market) & (percentiles["report"] == report)].copy()
        part = part.sort_values("percentile")
        bars = ax.barh(part["group"], part["percentile"], color=BLUE["base"], edgecolor=BLUE["dark"], linewidth=1.0)
        ax.axvline(10, color=ORANGE["dark"], linewidth=1.0, linestyle=":")
        ax.axvline(90, color=ORANGE["dark"], linewidth=1.0, linestyle=":")
        ax.set_xlim(0, 100)
        ax.set_title(f"{market} — {report}", loc="left", fontsize=11, fontweight="semibold", color=TOKENS["ink"])
        ax.set_xlabel("Historical percentile")
        ax.set_ylabel("")
        ax.xaxis.grid(True)
        ax.yaxis.grid(False)
        for bar, value in zip(bars, part["percentile"]):
            ax.text(min(value + 1.3, 98), bar.get_y() + bar.get_height() / 2, f"{value:.1f}", ha="left" if value < 94 else "right", va="center", fontsize=8, color=TOKENS["ink"], family="monospace")
        sns.despine(ax=ax)
    add_chart_header(
        fig,
        axes,
        "Where current positioning sits in the 2016–2026 history",
        "Expanding-window percentile through June 16, 2026. Dotted lines mark the 10th and 90th percentiles used as extreme zones.",
    )
    for suffix in ("png", "svg"):
        fig.savefig(out_dir / f"positioning_percentiles.{suffix}", dpi=180, bbox_inches="tight")
    plt.close(fig)


def fmt_contracts(value: float) -> str:
    return f"{value:+,.0f}"


def fmt_pct(value: float) -> str:
    return f"{value:+.1f}%"


def table_html(frame: pd.DataFrame) -> str:
    headers = "".join(f"<th>{html.escape(str(col))}</th>" for col in frame.columns)
    body = []
    for _, row in frame.iterrows():
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<div class='table-wrap'><table><thead><tr>{headers}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"


def market_table(position_rows: pd.DataFrame, percentiles: pd.DataFrame, market: str) -> str:
    merged = position_rows.loc[position_rows["market"] == market].copy()
    if "percentile" not in merged.columns:
        merged = merged.merge(
            percentiles[["market", "report", "group", "percentile"]], on=["market", "report", "group"], how="left"
        )
    display = merged[["report", "group", "net", "net_oi_pct", "net_change", "long_change", "short_change", "percentile"]].copy()
    display.columns = ["Report", "Participant", "Net contracts", "Net / OI", "Weekly net change", "Long change", "Short change", "Hist. percentile"]
    display["Net contracts"] = display["Net contracts"].map(lambda x: f"{x:,.0f}")
    display["Net / OI"] = display["Net / OI"].map(lambda x: f"{x:+.1f}%")
    display["Weekly net change"] = display["Weekly net change"].map(fmt_contracts)
    display["Long change"] = display["Long change"].map(fmt_contracts)
    display["Short change"] = display["Short change"].map(fmt_contracts)
    display["Hist. percentile"] = display["Hist. percentile"].map(lambda x: f"{x:.1f}")
    return table_html(display)


def build_report(position_rows: pd.DataFrame, meta: pd.DataFrame, percentiles: pd.DataFrame, regimes: pd.DataFrame, out_dir: Path) -> Path:
    sp_tff = regimes.loc[(regimes["market"] == "S&P 500") & (regimes["report"] == "TFF")].iloc[0]
    nq_tff = regimes.loc[(regimes["market"] == "NASDAQ-100") & (regimes["report"] == "TFF")].iloc[0]
    nq_legacy = regimes.loc[(regimes["market"] == "NASDAQ-100") & (regimes["report"] == "Legacy")].iloc[0]
    sp_oi = meta.loc[(meta["market"] == "S&P 500") & (meta["report"] == "TFF")].iloc[0]
    nq_oi = meta.loc[(meta["market"] == "NASDAQ-100") & (meta["report"] == "TFF")].iloc[0]

    sp_table = market_table(position_rows, percentiles, "S&P 500")
    nq_table = market_table(position_rows, percentiles, "NASDAQ-100")
    title = "S&P 500 and Nasdaq-100 COT Read"
    report_path = out_dir / "cot_sp_nq_2026-06-16.html"
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{ --bg:#faf8f5; --panel:#fff; --ink:#171411; --muted:#5f5750; --line:#ddd6ce; --blue:#2E4780; --orange:#804126; }}
    * {{ box-sizing:border-box; }}
    body {{ font-family:Inter,"Segoe UI",system-ui,sans-serif; margin:0; background:var(--bg); color:var(--ink); }}
    main {{ max-width:1080px; margin:0 auto; padding:42px 24px 72px; }}
    header, section {{ margin-bottom:36px; }}
    h1 {{ font-size:38px; line-height:1.08; margin:0 0 8px; letter-spacing:-0.03em; }}
    h2 {{ font-size:25px; line-height:1.2; margin:0 0 14px; letter-spacing:-0.02em; }}
    h3 {{ font-size:18px; margin:24px 0 10px; }}
    p, li {{ line-height:1.58; }}
    .eyebrow {{ color:var(--muted); font-size:14px; }}
    .executive-summary-box {{ padding:22px 26px; background:linear-gradient(180deg,#f6f0e8 0%,#efe7dc 100%); border:1px solid #ddd1c2; border-radius:18px; box-shadow:0 12px 28px rgba(23,20,17,.06); }}
    .executive-summary-box ul {{ margin:0; padding-left:22px; }}
    .executive-summary-box li + li {{ margin-top:10px; }}
    .callout {{ padding:18px 20px; background:#f2ede6; border-radius:12px; border-left:4px solid var(--orange); }}
    .definition {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
    .definition div {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
    .definition strong {{ display:block; margin-bottom:4px; }}
    figure {{ margin:24px 0; background:var(--panel); border:1px solid var(--line); border-radius:16px; padding:16px; }}
    figure img {{ width:100%; height:auto; display:block; }}
    figcaption {{ color:var(--muted); font-size:14px; margin-top:10px; }}
    .table-wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:12px; background:var(--panel); }}
    table {{ width:100%; border-collapse:collapse; font-size:13px; }}
    th,td {{ padding:10px 11px; border-bottom:1px solid #eee8e1; text-align:right; white-space:nowrap; }}
    th:first-child,td:first-child,th:nth-child(2),td:nth-child(2) {{ text-align:left; }}
    th {{ background:#f4f1ed; color:#403a35; position:sticky; top:0; }}
    tr:last-child td {{ border-bottom:none; }}
    .tag {{ display:inline-block; padding:3px 8px; border-radius:999px; background:#eaf1fe; color:var(--blue); font-size:12px; font-weight:600; }}
    @media (max-width:760px) {{ main {{ padding:28px 14px 48px; }} h1 {{ font-size:30px; }} .definition {{ grid-template-columns:1fr; }} figure {{ padding:8px; }} }}
  </style>
</head>
<body>
<main data-report-audience="product stakeholders" data-report-date="2026-06-16"
      data-source-tff="https://www.cftc.gov/dea/newcot/FinFutWk.txt"
      data-source-legacy="https://www.cftc.gov/dea/newcot/deafut.txt">
  <header data-contract-section="title">
    <h1>{title}</h1>
    <div class="eyebrow">Positions dated June 16, 2026 · released June 19 · first actionable session June 22</div>
  </header>

  <section class="executive-summary-box" data-contract-section="executive-summary">
    <h2>Executive Summary</h2>
    <ul>
      <li><strong>Nasdaq has the clearer contrarian upside setup, but it is a squeeze setup—not clean risk-on.</strong> Legacy non-commercials are net short 20,866 contracts, only the 6.8th percentile of the 2016–2026 history, which triggers the local model’s +2.5 Risk-On signal. TFF simultaneously shows asset managers cutting net exposure by 13,304 contracts and non-reportables at the 87.5th percentile, so sponsorship is weaker and retail crowding is higher.</li>
      <li><strong>S&amp;P positioning is neutral-to-mixed.</strong> Asset managers remain heavily net long (+986,577; 37.6% of OI), while leveraged funds added 64,192 net shorts. Dealers became 59,630 contracts less net short and Legacy non-commercials covered 14,411 net shorts, but non-reportables are already at the 89.7th percentile.</li>
      <li><strong>Do not over-read the sharp net/OI percentage moves this week.</strong> Consolidated open interest jumped {sp_oi['open_interest_change_pct']:.1f}% in S&amp;P and {nq_oi['open_interest_change_pct']:.1f}% in Nasdaq during quarterly expiry/roll week. Absolute long/short changes are the cleaner conviction read.</li>
    </ul>
  </section>

  <section data-contract-section="definitions">
    <h2>What this report measures</h2>
    <div class="definition">
      <div><strong>TFF</strong>Dealer, asset-manager, leveraged-fund, other-reportable, and non-reportable futures-only positions.</div>
      <div><strong>Legacy</strong>Non-commercial, commercial, and non-reportable futures-only positions.</div>
      <div><strong>Percentile</strong>Expanding 2016–2026 percentile in the local regime model; 10/90 mark extreme zones.</div>
    </div>
  </section>

  <section data-contract-section="key-findings">
    <h2>S&amp;P: institutions still own the trend, but the marginal flow is conflicted</h2>
    <p><strong>TFF is not giving a clean directional signal.</strong> Asset managers barely changed their absolute net (+986,838 to +986,577), so their apparent 6.4-point collapse as a share of OI is almost entirely a rollover-denominator effect. The real weekly move was leveraged money: longs fell 11,546 while shorts rose 52,647, worsening the net short by 64,192. Dealer positioning moved the opposite way as dealer shorts fell 45,918.</p>
    <p><strong>Legacy confirms short covering, not fresh speculative buying.</strong> Non-commercial longs fell 5,510, but shorts fell more—19,921—so net positioning improved by 14,411 while remaining net short 180,143. Non-reportables added 17,757 net longs and sit at the 89.7th percentile, just below the model’s 90th-percentile crowding threshold.</p>
    {sp_table}
  </section>

  <section data-contract-section="key-findings">
    <h2>Nasdaq: short crowding supports a squeeze, while TFF sponsorship weakens</h2>
    <p><strong>Legacy gives the strongest signal in the four-way comparison.</strong> Non-commercials added 9,885 net shorts, driven by a 10,748 increase in shorts against only 863 added longs. Net exposure is -5.6% of OI and at the 6.8th percentile, a historically crowded short position. Commercials became 6,390 contracts more net long, adding contrarian support.</p>
    <p><strong>TFF blocks a simple bullish conclusion.</strong> Asset managers cut longs and added shorts, reducing net by 13,304. Leveraged funds covered 6,037 shorts and improved net by 5,286, but non-reportables added 3,495 net longs and remain above the TFF model’s 85th-percentile risk threshold. The result is a <span class="tag">TFF Mixed, score -1.0</span> against a <span class="tag">Legacy Risk-On, score +2.5</span>.</p>
    {nq_table}
  </section>

  <section data-contract-section="visual-evidence">
    <h2>Positioning is more polarized in S&amp;P; Nasdaq is more asymmetric</h2>
    <p>S&amp;P shows the classic TFF split between long asset managers and short leveraged funds/dealers. Nasdaq is less extreme in those TFF buckets, but its Legacy speculative short is historically compressed enough to create squeeze fuel.</p>
    <figure>
      <img src="current_net_oi.png" alt="Current net positions as a percent of open interest for S&P 500 and Nasdaq-100 in TFF and Legacy reports">
      <figcaption>Net position as a share of open interest. Positive bars are net long; negative bars are net short. Source: CFTC futures-only consolidated reports.</figcaption>
    </figure>
  </section>

  <section data-contract-section="visual-evidence">
    <h2>The actionable extremes are Nasdaq non-commercial shorts and elevated retail longs</h2>
    <p>The percentile view separates ordinary net positions from historically stretched ones. Nasdaq Legacy non-commercials are below the 10th percentile, while Nasdaq and S&amp;P non-reportables sit close to the upper extreme zone.</p>
    <figure>
      <img src="positioning_percentiles.png" alt="Historical percentiles of COT positioning for S&P 500 and Nasdaq-100">
      <figcaption>Expanding-window percentile through June 16, 2026; dotted reference lines mark the 10th and 90th percentiles.</figcaption>
    </figure>
  </section>

  <section data-contract-section="recommended-next-steps">
    <h2>Trading read and next confirmation points</h2>
    <ol>
      <li><strong>Relative bias: Nasdaq over S&amp;P for upside asymmetry.</strong> The crowded Legacy short can fuel a squeeze, but require price acceptance above the June 16/22 area because TFF asset managers are not confirming.</li>
      <li><strong>S&amp;P: stay neutral until one side resolves.</strong> A better long setup needs leveraged-fund short covering without non-reportables pushing decisively above the 90th percentile. A bearish setup needs asset-manager net selling in absolute contracts, not only a lower net/OI ratio.</li>
      <li><strong>Next COT checkpoint:</strong> watch whether Nasdaq non-commercial shorts unwind and whether asset managers stabilize. If both occur together, the squeeze becomes a broader risk-on signal; if shorts remain crowded while asset managers keep selling, expect volatility rather than a clean trend.</li>
    </ol>
  </section>

  <section data-contract-section="further-questions">
    <h2>What would change the call</h2>
    <p>A decisive shift would be synchronized institutional flow: Nasdaq asset managers adding net longs while Legacy non-commercials cover shorts, or S&amp;P leveraged funds covering while asset managers hold their absolute net exposure. Until then, the report argues for relative positioning and confirmation, not an outright index-level forecast.</p>
  </section>

  <section data-contract-section="caveats-and-assumptions">
    <h2>Caveats and Assumptions</h2>
    <div class="callout">
      <p><strong>Quarterly roll week is the main caveat.</strong> Consolidated open interest rose sharply, so net/OI changes mechanically exaggerate shifts. COT positions are Tuesday snapshots released Friday, not live Monday flow. TFF and Legacy categories overlap economically and should not be added together. Percentile and regime labels are historical associations, not causal forecasts; short-horizon regime differences are weak in the local backtest.</p>
    </div>
  </section>
</main>
</body>
</html>"""
    report_path.write_text(document, encoding="utf-8")
    return report_path


def build_notebook(position_rows: pd.DataFrame, meta: pd.DataFrame, percentiles: pd.DataFrame, regimes: pd.DataFrame, out_dir: Path) -> Path:
    root_literal = repr(str(ROOT))
    notebook = nbf.v4.new_notebook()
    notebook["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    notebook["cells"] = [
        nbf.v4.new_markdown_cell(
            "## tl;dr\n\n"
            "- Nasdaq Legacy positioning is the clearest contrarian upside signal: non-commercial net exposure is at the 6.8th percentile.\n"
            "- Nasdaq TFF is less constructive because asset managers reduced net exposure and non-reportables remain elevated.\n"
            "- S&P is mixed: asset-manager longs remain large, leveraged funds added shorts, and retail positioning is near an extreme.\n"
            "- Quarterly rollover inflated open interest, so absolute contract changes carry more weight than weekly net/OI changes."
        ),
        nbf.v4.new_markdown_cell(
            "## Context & Methods\n\n"
            "The notebook uses the local CFTC futures-only consolidated extracts refreshed through June 16, 2026. "
            "It compares the latest row with June 9, then joins the current expanding-window percentiles and regime labels.\n\n"
            "### Key Assumptions\n\n"
            "- TFF and Legacy are interpreted separately because their trader classifications overlap.\n"
            "- Absolute long/short changes receive more weight in quarterly roll week than changes in net position as a share of open interest."
        ),
        nbf.v4.new_markdown_cell("## Data\n\n### 1. Load the refreshed COT extracts"),
        nbf.v4.new_code_cell(
            f"from pathlib import Path\nimport pandas as pd\n\nROOT = Path({root_literal})\nANALYSIS = ROOT / 'analysis'\n"
            "paths = {\n"
            "    ('S&P 500','TFF'): ANALYSIS/'cot_exact_output'/'sp500_exact_consolidated_data_2016_2026.csv',\n"
            "    ('NASDAQ-100','TFF'): ANALYSIS/'cot_exact_output'/'nq_exact_consolidated_data_2016_2026.csv',\n"
            "    ('S&P 500','Legacy'): ANALYSIS/'cot_legacy_output'/'sp500_legacy_data_2016_2026.csv',\n"
            "    ('NASDAQ-100','Legacy'): ANALYSIS/'cot_legacy_output'/'nq_legacy_data_2016_2026.csv',\n"
            "}\n"
            "freshness = []\n"
            "for (market, report), path in paths.items():\n"
            "    frame = pd.read_csv(path)\n"
            "    freshness.append({'market': market, 'report': report, 'latest_date': frame['date'].iloc[-1], 'rows': len(frame)})\n"
            "pd.DataFrame(freshness)"
        ),
        nbf.v4.new_markdown_cell("## Results\n\n### 2. Latest positioning, flows, and historical percentiles"),
        nbf.v4.new_code_cell(
            "position_rows = pd.read_csv(ANALYSIS/'reports'/'cot_2026-06-16'/'position_rows.csv')\n"
            "position_rows[['market','report','group','net','net_oi_pct','net_change','long_change','short_change','percentile']].round(2)"
        ),
        nbf.v4.new_markdown_cell("### 3. Regime labels and rollover check"),
        nbf.v4.new_code_cell(
            "regimes = pd.read_csv(ANALYSIS/'reports'/'cot_2026-06-16'/'current_regimes.csv')\n"
            "meta = pd.read_csv(ANALYSIS/'reports'/'cot_2026-06-16'/'market_meta.csv')\n"
            "display(regimes)\n"
            "meta[['market','report','date','open_interest','open_interest_change','open_interest_change_pct','price_return_1w_pct']].round(2)"
        ),
        nbf.v4.new_markdown_cell(
            "## Takeaways\n\n"
            "1. Nasdaq has stronger upside asymmetry than S&P because Legacy speculative shorts are historically crowded.\n"
            "2. Nasdaq is not a clean structural long until TFF asset managers stop reducing exposure.\n"
            "3. S&P is mixed and needs confirmation from leveraged-fund covering or genuine asset-manager selling.\n"
            "4. Elevated non-reportable percentiles in both markets reduce the quality of an unhedged chase."
        ),
    ]
    notebook_path = out_dir / "cot_sp_nq_2026-06-16.ipynb"
    nbf.write(notebook, notebook_path)
    client = NotebookClient(notebook, timeout=180, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
    client.execute()
    nbf.write(notebook, notebook_path)
    return notebook_path


def build_source_notes(out_dir: Path) -> None:
    notes = """# Source and QA Notes

## Controlling sources

- Official CFTC current report page: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- TFF Futures Only weekly feed: https://www.cftc.gov/dea/newcot/FinFutWk.txt
- Legacy Futures Only weekly feed: https://www.cftc.gov/dea/newcot/deafut.txt
- Local refreshed TFF extracts: `analysis/cot_exact_output/*_exact_consolidated_data_2016_2026.csv`
- Local refreshed Legacy extracts: `analysis/cot_legacy_output/*_legacy_data_2016_2026.csv`
- Local regime histories: `analysis/cot_regime_backtest_output/regime_score_history.csv` and `analysis/cot_legacy_regime_backtest_output/regime_score_history.csv`

## Validation checks

- Dashboard metadata and all four source extracts end on 2026-06-16.
- Official CFTC viewable TFF and Legacy pages show the same open interest and participant positions used here.
- Latest rows were compared with 2026-06-09 by direct subtraction of long, short, and net contracts.
- Open-interest changes were checked independently because quarterly rollover makes net/OI deltas less reliable.
- TFF and Legacy totals were not added together because classifications overlap.

## Chart map

1. `current_net_oi.png`: Comparison & Ranking / faceted diverging horizontal bars; current net/OI by report, market, and participant; two-root signed palette.
2. `positioning_percentiles.png`: Uncertainty & Benchmark / faceted horizontal bars; current expanding-window percentile with 10th/90th reference lines; single-root palette plus neutral/orange references.

## Report structure mapping

- Title: report header.
- Executive summary: visible answer-first summary.
- Key findings with visual evidence: S&P section, Nasdaq section, net/OI chart, percentile chart.
- Recommended next steps: trading read and next confirmation points.
- Further questions: what would change the call.
- Caveats and assumptions: rollover, reporting lag, classification overlap, and non-causal backtest caveat.

## QA result

Ready to share with caveats. The material caveat is quarterly rollover: absolute contract changes are emphasized over net/OI percentage changes.
"""
    (out_dir / "source_notes.md").write_text(notes, encoding="utf-8")


def main() -> None:
    position_rows, meta = load_position_rows()
    percentiles, regimes = load_percentiles(position_rows)
    report_date = position_rows["date"].max().strftime("%Y-%m-%d")
    out_dir = ANALYSIS / "reports" / f"cot_{report_date}"
    out_dir.mkdir(parents=True, exist_ok=True)

    position_rows = position_rows.merge(
        percentiles[["market", "report", "group", "percentile"]],
        on=["market", "report", "group"],
        how="left",
    )
    position_rows.to_csv(out_dir / "position_rows.csv", index=False)
    meta.to_csv(out_dir / "market_meta.csv", index=False)
    regimes.to_csv(out_dir / "current_regimes.csv", index=False)

    render_net_oi_chart(position_rows, out_dir)
    render_percentile_chart(percentiles, out_dir)
    report_path = build_report(position_rows, meta, percentiles, regimes, out_dir)
    build_source_notes(out_dir)
    notebook_path = build_notebook(position_rows, meta, percentiles, regimes, out_dir)
    print(f"Report: {report_path}")
    print(f"Notebook: {notebook_path}")


if __name__ == "__main__":
    main()
