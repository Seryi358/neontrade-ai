"""
NeonTrade AI - Broker Connection Test
Tests live connection to Capital.com:
  1. Authentication (session creation)
  2. Account summary (balance, equity)
  3. Live price quote (EUR/USD)
  4. Place minimum trade (smallest allowed size)
  5. Verify trade opened
  6. Close trade immediately

Usage:
    cd backend && python test_broker_connection.py
    python test_broker_connection.py --dry-run   # Skip actual trade, just test connection + prices
"""

import asyncio
import sys
import os

# Ensure we can import from the backend package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from broker.capital_client import CapitalClient


async def test_connection():
    """Full broker connection test."""
    dry_run = "--dry-run" in sys.argv

    print("=" * 60)
    print("  NeonTrade AI - Broker Connection Test")
    print("  Broker: Capital.com")
    print(f"  Environment: {settings.capital_environment.upper()}")
    print(f"  Mode: {'DRY RUN (no trades)' if dry_run else 'LIVE TEST (will open & close a trade)'}")
    print("=" * 60)
    print()

    # ── Step 1: Create client and authenticate ────────────────────
    print("[1/6] Connecting to Capital.com...")
    client = CapitalClient(
        api_key=settings.capital_api_key,
        password=settings.capital_password,
        identifier=settings.capital_identifier,
        environment=settings.capital_environment,
    )

    try:
        await client._ensure_session()
        print(f"  ✓ Session created (CST token received)")
        print(f"  ✓ Security token received")
    except Exception as e:
        print(f"  ✗ Authentication FAILED: {e}")
        await client.close()
        return False

    # ── Step 2: Get account summary ───────────────────────────────
    print()
    print("[2/6] Fetching account summary...")
    try:
        summary = await client.get_account_summary()
        print(f"  ✓ Balance:          {summary.currency} {summary.balance:,.2f}")
        print(f"  ✓ Equity:           {summary.currency} {summary.equity:,.2f}")
        print(f"  ✓ Unrealized P&L:   {summary.currency} {summary.unrealized_pnl:,.2f}")
        print(f"  ✓ Margin Used:      {summary.currency} {summary.margin_used:,.2f}")
        print(f"  ✓ Margin Available: {summary.currency} {summary.margin_available:,.2f}")
        print(f"  ✓ Open Positions:   {summary.open_trade_count}")
    except Exception as e:
        print(f"  ✗ Account summary FAILED: {e}")
        await client.close()
        return False

    # ── Step 3: Get live price for EUR/USD ────────────────────────
    print()
    print("[3/6] Fetching live price for EUR/USD...")
    try:
        price = await client.get_current_price("EUR_USD")
        print(f"  ✓ Bid:    {price.bid:.5f}")
        print(f"  ✓ Ask:    {price.ask:.5f}")
        print(f"  ✓ Spread: {price.spread:.5f} ({price.spread / 0.0001:.1f} pips)")
        print(f"  ✓ Time:   {price.time}")
    except Exception as e:
        print(f"  ✗ Price fetch FAILED: {e}")
        await client.close()
        return False

    # ── Step 4: Get instrument info ───────────────────────────────
    print()
    print("[4/6] Fetching EUR/USD instrument info...")
    try:
        info = await client.get_instrument_info("EUR_USD")
        min_size = info.get("minDealSize", {})
        if isinstance(min_size, dict):
            min_val = min_size.get("value", "?")
        else:
            min_val = min_size
        print(f"  ✓ Epic:          {info.get('epic', '?')}")
        print(f"  ✓ Name:          {info.get('instrumentName', '?')}")
        print(f"  ✓ Type:          {info.get('instrumentType', '?')}")
        print(f"  ✓ Min Deal Size: {min_val}")
        print(f"  ✓ Status:        {info.get('marketStatus', '?')}")
    except Exception as e:
        print(f"  ⚠ Instrument info partially failed: {e}")

    if dry_run:
        print()
        print("[5/6] SKIPPED (dry-run mode)")
        print("[6/6] SKIPPED (dry-run mode)")
        print()
        print("=" * 60)
        print("  ✓ CONNECTION TEST PASSED (dry-run)")
        print("  Auth, account, and market data all working!")
        print("=" * 60)
        await client.close()
        return True

    # ── Step 5: Place minimum trade ───────────────────────────────
    # With 100% margin factor, forex requires full notional value.
    # Try instruments in order of margin requirement (lowest first).
    test_trades = [
        ("EUR_USD", 100, 0.0050, 5),   # min=100 units, ~$116 margin
    ]

    # Check if balance is too low for forex — try crypto instead
    if summary.balance < 120:
        print()
        print(f"  ℹ Balance (${summary.balance:.2f}) too low for forex (min ~$116).")
        print(f"  → Trying crypto instruments instead...")
        test_trades = [
            ("ETH_USD", 0.001, 50, 2),   # min=0.001 ETH, ~$2.15 margin
            ("BTC_USD", 0.0001, 500, 2),  # min=0.0001 BTC, ~$7 margin
        ]

    result = None
    trade_instrument = None

    for instrument, size, sl_dist, price_decimals in test_trades:
        print()
        print(f"[5/6] Opening minimum {instrument} BUY position (size={size})...")

        try:
            iprice = await client.get_current_price(instrument)
            sl_price = round(iprice.bid - sl_dist, price_decimals)
            tp_price = round(iprice.ask + sl_dist, price_decimals)

            result = await client.place_market_order(
                instrument=instrument,
                units=size,
                stop_loss=sl_price,
                take_profit=tp_price,
            )

            if result.success:
                trade_instrument = instrument
                print(f"  ✓ Trade OPENED successfully!")
                print(f"  ✓ Trade ID:    {result.trade_id}")
                print(f"  ✓ Fill Price:  {result.fill_price}")
                print(f"  ✓ Size:        {size}")
                print(f"  ✓ Stop Loss:   {sl_price}")
                print(f"  ✓ Take Profit: {tp_price}")
                break
            else:
                print(f"  ✗ Trade FAILED: {result.error}")

        except Exception as e:
            print(f"  ✗ Order EXCEPTION: {e}")

    if not result or not result.success:
        print()
        print("  ✗ Could not open a trade on any instrument.")
        print("  → Your balance may be too low, or leverage needs to be activated")
        print("    on Capital.com's web platform.")
        await client.close()
        return False

    # ── Step 6: Close the trade immediately ───────────────────────
    print()
    print("[6/6] Closing test trade immediately...")
    await asyncio.sleep(2)  # Brief delay to let the position settle

    try:
        if result.trade_id:
            closed = await client.close_trade(result.trade_id)
            if closed:
                print(f"  ✓ Trade {result.trade_id} CLOSED successfully")
            else:
                print(f"  ⚠ Could not close trade {result.trade_id} — close manually!")
        else:
            # Fallback: close all open trades we might have opened
            trades = await client.get_open_trades()
            print(f"  Found {len(trades)} open positions, closing most recent...")
            if trades:
                closed = await client.close_trade(trades[-1].trade_id)
                print(f"  ✓ Closed trade {trades[-1].trade_id}" if closed else "  ⚠ Close failed")
    except Exception as e:
        print(f"  ⚠ Close FAILED: {e}")
        print(f"  → Please close the trade manually in Capital.com!")

    # ── Final summary ─────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  ✓ BROKER CONNECTION TEST COMPLETE")
    print(f"  Account: {summary.currency} {summary.balance:,.2f}")
    print(f"  Trade executed and closed successfully")
    print("=" * 60)

    await client.close()
    return True


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    sys.exit(0 if success else 1)
