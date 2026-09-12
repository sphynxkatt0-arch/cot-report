#!/usr/bin/env python3
"""Settle v1 legacy and v2 release-corrected general live forecasts."""
import settle_live_signals as legacy
import ledger_v2

def main():
    original=legacy.validate_forecast;legacy.validate_forecast=ledger_v2.validate_forecast
    try:legacy.main()
    finally:legacy.validate_forecast=original
if __name__=="__main__":main()
