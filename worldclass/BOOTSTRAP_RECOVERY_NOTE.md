# Runtime data recovery contract

The production shell must remain usable when `worldclass/base.json` is missing, empty, or invalid.

`bootstrap.js` therefore:

1. validates the compact bundle before accepting it;
2. falls back to `interactive_cot_dashboard.html` when necessary;
3. extracts the same embedded JSON constants used by the compact bundle;
4. exposes them through `window.__COT_WORLDCLASS_BASE__`;
5. intercepts the legacy app data request so the recovered payload is reused rather than downloaded twice.

This fallback is recovery-only. A healthy deployment should still publish a non-empty compact bundle.
