"""
NeonTrade AI - Comprehensive System Test
Tests EVERY function of the system against Capital.com LIVE.
"""

import asyncio
import sys
import os
import json
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from broker.capital_client import CapitalClient


# ── Helpers ────────────────────────────────────────────────────────
passed = 0
failed = 0
warnings = 0

def ok(msg):
    global passed
    passed += 1
    print(f"  ✓ {msg}")

def fail(msg):
    global failed
    failed += 1
    print(f"  ✗ {msg}")

def warn(msg):
    global warnings
    warnings += 1
    print(f"  ⚠ {msg}")


async def run_all_tests():
    global passed, failed, warnings

    print("=" * 70)
    print("  NeonTrade AI - Full System Test")
    print(f"  Broker: Capital.com ({settings.capital_environment.upper()})")
    print(f"  Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 70)

    client = CapitalClient(
        api_key=settings.capital_api_key,
        password=settings.capital_password,
        identifier=settings.capital_identifier,
        environment=settings.capital_environment,
    )

    # ════════════════════════════════════════════════════════════════
    # TEST 1: Authentication
    # ════════════════════════════════════════════════════════════════
    print("\n[1] AUTHENTICATION")
    try:
        await client._ensure_session()
        if client._cst and client._security_token:
            ok(f"Session created (CST={client._cst[:8]}...)")
        else:
            fail("Session created but missing tokens")
    except Exception as e:
        fail(f"Auth failed: {e}")
        return

    # ════════════════════════════════════════════════════════════════
    # TEST 2: Account Selection (real vs demo)
    # ════════════════════════════════════════════════════════════════
    print("\n[2] ACCOUNT SELECTION")
    try:
        if client._active_account_id:
            ok(f"Active account: {client._active_account_id}")
        else:
            warn("No active account ID set")

        data = await client._get("/api/v1/accounts")
        accounts = data.get("accounts", [])
        ok(f"Found {len(accounts)} sub-accounts")
        for acct in accounts:
            bal = float(acct.get("balance", {}).get("balance", 0))
            name = acct.get("accountName", "?")
            is_active = "← ACTIVE" if acct.get("accountId") == client._active_account_id else ""
            ok(f"  {name}: ${bal:,.2f} {is_active}")
    except Exception as e:
        fail(f"Account check failed: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 3: Account Summary
    # ════════════════════════════════════════════════════════════════
    print("\n[3] ACCOUNT SUMMARY")
    try:
        summary = await client.get_account_summary()
        ok(f"Balance: {summary.currency} {summary.balance:,.2f}")
        ok(f"Equity: {summary.currency} {summary.equity:,.2f}")
        ok(f"Margin available: {summary.currency} {summary.margin_available:,.2f}")
        ok(f"Open positions: {summary.open_trade_count}")
        balance = summary.balance
    except Exception as e:
        fail(f"Account summary failed: {e}")
        balance = 0

    # ════════════════════════════════════════════════════════════════
    # TEST 4: Instrument Info + Leverage Check
    # ════════════════════════════════════════════════════════════════
    print("\n[4] INSTRUMENT INFO & LEVERAGE")
    instruments_to_check = {
        "EUR_USD": "CURRENCIES",
        "BTC_USD": "CRYPTOCURRENCIES",
        "XAU_USD": "COMMODITIES",  # Gold
    }
    leverage_info = {}
    for inst, expected_type in instruments_to_check.items():
        try:
            info = await client.get_instrument_info(inst)
            epic = info.get("epic", "?")
            margin_factor = info.get("marginFactor")
            margin_unit = info.get("marginFactorUnit", "?")
            dealing = info.get("dealingRules", {})
            min_size = dealing.get("minDealSize", {}).get("value", "?")
            snap = info.get("snapshot", {})
            status = snap.get("marketStatus", "?")

            # Calculate leverage
            if margin_factor and margin_unit == "PERCENTAGE":
                leverage = round(100 / float(margin_factor))
                leverage_info[inst] = {
                    "leverage": leverage,
                    "margin_pct": float(margin_factor),
                    "min_size": min_size,
                }
                ok(f"{inst}: epic={epic}, leverage={leverage}:1, margin={margin_factor}%, min_size={min_size}, status={status}")
            else:
                warn(f"{inst}: margin_factor={margin_factor} {margin_unit}")
                leverage_info[inst] = {"leverage": 1, "margin_pct": 100, "min_size": min_size}
        except Exception as e:
            fail(f"{inst}: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 5: Price Fetching
    # ════════════════════════════════════════════════════════════════
    print("\n[5] PRICE FETCHING")
    eur_price = None
    for inst in ["EUR_USD", "GBP_USD", "XAU_USD"]:
        try:
            price = await client.get_current_price(inst)
            ok(f"{inst}: bid={price.bid:.5f}, ask={price.ask:.5f}, spread={price.spread:.5f}")
            if inst == "EUR_USD":
                eur_price = price
        except Exception as e:
            fail(f"{inst} price failed: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 6: Bulk Prices
    # ════════════════════════════════════════════════════════════════
    print("\n[6] BULK PRICES")
    try:
        bulk = await client.get_prices_bulk(["EUR_USD", "GBP_USD", "USD_JPY"])
        ok(f"Bulk prices returned for {len(bulk)} instruments")
        for inst, p in bulk.items():
            ok(f"  {inst}: {p.bid:.5f}/{p.ask:.5f}")
    except Exception as e:
        fail(f"Bulk prices failed: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 7: Candle Data
    # ════════════════════════════════════════════════════════════════
    print("\n[7] CANDLE DATA")
    for tf in ["D", "H4", "H1", "M5"]:
        try:
            candles = await client.get_candles("EUR_USD", granularity=tf, count=5)
            if candles:
                last = candles[-1]
                ok(f"EUR_USD {tf}: {len(candles)} candles, last close={last.close:.5f}, vol={last.volume}")
            else:
                warn(f"EUR_USD {tf}: empty candle list")
        except Exception as e:
            fail(f"EUR_USD {tf} candles: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 8: Pip Value
    # ════════════════════════════════════════════════════════════════
    print("\n[8] PIP VALUES")
    for inst, expected in [("EUR_USD", 0.0001), ("USD_JPY", 0.01), ("XAU_USD", 0.0001)]:
        try:
            pip = await client.get_pip_value(inst)
            if pip == expected:
                ok(f"{inst}: pip={pip}")
            else:
                warn(f"{inst}: pip={pip} (expected {expected})")
        except Exception as e:
            fail(f"{inst} pip: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 9: Position Sizing Calculation
    # ════════════════════════════════════════════════════════════════
    print("\n[9] POSITION SIZING (1% risk on balance)")
    if eur_price and balance > 0:
        risk_pct = 0.01  # 1%
        risk_amount = balance * risk_pct
        sl_pips = 30  # 30 pips SL
        pip_value_per_unit = 0.0001  # for EUR_USD
        sl_distance = sl_pips * pip_value_per_unit  # 0.003

        # Units = risk_amount / sl_distance
        units = risk_amount / sl_distance
        # With 100:1 leverage, margin needed = units * price / leverage
        lev_info = leverage_info.get("EUR_USD", {})
        leverage = lev_info.get("leverage", 1)
        margin_needed = units * eur_price.ask / leverage
        min_size = lev_info.get("min_size", 100)

        ok(f"Balance: ${balance:.2f}")
        ok(f"Risk amount (1%): ${risk_amount:.4f}")
        ok(f"SL distance: {sl_pips} pips = {sl_distance:.4f}")
        ok(f"Calculated units: {units:.0f}")
        ok(f"Leverage: {leverage}:1")
        ok(f"Margin needed: ${margin_needed:.2f}")
        ok(f"Min deal size: {min_size}")

        if units < float(min_size if min_size != "?" else 100):
            warn(f"Calculated units ({units:.0f}) < min size ({min_size})! Need more capital for proper 1% risk.")
        else:
            ok(f"Position size OK — units ({units:.0f}) >= min size ({min_size})")
    else:
        warn("Skipped — no price/balance data")

    # ════════════════════════════════════════════════════════════════
    # TEST 10: REAL TRADE (open, verify, modify SL, close)
    # ════════════════════════════════════════════════════════════════
    print("\n[10] REAL TRADE LIFECYCLE")
    if eur_price:
        # Use minimum size for safety
        min_sz = leverage_info.get("EUR_USD", {}).get("min_size", 100)
        trade_size = int(min_sz) if min_sz != "?" else 100

        entry = eur_price.ask
        sl = round(entry - 0.0050, 5)  # 50 pips SL
        tp = round(entry + 0.0050, 5)  # 50 pips TP

        print(f"  Opening BUY {trade_size} EUR_USD @ ~{entry:.5f}, SL={sl}, TP={tp}")

        # 10a: Place order
        try:
            result = await client.place_market_order(
                instrument="EUR_USD",
                units=trade_size,
                stop_loss=sl,
                take_profit=tp,
            )
            if result.success:
                ok(f"Trade OPENED: ID={result.trade_id}, fill={result.fill_price}")
            else:
                fail(f"Trade FAILED: {result.error}")
                if result.raw_response:
                    print(f"    Raw: {json.dumps(result.raw_response, indent=2)}")
        except Exception as e:
            fail(f"Trade exception: {e}")
            result = None

        if result and result.success and result.trade_id:
            await asyncio.sleep(1)

            # 10b: Verify in open trades
            try:
                trades = await client.get_open_trades()
                found = any(t.trade_id == result.trade_id for t in trades)
                if found:
                    ok(f"Trade {result.trade_id} found in open positions ({len(trades)} total)")
                else:
                    warn(f"Trade {result.trade_id} NOT found in open positions (may have already closed)")
            except Exception as e:
                fail(f"Get open trades failed: {e}")

            # 10c: Modify SL (move closer)
            try:
                new_sl = round(entry - 0.0040, 5)  # 40 pips instead of 50
                moved = await client.modify_trade_sl(result.trade_id, new_sl)
                if moved:
                    ok(f"SL modified to {new_sl}")
                else:
                    warn(f"SL modification returned False")
            except Exception as e:
                fail(f"Modify SL failed: {e}")

            # 10d: Modify TP
            try:
                new_tp = round(entry + 0.0060, 5)  # 60 pips instead of 50
                moved = await client.modify_trade_tp(result.trade_id, new_tp)
                if moved:
                    ok(f"TP modified to {new_tp}")
                else:
                    warn(f"TP modification returned False")
            except Exception as e:
                fail(f"Modify TP failed: {e}")

            await asyncio.sleep(1)

            # 10e: Close trade
            try:
                closed = await client.close_trade(result.trade_id)
                if closed:
                    ok(f"Trade {result.trade_id} CLOSED successfully")
                else:
                    fail(f"Trade close returned False — CHECK MANUALLY!")
            except Exception as e:
                fail(f"Close trade failed: {e} — CHECK MANUALLY!")

            # 10f: Verify closed
            try:
                await asyncio.sleep(1)
                trades_after = await client.get_open_trades()
                still_open = any(t.trade_id == result.trade_id for t in trades_after)
                if not still_open:
                    ok(f"Trade confirmed closed (not in open positions)")
                else:
                    warn(f"Trade still appears in open positions")
            except Exception as e:
                warn(f"Post-close verification failed: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 11: Limit Order (place and cancel)
    # ════════════════════════════════════════════════════════════════
    print("\n[11] LIMIT ORDER (place + cancel)")
    if eur_price:
        # Place a limit order far from current price (won't fill)
        limit_price = round(eur_price.bid - 0.0200, 5)  # 200 pips below
        limit_sl = round(limit_price - 0.0050, 5)
        limit_tp = round(limit_price + 0.0100, 5)

        try:
            limit_result = await client.place_limit_order(
                instrument="EUR_USD",
                units=100,
                price=limit_price,
                stop_loss=limit_sl,
                take_profit=limit_tp,
                expiry_hours=1,
            )
            if limit_result.success:
                ok(f"Limit order placed @ {limit_price}, ID={limit_result.trade_id}")
                # Cancel it (Capital.com: delete working order)
                await asyncio.sleep(1)
                try:
                    resp = await client._delete(
                        f"/api/v1/workingorders/{limit_result.trade_id}"
                    )
                    ok(f"Limit order cancelled")
                except Exception as e:
                    warn(f"Limit order cancel: {e} (may have expired)")
            else:
                fail(f"Limit order failed: {limit_result.error}")
        except Exception as e:
            fail(f"Limit order exception: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 12: Post-trade Account Summary
    # ════════════════════════════════════════════════════════════════
    print("\n[12] POST-TRADE ACCOUNT CHECK")
    try:
        post_summary = await client.get_account_summary()
        pnl = post_summary.balance - balance
        ok(f"Balance after: {post_summary.currency} {post_summary.balance:,.2f} (P&L: {pnl:+.4f})")
        ok(f"Open positions: {post_summary.open_trade_count}")
    except Exception as e:
        fail(f"Post-trade summary failed: {e}")

    # ════════════════════════════════════════════════════════════════
    # TEST 13: Epic Resolution (spot vs forward)
    # ════════════════════════════════════════════════════════════════
    print("\n[13] EPIC RESOLUTION")
    test_epics = ["EUR_USD", "GBP_USD", "USD_JPY", "XAU_USD", "BTC_USD"]
    for inst in test_epics:
        try:
            epic = await client._resolve_epic(inst)
            expected = inst.replace("_", "")
            # Check it's not a forward (shouldn't have M2026, U2026 suffix)
            is_forward = any(epic.endswith(s) for s in ["M2026", "U2026", "Z2026", "H2027"])
            if is_forward:
                warn(f"{inst} → {epic} (FORWARD! Should be spot)")
            else:
                ok(f"{inst} → {epic}")
        except Exception as e:
            fail(f"{inst} epic resolution: {e}")

    # ════════════════════════════════════════════════════════════════
    # SUMMARY
    # ════════════════════════════════════════════════════════════════
    await client.close()

    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed, {warnings} warnings")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
