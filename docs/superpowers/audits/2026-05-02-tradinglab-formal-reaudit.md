# TradingLab Formal Reaudit - 2026-05-02

Target app: Atlas / NeonTrade AI
Repo state audited: `65c0568` (`Fix auto mode display and watchlist scroll`)
Production target: `https://n8n-neontrade-ai.zb12wf.easypanel.host/`
Local TradingLab corpus: `TradingLab_Notas/`

## Scope

This reaudit checks the executable trading surface against the local TradingLab material:

- 554 total local files under `TradingLab_Notas/`
- 535 text files (`.md` / `.txt`) available for rule extraction
- Trading Plan PDF source: `TradingLab_Notas/Trading Mastery/04_Avanzado/03_Documentacion/TradingPlan_2024.pdf`
- Prior audit baseline: `docs/superpowers/audits/2026-04-17-audit-mentoria.md`

The goal is not to force trades. The goal is to make sure automatic execution only happens when TradingLab strategy, risk, market-hours, news, broker and position-management constraints are satisfied.

## Current Live Capital Assumption

Capital observed in production API and UI: 183.69 USD.

Effective risk budget at that balance:

| Rule | TradingLab value | USD equivalent on 183.69 |
|---|---:|---:|
| Day trading risk | 1.00% | 1.84 USD |
| Scalping risk | 0.50% | 0.92 USD |
| Swing risk | 3.00% | 5.51 USD |
| Correlated trade risk | 0.75% | 1.38 USD |
| Max simultaneous risk | 7.00% | 12.86 USD |

Important operating constraint: `auto_hold_qualified_overnight_positions=false` and `auto_close_overnight_positions=true`, so the system is intentionally biased against overnight financing exposure on the small live account.

## Source Rule Matrix

| Domain | TradingLab rule | Current implementation | Status |
|---|---|---|---|
| Trading style | Default profile is day trading; swing can be used where the asset/context requires it | `settings.trading_style="day_trading"` and `swing_for_equities=true` | PASS |
| Risk per style | Day 1%, scalping 0.5%, swing 3% | `risk_day_trading=0.01`, `risk_scalping=0.005`, `risk_swing=0.03` | PASS |
| Total risk | Max 7% open at once | `max_total_risk=0.07` | PASS |
| Correlated trades | Reduce correlated exposure to 0.75% each | `correlated_risk_pct=0.0075`; equity, crypto, index correlation groups exist | PASS |
| BE trigger | Move to BE halfway to TP1 per written Trading Plan | `be_trigger_method="pct_to_tp1"`, `move_sl_to_be_pct_to_tp1=0.50` | PASS |
| Position management | CP is preferred; after BE wait for structural break before EMA trailing | CP default; `swing_to_break` gate blocks trailing until previous swing breaks | PASS |
| CP trailing | Day-trading CP uses shortest EMAs from plan | CP/day trail = `EMA_M5_5`; emergency exit = `EMA_M5_2` | PASS |
| BLUE targets | TP1 is previous swing extreme; TP_max is EMA 50 H4 except BLUE A extension case | `BlueStrategy.get_tp_levels()` implements swing TP1 and EMA/Fib TP_max | PASS |
| RED targets | TP1 previous extreme; with HTF favor TP_max defaults to Fib 1.0 | `RedStrategy.get_tp_levels()` prioritizes directional Fib 1.0 | PASS |
| WHITE targets | TP behaves like PINK; TP_max is H4 impulse extreme when available | `WhiteStrategy.get_tp_levels()` uses previous swing TP1 and H4 impulse TP_max | PASS |
| BLACK targets | TP is EMA 50 H4; min R:R 2:1 | `BlackStrategy.get_tp_levels()` requires EMA H4; `min_rr_black=2.0` | PASS |
| GREEN crypto | GREEN is enabled for crypto and uses crypto-specific handling | all strategy defaults include `GREEN=true`; crypto-only filters are explicit | PASS |
| EMA 8 weekly | Applies to crypto, not to forex/indices/equities globally | `_check_weekly_ema8_filter()` returns pass-through for non-crypto | PASS |
| SMA 200 | Long-term trend context/filter | `sma_d200` is calculated and contributes to confluence | PASS |
| News filter | Day trading avoids major news; scalping avoids wider window | day 30/30, scalping 60/60, swing 15/5 | PASS |
| Friday / weekend | No new Friday trades after cutoff; weekend closed notice | Friday rules plus `weekend_closed` engine state | PASS |
| Overnight fees | Avoid unattended overnight on small account | automatic out-of-session close enabled; qualified overnight disabled | PASS |
| AUTO mode | AUTO executes valid setups; manual queue is not the active mode | backend `engine_mode=AUTO`; frontend reads `/mode` and shows `AUTO ACTIVO` | PASS |
| Watchlist breadth | Operates full opportunity set when enabled | active categories: forex, forex_exotic, commodities, indices, equities, crypto | PASS |
| Broker surface | Only Capital.com should be connected | runtime broker package contains Capital.com only; production `/api/v1/broker` reports `capital` connected | PASS |
| Scalping | Workshop exists; scalping is riskier and uses 0.50% risk plus wider news filter | code default remains off, production override is currently enabled for the user's requested faster validation; `/api/v1/scalping/status` reports enabled | PASS / USER-REQUESTED |
| Discretion | Alex uses discretion; automated system must avoid discretionary overrides | strict mode enabled; no discretionary override in execution path | PASS |

## Prior 24-Item Audit Closure

The 2026-04-17 audit listed 24 discrepancies. Current status:

