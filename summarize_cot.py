import pandas as pd
from pathlib import Path

ROOT = Path(r"a:\work\trading\cot report\analysis")

files = {
    ("S&P 500", "TFF"): ROOT / "cot_exact_output" / "sp500_exact_consolidated_data_2016_2026.csv",
    ("NASDAQ-100", "TFF"): ROOT / "cot_exact_output" / "nq_exact_consolidated_data_2016_2026.csv",
    ("S&P 500", "Legacy"): ROOT / "cot_legacy_output" / "sp500_legacy_data_2016_2026.csv",
    ("NASDAQ-100", "Legacy"): ROOT / "cot_legacy_output" / "nq_legacy_data_2016_2026.csv",
}

print("=== SUMMARY OF COT DATA ===")
for (market, report), path in files.items():
    if not path.exists():
        print(f"File missing: {path}")
        continue
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    curr = df.iloc[-1]
    prev = df.iloc[-2]
    print(f"\n--- {market} ({report}) ---")
    print(f"Latest Date: {curr['date'].strftime('%Y-%m-%d')} (Previous: {prev['date'].strftime('%Y-%m-%d')})")
    print(f"Price: {curr['price']:,.2f} (1W chg: {curr['price_return_1w']*100:+.2f}%)")
    print(f"Open Interest: {curr['open_interest']:,.0f} (Chg: {curr['open_interest'] - prev['open_interest']:+,.0f}, {((curr['open_interest']/prev['open_interest'])-1)*100:+.2f}%)")

    if report == "TFF":
        groups = {
            "Asset Manager": ("asset_mgr_long", "asset_mgr_short", "asset_mgr_net", "asset_mgr_net_oi_pct"),
            "Dealer": ("dealer_long", "dealer_short", "dealer_net", "dealer_net_oi_pct"),
            "Leveraged Money": ("lev_money_long", "lev_money_short", "lev_money_net", "lev_money_net_oi_pct"),
            "Other Reportable": ("other_reportable_long", "other_reportable_short", "other_reportable_net", "other_reportable_net_oi_pct"),
            "Non-reportable": ("non_reportable_long", "non_reportable_short", "non_reportable_net", "non_reportable_net_oi_pct"),
        }
    else:
        groups = {
            "Non-commercial": ("noncommercial_long", "noncommercial_short", "noncommercial_net", "noncommercial_net_oi_pct"),
            "Commercial": ("commercial_long", "commercial_short", "commercial_net", "commercial_net_oi_pct"),
            "Non-reportable": ("nonreportable_long", "nonreportable_short", "nonreportable_net", "nonreportable_net_oi_pct"),
        }
    
    for gname, (l_col, s_col, n_col, pct_col) in groups.items():
        net = curr[n_col]
        net_oi = curr[pct_col]
        net_chg = curr[n_col] - prev[n_col]
        l_chg = curr[l_col] - prev[l_col]
        s_chg = curr[s_col] - prev[s_col]
        print(f"  {gname:16s}: Net {net:+10,.0f} | Net/OI: {net_oi:+6.2f}% | NetChg: {net_chg:+8,.0f} | LChg: {l_chg:+8,.0f} | SChg: {s_chg:+8,.0f}")
