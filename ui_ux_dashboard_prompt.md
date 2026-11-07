# Prompt: Improve The COT Macro Monitor Dashboard UI/UX

Use `ui-ux-pro-max-skill-main` to redesign and implement a more polished UI/UX for the existing dashboard in `A:\work\trading\cot report`.

## Objective

Improve the existing COT Macro Monitor into a professional, data-dense financial analytics workbench for traders and market researchers. The dashboard must remain operational and information-rich: CFTC positioning, macro liquidity, rates, credit, volatility, regime scoring, threshold scans, and backtest evidence should become easier to scan, compare, and act on.

This is not a landing page. Do not add marketing hero sections, decorative illustration, gradient blobs, or oversized promotional composition. The first viewport should still clearly be the dashboard.

## Source Files

Work from the source templates:

- `analysis/dashboard_template/dashboard_template.html`
- `analysis/dashboard_template/dashboard.css`
- `analysis/dashboard_template/dashboard.js`
- `analysis/build_interactive_cot_dashboard.py` only if new generated markup/data is required

Generated output:

- `analysis/interactive_cot_dashboard.html`

Do not treat the generated HTML as the source of truth.

## Start With UI UX Pro Max

Run the local skill searches first and synthesize the results:

```powershell
cd "A:\work\trading\cot report\ui-ux-pro-max-skill-main\ui-ux-pro-max-skill-main"
py src\ui-ux-pro-max\scripts\search.py "financial trading macro liquidity COT dashboard data-dense analytical workbench" --design-system -p "COT Macro Monitor" -f markdown
py src\ui-ux-pro-max\scripts\search.py "financial dashboard timeline scorecard comparative analytics" --domain chart -n 8
py src\ui-ux-pro-max\scripts\search.py "dashboard controls responsive accessibility data dense" --domain ux -n 10
py src\ui-ux-pro-max\scripts\search.py "dashboard charts controls vanilla html css javascript plotly" --stack html-tailwind
```

Use this design direction unless the searches reveal a better fit:

- Style: dark-first financial/data-dense dashboard, with light theme preserved.
- Mood: quiet, technical, precise, high-trust, low ornament.
- Typography: Fira Sans for body/interface, Fira Code only for values, dates, tickers, and compact technical labels.
- Palette: deep slate/OLED backgrounds, restrained borders, semantic green/amber/red status colors, cyan/blue for primary data traces. Avoid a purple-dominant or one-hue palette.
- Charts: time-series line charts remain appropriate; scorecards should expose visible values and thresholds, not hover-only data.

## Problems To Solve

1. Mobile layout currently breaks down: the control panel and chart remain side-by-side, the main chart/title can be pushed off-screen, and the floating "Hide controls" button overlaps form content. Create a mobile-first layout with a proper controls drawer/sheet or stacked controls above the workbench. No page-level horizontal scrolling at 320, 375, 414, 768, 1024, or 1440 px.

2. Desktop density needs stronger hierarchy. Keep the dashboard compact, but make the reading path clearer: top status strip, primary score/regime read, workbench chart, decision snapshot, macro monitor, evidence/research. Use section anchors/tabs only if they improve scanning.

3. The main chart is visually overloaded. Improve chart affordances without removing analytical capability:
   - Better legend placement and active/inactive state clarity.
   - Clearer default overlay set.
   - Stronger color and stroke differentiation, including dashed/dotted styles where helpful.
   - Axis labels that are easier to associate with their series.
   - Controls for common presets such as "COT + Price", "Macro Liquidity", "Stress", and "Sentiment" if this can be done cleanly.

4. The sidebar controls need to feel like an analyst control surface, not a long form:
   - Group related controls into compact sections.
   - Use stable control heights and responsive constraints.
   - Make checkboxes/toggles large enough for touch.
   - Keep reset actions close to the thing they reset.
   - Ensure focus states and keyboard use are obvious.

5. The top summary and macro scorecard should make the current read obvious in under 10 seconds:
   - Current market/report/date.
   - Regime score and confidence.
   - Biggest positive and negative drivers.
   - Freshness warnings.
   - Latest extreme/crowding signal.
   Preserve nuance, but make the hierarchy sharper.

6. Tables and evidence panels should be readable on small screens. Use contained horizontal scroll wrappers or responsive card rows where appropriate. Do not let tables force the entire viewport wider.

7. Improve Plotly loading UX. If Plotly is unavailable, avoid a giant empty chart area as the only feedback. Provide a compact fallback panel with the relevant summary and a clear note. If practical without adding a build step, make the local served dashboard more robust against CDN failure.

8. Clean up visual polish:
   - Consistent spacing scale.
   - 8 px or smaller radius unless an existing component requires otherwise.
   - No nested decorative cards where a simple grid or section would work better.
   - No broken glyphs or encoding artifacts in buttons.
   - Button text must fit at mobile and desktop sizes.

## Implementation Constraints

- Keep the current vanilla HTML/CSS/JavaScript + Plotly architecture. Do not introduce React, Tailwind, a package build, or a new framework.
- Preserve existing data bindings, localStorage keys, chart behavior, collapsible cards, line customization, threshold scanner, and generated JSON placeholders.
- Prefer CSS custom properties and existing template structure.
- Use external dependencies sparingly. If adding icons, use inline SVG with explicit dimensions and accessible labels; do not use emojis as icons.
- Respect `prefers-reduced-motion`.
- Maintain both dark and light themes, but optimize the default dark theme.
- Keep changes scoped to dashboard UI/UX unless a small supporting data/template change is necessary.

## Verification

After implementation:

```powershell
cd "A:\work\trading\cot report\analysis"
py build_interactive_cot_dashboard.py
py serve_interactive_cot_dashboard.py --skip-refresh --open
```

Verify in browser screenshots at:

- 390 x 844 mobile
- 768 x 1024 tablet
- 1440 x 1000 desktop

Acceptance checks:

- No horizontal page scroll on mobile.
- Controls are usable by touch and keyboard.
- Main chart is visible and not clipped.
- Summary cards and scorecards do not overflow.
- Tables are contained and readable.
- Theme toggle still works.
- Collapse/fold controls still work.
- Plotly chart renders when available; fallback is compact and useful when unavailable.
- Text contrast meets WCAG AA for normal text.

## Deliverable

Implement the UI/UX improvements, rebuild the generated dashboard, and provide a short summary of:

- What changed.
- Which files changed.
- What viewport checks were performed.
- Any remaining tradeoffs or data/Plotly limitations.
