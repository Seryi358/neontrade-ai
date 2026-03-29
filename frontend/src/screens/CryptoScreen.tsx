/**
 * NeonTrade AI - Crypto Market Cycle Dashboard
 * Dedicated screen for crypto market analysis from TradingLab Esp. Criptomonedas.
 * Shows: BTC dominance, halving phase, BMSB, Pi Cycle, altcoin season, rotation.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, authFetch } from '../services/api';

// Types
interface CycleData {
  btc_dominance: number | null;
  btc_dominance_trend: string;
  market_phase: string;
  altcoin_season: boolean;
  btc_eth_ratio: number | null;
  btc_eth_trend: string;
  eth_outperforming_btc: boolean;
  rotation_phase: string;
  halving_phase: string;
  halving_phase_description: string;
  halving_sentiment: string;
  btc_rsi_14: number | null;
  ema8_weekly_broken: boolean;
  bmsb_status: string | null;
  bmsb_consecutive_bearish_closes: number;
  pi_cycle_status: string | null;
  sma_d200_position: string | null;
  usdt_dominance_rising: boolean | null;
  golden_cross: boolean;
  death_cross: boolean;
  rsi_diagonal_bearish: boolean;
  rsi_diagonal_bullish: boolean;
  last_updated: string | null;
  error?: string;
}

interface AllocationData {
  trading_pct: number;
  forex_pct: number;
  crypto_pct: number;
  investment_pct: number;
  crypto_default_strategy: string;
  crypto_position_mgmt_style: string;
  memecoins_monitor_only: boolean;
}

// Helpers
const getPhaseColor = (phase: string): string => {
  switch (phase) {
    case 'bull_run': return theme.colors.neonGreen;
    case 'bear_market': return theme.colors.neonRed;
    case 'accumulation': return theme.colors.neonCyan;
    case 'distribution': return theme.colors.neonOrange;
    default: return theme.colors.textMuted;
  }
};

const getPhaseLabel = (phase: string): string => {
  switch (phase) {
    case 'bull_run': return 'BULL RUN';
    case 'bear_market': return 'BEAR MARKET';
    case 'accumulation': return 'ACUMULACION';
    case 'distribution': return 'DISTRIBUCION';
    default: return phase.toUpperCase();
  }
};

const getSentimentColor = (sentiment: string): string => {
  switch (sentiment) {
    case 'very_bullish': return theme.colors.neonGreen;
    case 'bullish': return theme.colors.neonGreen;
    case 'bearish': return theme.colors.neonRed;
    case 'very_bearish': return theme.colors.neonRed;
    default: return theme.colors.textMuted;
  }
};

const getRotationLabel = (phase: string): string => {
  switch (phase) {
    case 'btc': return 'BITCOIN';
    case 'eth': return 'ETHEREUM';
    case 'large_alts': return 'LARGE ALTS';
    case 'small_alts': return 'SMALL ALTS';
    case 'memecoins': return 'MEMECOINS';
    default: return phase.toUpperCase();
  }
};

const getHalvingLabel = (phase: string): string => {
  switch (phase) {
    case 'pre_halving': return 'PRE-HALVING';
    case 'post_halving': return 'POST-HALVING';
    case 'expansion': return 'EXPANSION';
    case 'distribution': return 'DISTRIBUCION';
    default: return phase.toUpperCase();
  }
};

export default function CryptoScreen() {
  const [cycle, setCycle] = useState<CycleData | null>(null);
  const [allocation, setAllocation] = useState<AllocationData | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [cycleRes, allocRes] = await Promise.all([
        authFetch(`${API_URL}/api/v1/crypto/cycle`).catch(() => null),
        authFetch(`${API_URL}/api/v1/crypto/allocation`).catch(() => null),
      ]);
      if (cycleRes?.ok) {
        setCycle(await cycleRes.json());
      }
      if (allocRes?.ok) {
        setAllocation(await allocRes.json());
      }
    } catch (err) {
      setError('Error al cargar datos crypto');
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000); // Update every minute
    return () => clearInterval(interval);
  }, [fetchData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>CRYPTO CYCLE</Text>
        <Text style={styles.subtitle}>MARKET INTELLIGENCE</Text>
      </View>

      {error && (
        <Text style={styles.errorText}>{error}</Text>
      )}

      {/* Market Phase Card — Main indicator */}
      <View style={[styles.card, styles.cardHighlight]}>
        <Text style={styles.cardTitle}>FASE DE MERCADO</Text>
        <Text style={[
          styles.phaseText,
          { color: cycle ? getPhaseColor(cycle.market_phase) : theme.colors.textMuted },
        ]}>
          {cycle ? getPhaseLabel(cycle.market_phase) : '---'}
        </Text>
        {cycle?.halving_phase_description && (
          <Text style={styles.phaseDescription}>
            {cycle.halving_phase_description}
          </Text>
        )}
      </View>

      {/* Halving Cycle */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>HALVING CYCLE</Text>
        <View style={styles.row}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>FASE</Text>
            <Text style={[styles.statValue, { color: theme.colors.cp2077Yellow }]}>
              {cycle ? getHalvingLabel(cycle.halving_phase) : '---'}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>SENTIMIENTO</Text>
            <Text style={[
              styles.statValue,
              { color: cycle ? getSentimentColor(cycle.halving_sentiment) : theme.colors.textMuted },
            ]}>
              {cycle?.halving_sentiment?.toUpperCase() || '---'}
            </Text>
          </View>
        </View>
      </View>

      {/* BTC Dominance */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>BTC DOMINANCE</Text>
        <View style={styles.row}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>BTC.D</Text>
            <Text style={styles.bigValue}>
              {cycle?.btc_dominance != null ? `${cycle.btc_dominance.toFixed(1)}%` : '---'}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>TENDENCIA</Text>
            <Text style={[
              styles.statValue,
              {
                color: cycle?.btc_dominance_trend === 'rising'
                  ? theme.colors.neonGreen
                  : cycle?.btc_dominance_trend === 'falling'
                    ? theme.colors.neonRed
                    : theme.colors.textMuted,
              },
            ]}>
              {cycle?.btc_dominance_trend === 'rising' ? '▲ SUBIENDO'
                : cycle?.btc_dominance_trend === 'falling' ? '▼ BAJANDO'
                : '— ESTABLE'}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>ALTSEASON</Text>
            <Text style={[
              styles.statValue,
              { color: cycle?.altcoin_season ? theme.colors.neonGreen : theme.colors.neonRed },
            ]}>
              {cycle?.altcoin_season ? 'SI' : 'NO'}
            </Text>
          </View>
        </View>
        {cycle?.usdt_dominance_rising != null && (
          <View style={styles.warningRow}>
            <Text style={[
              styles.warningText,
              { color: cycle.usdt_dominance_rising ? theme.colors.neonOrange : theme.colors.neonGreen },
            ]}>
              {cycle.usdt_dominance_rising
                ? 'USDT.D subiendo — capital saliendo a stablecoins (risk-off)'
                : 'USDT.D estable/bajando — capital fluyendo a crypto'}
            </Text>
          </View>
        )}
      </View>

      {/* Capital Rotation */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ROTACION DE CAPITAL</Text>
        <View style={styles.row}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>FASE ACTUAL</Text>
            <Text style={[styles.statValue, { color: theme.colors.neonCyan }]}>
              {cycle ? getRotationLabel(cycle.rotation_phase) : '---'}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>ETH vs BTC</Text>
            <Text style={[
              styles.statValue,
              {
                color: cycle?.eth_outperforming_btc
                  ? theme.colors.neonGreen
                  : theme.colors.neonRed,
              },
            ]}>
              {cycle?.eth_outperforming_btc ? 'ETH LIDERA' : 'BTC LIDERA'}
            </Text>
          </View>
        </View>
        <Text style={styles.rotationHint}>
          BTC → ETH → Large Alts → Small Alts → Memecoins → Corrección
        </Text>
      </View>

      {/* Crypto Indicators */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>INDICADORES CRYPTO</Text>

        {/* BMSB */}
        <View style={styles.indicatorRow}>
          <Text style={styles.indicatorLabel}>BMSB (SMA 20 + EMA 21)</Text>
          <Text style={[
            styles.indicatorValue,
            {
              color: cycle?.bmsb_status === 'bullish'
                ? theme.colors.neonGreen
                : cycle?.bmsb_status === 'bearish'
                  ? theme.colors.neonRed
                  : theme.colors.textMuted,
            },
          ]}>
            {cycle?.bmsb_status?.toUpperCase() || 'N/A'}
          </Text>
        </View>
        {(cycle?.bmsb_consecutive_bearish_closes ?? 0) > 0 && (
          <Text style={styles.indicatorNote}>
            {cycle?.bmsb_consecutive_bearish_closes} cierre(s) semanal(es) bajo BMSB
            {(cycle?.bmsb_consecutive_bearish_closes ?? 0) >= 2 ? ' — CONFIRMADO BEARISH' : ' — esperando confirmación'}
          </Text>
        )}

        {/* Pi Cycle */}
        <View style={styles.indicatorRow}>
          <Text style={styles.indicatorLabel}>Pi Cycle Top/Bottom</Text>
          <Text style={[
            styles.indicatorValue,
            {
              color: cycle?.pi_cycle_status === 'near_top'
                ? theme.colors.neonRed
                : cycle?.pi_cycle_status === 'near_bottom'
                  ? theme.colors.neonGreen
                  : theme.colors.textMuted,
            },
          ]}>
            {cycle?.pi_cycle_status === 'near_top' ? 'CERCA DE TECHO'
              : cycle?.pi_cycle_status === 'near_bottom' ? 'CERCA DE SUELO'
              : 'NEUTRAL'}
          </Text>
        </View>

        {/* EMA 8 Weekly */}
        <View style={styles.indicatorRow}>
          <Text style={styles.indicatorLabel}>EMA 8 Semanal</Text>
          <Text style={[
            styles.indicatorValue,
            { color: cycle?.ema8_weekly_broken ? theme.colors.neonRed : theme.colors.neonGreen },
          ]}>
            {cycle?.ema8_weekly_broken ? 'ROTA (BEARISH)' : 'INTACTA (BULLISH)'}
          </Text>
        </View>

        {/* SMA 200 Daily */}
        <View style={styles.indicatorRow}>
          <Text style={styles.indicatorLabel}>SMA 200 Diaria</Text>
          <Text style={[
            styles.indicatorValue,
            {
              color: cycle?.sma_d200_position === 'above'
                ? theme.colors.neonGreen
                : cycle?.sma_d200_position === 'below'
                  ? theme.colors.neonRed
                  : theme.colors.textMuted,
            },
          ]}>
            {cycle?.sma_d200_position === 'above' ? 'PRECIO ENCIMA'
              : cycle?.sma_d200_position === 'below' ? 'PRECIO DEBAJO'
              : 'N/A'}
          </Text>
        </View>

        {/* Golden/Death Cross */}
        {(cycle?.golden_cross || cycle?.death_cross) && (
          <View style={styles.indicatorRow}>
            <Text style={styles.indicatorLabel}>Cruce SMA 50/200</Text>
            <Text style={[
              styles.indicatorValue,
              { color: cycle.golden_cross ? theme.colors.neonGreen : theme.colors.neonRed },
            ]}>
              {cycle.golden_cross ? 'GOLDEN CROSS' : 'DEATH CROSS'}
            </Text>
          </View>
        )}

        {/* RSI 14 */}
        <View style={styles.indicatorRow}>
          <Text style={styles.indicatorLabel}>RSI 14 (BTC)</Text>
          <Text style={[
            styles.indicatorValue,
            {
              color: (cycle?.btc_rsi_14 ?? 50) > 70
                ? theme.colors.neonRed
                : (cycle?.btc_rsi_14 ?? 50) < 30
                  ? theme.colors.neonGreen
                  : theme.colors.textWhite,
            },
          ]}>
            {cycle?.btc_rsi_14 != null ? cycle.btc_rsi_14.toFixed(1) : '---'}
          </Text>
        </View>

        {/* RSI Diagonal */}
        {(cycle?.rsi_diagonal_bearish || cycle?.rsi_diagonal_bullish) && (
          <View style={styles.indicatorRow}>
            <Text style={styles.indicatorLabel}>RSI Diagonal</Text>
            <Text style={[
              styles.indicatorValue,
              { color: cycle.rsi_diagonal_bullish ? theme.colors.neonGreen : theme.colors.neonRed },
            ]}>
              {cycle.rsi_diagonal_bullish ? 'ACUMULACION (alcista)' : 'DISTRIBUCION (bajista)'}
            </Text>
          </View>
        )}
      </View>

      {/* Allocation */}
      {allocation && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>ASIGNACION CAPITAL</Text>
          <View style={styles.allocationGrid}>
            <View style={styles.allocItem}>
              <Text style={styles.allocPct}>{(allocation.trading_pct * 100).toFixed(0)}%</Text>
              <Text style={styles.allocLabel}>TRADING</Text>
            </View>
            <View style={styles.allocItem}>
              <Text style={styles.allocPct}>{(allocation.investment_pct * 100).toFixed(0)}%</Text>
              <Text style={styles.allocLabel}>INVERSION</Text>
            </View>
          </View>
          <View style={styles.allocBreakdown}>
            <Text style={styles.allocDetail}>
              Trading: {(allocation.forex_pct * 100).toFixed(0)}% Forex · {(allocation.crypto_pct * 100).toFixed(0)}% Crypto
            </Text>
            <Text style={styles.allocDetail}>
              Estrategia crypto: {allocation.crypto_default_strategy} | Gestión: {allocation.crypto_position_mgmt_style.toUpperCase()}
            </Text>
            {allocation.memecoins_monitor_only && (
              <Text style={[styles.allocDetail, { color: theme.colors.neonOrange }]}>
                Memecoins: solo monitoreo (no trading)
              </Text>
            )}
          </View>
        </View>
      )}

      {/* Last Updated */}
      {cycle?.last_updated && (
        <Text style={styles.lastUpdated}>
          Actualizado: {new Date(cycle.last_updated).toLocaleTimeString()}
        </Text>
      )}

      <View style={{ height: 32 }} />
    </ScrollView>
  );
}

// ── Styles ────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    paddingHorizontal: 16,
  },
  header: {
    paddingTop: 48,
    paddingBottom: 16,
    alignItems: 'center',
  },
  title: {
    fontFamily: theme.fonts.heading,
    fontSize: 28,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 8,
    textTransform: 'uppercase',
  },
  subtitle: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.neonCyan,
    letterSpacing: 6,
    textTransform: 'uppercase',
    marginTop: 2,
  },
  errorText: {
    color: theme.colors.neonRed,
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    textAlign: 'center',
    padding: 8,
    letterSpacing: 2,
  },
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.cp2077Yellow,
    borderRadius: theme.borderRadius.sm,
    padding: 16,
    marginBottom: 12,
  },
  cardHighlight: {
    borderLeftColor: theme.colors.neonCyan,
    borderColor: theme.colors.neonCyanDim,
  },
  cardTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 12,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 4,
    textTransform: 'uppercase',
    marginBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingBottom: 6,
  },
  phaseText: {
    fontFamily: theme.fonts.heading,
    fontSize: 32,
    letterSpacing: 6,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  phaseDescription: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 18,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  stat: {
    alignItems: 'center',
    flex: 1,
  },
  statLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  statValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.textWhite,
  },
  bigValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 22,
    color: theme.colors.textWhite,
    fontWeight: '600',
  },
  warningRow: {
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  warningText: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    textAlign: 'center',
    letterSpacing: 1,
  },
  rotationHint: {
    fontFamily: theme.fonts.light,
    fontSize: 10,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: 12,
    letterSpacing: 1,
  },
  indicatorRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  indicatorLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 12,
    color: theme.colors.textSecondary,
    letterSpacing: 1,
  },
  indicatorValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 2,
  },
  indicatorNote: {
    fontFamily: theme.fonts.light,
    fontSize: 10,
    color: theme.colors.neonOrange,
    textAlign: 'right',
    marginTop: -4,
    marginBottom: 4,
    letterSpacing: 1,
  },
  allocationGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: 12,
  },
  allocItem: {
    alignItems: 'center',
  },
  allocPct: {
    fontFamily: theme.fonts.heading,
    fontSize: 28,
    color: theme.colors.neonCyan,
    letterSpacing: 2,
  },
  allocLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 3,
    textTransform: 'uppercase',
  },
  allocBreakdown: {
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: 8,
  },
  allocDetail: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textSecondary,
    textAlign: 'center',
    marginBottom: 4,
    letterSpacing: 1,
  },
  lastUpdated: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    letterSpacing: 2,
  },
});