| Prior item | Current status | Evidence |
|---:|---|---|
| 1 BLUE TP1 incorrect | CLOSED | `backend/strategies/base.py` TP1 uses nearest swing high/low |
| 2 Post-BE EMA 50 vs EMA 2/5 | CLOSED | `backend/core/position_manager.py` CP/day uses EMA M5 5 + M5 2 exit |
| 3 EMA 8 W global gate | CLOSED | non-crypto pass-through |
| 4 RED Fib target | CLOSED | RED defaults to Fib 1.0 with HTF favor |
| 5 Max total risk 5% | CLOSED | default is 7% |
| 6 Swing risk 1% | CLOSED | default is 3% |
| 7 BE risk-distance default | CLOSED | default is 50% to TP1 |
| 8 Trailing before swing break | CLOSED | BE phase waits for swing break |
| 9 50% risk cut proxy | CLOSED | structural level first, proxy fallback only when swing data missing |
| 10 BLACK blocked by EMA 8 W | CLOSED | non-crypto pass-through fixes BLACK |
| 11 GREEN blocked by EMA 8 W on non-crypto | CLOSED | non-crypto pass-through |
| 12 WHITE TP_max missing H4 impulse | CLOSED | H4 impulse high/low consumed when available |
| 13 BLACK R:R | ACCEPTED | min 2:1 matches explicit minimum |
| 14 Scalping limits not separate | CLOSED | separate scalping max trades/cooldown |
| 15 Scalping BLUE threshold unclear | CLOSED | clean-only requires confidence >= 80 |
| 16 Crypto reentry defaults | ACCEPTED | configurable defaults, not hard rule |
| 17 Scalping news window too short | CLOSED | 60/60 |
| 18 Day news post-window too short | CLOSED | 30/30 |
| 19 Capital.com M2 approximation | ACCEPTED | documented M2 derived from M1 |
| 20 SMA 200 unused | CLOSED | calculated and used in confluence |
| 21 Partial profits | ACCEPTED | default false matches Alex written plan; optional config exists |
| 22 Cooldown reset on win | ACCEPTED | implementation is reasonable and non-critical |
| 23 Friday close | ACCEPTED | closes near SL/TP, keeps mid-range per plan interpretation |
| 24 Scalping R:R | ACCEPTED | workshop examples are aspirational, no explicit hard minimum |

## Production UI Verification From This Round

Observed in production browser after deploy:

- Dashboard shows `AUTO`.
- Dashboard shows broker `capital`.
- Dashboard shows account balance `183.69`.
- Dashboard shows weekend closed state: `Mercado cerrado`.
- Trade tab now uses subtab `Queue`, not `Manual`.
- Queue view shows `AUTO EXECUTION` and `AUTO ACTIVO`.
- Market > Watchlist scrolls; lower instruments are reachable after scroll.
- Watchlist shows one displayed score per instrument; SPX500/USD shows score 95 and `ready_waiting`, meaning high score but still waiting for a valid entry pattern.

## Production API Verification From This Round

Authenticated read-only API smoke against production:

| Endpoint | Result |
|---|---|
| `/health` | online, engine running, mode AUTO, broker capital, database true |
| `/api/v1/status` | running true, mode AUTO, broker capital, startup error empty, open positions 0 |
| `/api/v1/mode` | AUTO, automatic operation description |
| `/api/v1/account` | balance 183.69 USD, equity 183.69 USD |
| `/api/v1/broker` | connected true, broker capital |
| `/api/v1/strategies/config` | BLUE, BLUE_A/B/C, RED, PINK, WHITE, BLACK, GREEN all enabled |
| `/api/v1/watchlist/categories` | forex, forex_exotic, commodities, indices, equities, crypto active |
| `/api/v1/engine-state` | running true; paused reason `weekend_closed`; resumes Monday 07:00 UTC |
| `/api/v1/risk-config` | day 1%, scalping 0.5%, swing 3%, max total risk 7%, CP management |
| `/api/v1/risk-status` | balance 183.69 USD, active risk 0%, max total risk 7% |
| `/api/v1/scalping/status` | enabled true, 30s scan interval, drawdown limits OK |
| `/api/v1/positions` | 0 open positions |
| `/api/v1/news` | reachable; 10 news items returned |
| `/api/v1/calendar` | reachable; 0 current events, no active warning |
| `/api/v1/alerts/config` | Gmail enabled with trade/setup/daily notifications enabled |
| `/api/v1/alerts/test/gmail` | PASS, Gmail test message accepted by production API |

## Non-Negotiable Safety Boundary

No real trade was opened by Codex during this reaudit. Real market execution is a financial transaction. The app can execute automatically when it is running, authenticated, market hours are valid, and a setup passes all rules, but the audit itself uses read-only broker checks and deterministic simulations.

## Remaining Risk / Not A Bug

- A score above 95 is not enough to trade. The execution path also requires a valid strategy setup, entry confirmation, R:R, news clearance, session open, margin availability, and risk budget.
- More frequent trades can be obtained only by loosening TradingLab gates or enabling scalping. That would be a deliberate deviation from the current strict TradingLab/day-trading operating profile.
- No software test can guarantee profitability or "100% no bugs"; tests can only verify defined behaviours.

## Verification Commands

- Backend focused mentoring tests: PASS - 152 passed.
- Backend full pytest: PASS - 1408 passed, 2 xfailed, 3 warnings.
- Frontend Jest: PASS - 52 passed.
- Frontend export: PASS - web bundle generated successfully.
- Production authenticated API smoke: PASS - health, broker, account, mode, risk, strategies, watchlist, scalping, positions, news, calendar and Gmail checked.
- Production UI smoke: PASS - AUTO dashboard, weekend closed banner, Queue/AUTO label, watchlist scroll and single score display verified in browser.
- Legacy broker residue check: PASS - no IBKR/OANDA references in runtime broker/core/api/frontend source or maintained broker tests.
