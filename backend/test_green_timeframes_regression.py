from strategies.base import GreenStrategy


def test_green_crypto_timeframes_resolve_without_nameerror(monkeypatch):
    """Crypto GREEN must resolve style-specific timeframes from the instrument.

    Regression for a bug where _get_green_timeframes() referenced an undefined
    ``analysis`` variable instead of the provided instrument, which could crash
    GREEN on crypto setups before execution.
    """
    from config import settings

    monkeypatch.setattr(settings, "trading_style", "day_trading", raising=False)

    strat = GreenStrategy()
    tf = strat._get_green_timeframes("BTC_USD")

    assert tf == {
        "direction": "H4",
        "pattern": "H1",
        "diagonal": "M15",
        "execution": "M2",
    }


def test_green_forex_timeframes_keep_trading_mastery_layout():
    """Non-crypto GREEN should keep the fixed Trading Mastery layout."""
    strat = GreenStrategy()
    tf = strat._get_green_timeframes("EUR_USD")

    assert tf == {
        "direction": "W",
        "pattern": "D",
        "diagonal": "H1",
        "execution": "M15",
    }
