# Macro Liquidity Plumbing Guard v1.0

## Purpose

The guard is a conservative execution block for severe, corroborated liquidity-plumbing stress.

It can:

- set new exposure to zero;
- change the actionable label to `Wait — Liquidity Plumbing Stress`;
- preserve the underlying COT structural thesis for later re-evaluation.

It cannot:

- create a bullish or bearish direction;
- reverse the Legacy Non-commercial structural sign;
- increase position size;
- override a higher-priority macro risk override or incomplete CFTC release state.

## Configuration

```text
config/macro_liquidity_guard_v1.json
```

Current thresholds:

```text
minimum total source coverage: 60%
severe pillar score:           25 or lower
minimum severe pillars:        2
```

Eligible independent pillars:

```text
funding_microstructure
dealer_absorption
fiscal_cash_flow
auction_absorption
```

## Pillar-specific freshness requirements

A low stored score is not sufficient. The source data supporting that pillar must still be fresh.

### Funding microstructure

Requires at least two fresh independent repo-rate venues among:

```text
DVP overnight/open repo rate
GCF overnight/open repo rate
tri-party overnight/open repo rate
```

DVP transaction volume is useful context but cannot substitute for a second rate venue.

### Dealer absorption

Requires at least two fresh sources among:

```text
primary-dealer Treasury positions
primary-dealer Treasury repo financing
primary-dealer Treasury settlement fails
```

### Daily fiscal cash flow

Requires both:

```text
daily Treasury operating cash / TGA
daily Treasury deposits and withdrawals
```

to be fresh.

### Auction absorption

Requires the official Treasury auction source to be fresh.

Stale or unavailable sources remain visible in the dashboard but cannot activate the guard.

## Activation

The guard activates only when all conditions are true:

1. Overall expanded-source coverage is at least 60%.
2. At least two eligible pillars have enough fresh supporting sources.
3. At least two of those reliable pillars have a score of 25 or lower.

Example:

```text
funding microstructure: 18, fresh across DVP and GCF
 dealer absorption:     22, fresh across positions and financing
 fiscal cash flow:       55
 auction absorption:     48
```

Result:

```text
final action: Wait — Liquidity Plumbing Stress
exposure:     0.00x
COT thesis:   unchanged
```

One severe pillar is not sufficient. A low-coverage dashboard is not sufficient. A stale auction score is not sufficient.

## Priority order

The live decision pipeline applies guards in this order:

1. Existing macro actionability and severe-risk override
2. Expanded liquidity-plumbing guard
3. Historical-evidence exposure cap
4. CFTC release-state guard

The release-state guard has final priority because an incomplete or delayed CFTC report cannot create a new actionable recommendation.

Historical evidence still gets recorded when the plumbing guard is active, but it cannot replace the higher-priority plumbing-stress action text.

## Generated decision fields

Each market decision contains:

```text
liquidity_plumbing_guard
liquidity_plumbing_guard_active
liquidity_plumbing_guard_reliable
```

The full guard object records:

- model version;
- overall source coverage;
- minimum required coverage;
- severe-score threshold;
- number of available pillars;
- severe pillars;
- per-pillar source freshness;
- required and actual fresh-source counts;
- source statuses and explanatory reasons.

## UX

The Market Playbook shows:

```text
Plumbing guard: Inactive
Plumbing guard: Active — blocks exposure
Plumbing guard: Unavailable — insufficient coverage
```

When active, the next-action text explains that exposure remains blocked until fewer than two reliable pillars are severely stressed.

## Validation

Regression coverage includes:

- one severe pillar does not activate;
- two severe fresh pillars activate;
- low overall coverage cannot activate;
- stale auction data cannot activate;
- one repo rate plus DVP volume cannot substitute for two independent rate venues;
- structural COT direction and adjusted COT score remain unchanged;
- macro override and CFTC release priority remain intact;
- historical evidence cannot replace the plumbing-stress action.

The complete local validation gate remains:

```powershell
py refresh_directional_cot_system.py --skip-public-refresh
py refresh_directional_cot_system.py --strict-refresh
```
