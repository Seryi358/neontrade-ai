"""TEST 5: AI Prompt Tests"""
import sys
import pytest
sys.path.insert(0, '.')

openai_analyzer = pytest.importorskip("ai.openai_analyzer", reason="openai not installed — skipping AI prompt tests")
TRADINGLAB_SYSTEM_PROMPT = openai_analyzer.TRADINGLAB_SYSTEM_PROMPT


class TestAIPromptCryptoSpecialization:
    """5.1 CRYPTO SPECIALIZATION section"""

    def test_contains_crypto_specialization(self):
        assert "CRYPTO SPECIALIZATION" in TRADINGLAB_SYSTEM_PROMPT

    def test_mentions_bmsb(self):
        assert "BMSB" in TRADINGLAB_SYSTEM_PROMPT

    def test_mentions_pi_cycle(self):
        assert "Pi Cycle" in TRADINGLAB_SYSTEM_PROMPT

    def test_mentions_ema_8_weekly(self):
        assert ("EMA 8 Weekly" in TRADINGLAB_SYSTEM_PROMPT or
                "EMA 8 weekly" in TRADINGLAB_SYSTEM_PROMPT)


class TestAIPromptGreenStrategy:
    """5.3 GREEN is ONLY crypto strategy"""

    def test_green_is_only_crypto_strategy(self):
        assert ("GREEN is the ONLY" in TRADINGLAB_SYSTEM_PROMPT or
                "GREEN is the only" in TRADINGLAB_SYSTEM_PROMPT)


class TestAIPromptLimitOrders:
    """5.4 Limit order requirements"""

    def test_limit_entry_requires_4_levels(self):
        assert ("4 levels" in TRADINGLAB_SYSTEM_PROMPT or
                "4 levels converge" in TRADINGLAB_SYSTEM_PROMPT or
                "ONLY when 4 levels" in TRADINGLAB_SYSTEM_PROMPT)


class TestAIPromptPartialProfits:
    """5.5 Partial profits description"""

    def test_partial_profits_optional(self):
        lower = TRADINGLAB_SYSTEM_PROMPT.lower()
        assert "optional" in lower and "partial" in lower

    def test_partial_profits_configurable(self):
        assert "configurable" in TRADINGLAB_SYSTEM_PROMPT.lower()
