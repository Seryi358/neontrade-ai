# Atlas Trading App - Audit Report
**Date:** 2026-04-15
**Account:** Capital.com, $190.88 USD, MANUAL mode

## Trading Style Decision

Based on TradingLab mentorship analysis, switched from **Scalping** to **Day Trading**.

Alex Ruiz (mentor): *"En mi opinion el mejor estilo es Day Trading independientemente de la situacion de cada uno...es el estilo mas equilibrado."*

Alex on scalping for beginners: *"Consideraras que es mucho mejor que empieces por scalping porque vas a ganar mas. Pues la respuesta es no. Vas a perder mas."*

## Commits Deployed (4 total)

| Commit | Description |
|--------|-------------|
| `593a605` | Fix CRITICAL: scalping EMA mapping mismatch with _tf_ema() |
| `e2c7f43` | Fix: 6 critical bugs in scalping strategy detection |
| `8880033` | Config: switch to Day Trading per mentorship |
| `e14079c` | Fix: frontend stuck on Loading (font timeout fallback) |

## Configuration Applied (per mentorship)

| Setting | Value | Source |
|---------|-------|--------|
| trading_style | day_trading | Alex: "el mejor estilo" |
| risk_day_trading | 1% ($1.91/trade) | Ch18.3 Regla del 1% |
| be_trigger_method | risk_distance | Alex: "cuando tengo 1% ganancia" |
| position_management | CP (short-term) | Alex: "salir cuanto antes" |
| max_trades_per_day | 3 | Day trading: quality over quantity |
| cooldown_minutes | 120 | 2h cooldown after 2 consecutive losses |
| max_total_risk | 5% | Conservative for $190 |
| drawdown_method | fixed_levels | 4.12%->0.75%, 6.18%->0.50%, 8.23%->0.25% |
| scalping_enabled | False | Master day trading first |
| strategies | BLUE + RED only | Mentorship: start with these two |
| trading_hours | 07:00-21:00 UTC | London + NY sessions |
| discretion | 0% | Beginners: follow plan exactly |

## Position Sizing for $190.88

- 1% risk = $1.91 per trade
- EUR/USD with 20-pip SL: ~1000 units (rounded from 954)
- Capital.com minimum: 100 units (0.001 lots) - OK
- Margin required at 100:1: ~$11.27 - well within $190.88
- At DD Level 3 (0.25% risk): 218 units - still above minimum

## Tests Passed

### Backend API (17 endpoints)
All endpoints respond correctly: health, price, candles, analysis, status, strategies, logs, diagnostic, account, alerts/test, risk-config, calendar, daily-activity, funded/status, equity-curve, history/stats, mode.

### Frontend UI (5 tabs via Playwright)
Home, Trade, Market, Log, Settings - all load without errors.

### Key Verifications
- Broker: Capital.com connected, session tokens active
- Gmail: OAuth2 working, test email sent successfully
- News Calendar: 5 upcoming events detected (high impact)
- Strategy Detection: AUD_USD RED passes HTF (score sufficient)
- Equity Curve: 178 historical snapshots
- Circuit Breaker: CLOSED, 0 failures

## What Happens When Market Opens (07:00 UTC)

1. Engine starts scanning every 120 seconds
2. Runs full analysis on 10 forex pairs (D->H4->H1->M5)
3. Checks BLUE and RED strategy conditions
4. If setup found: AI validates, calculates position size, queues for approval
5. You get a Gmail alert with the setup details
6. In the app's Trade tab, you approve or reject
7. If approved: order sent to Capital.com
8. Position managed with CP trailing (M5 EMA 50)
9. Break-even moves at 1x risk distance ($1.91 profit)

## Known Limitations

- Font SF Pro Display not in Expo web build (system fonts used as fallback)
- Candle endpoint requires count >= 10
- Some pairs may not pass strategy conditions in ranging markets
- Expect 0-3 setups per day in normal conditions
