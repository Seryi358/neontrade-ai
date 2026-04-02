/**
 * NeonTrade AI - Crypto Market Cycle Dashboard
 * Dedicated screen for crypto market analysis from TradingLab Esp. Criptomonedas.
 * CyberPunk 2077 HUD redesign with sub-navigation pills.
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
const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);
import {
  HUDCard,
  HUDHeader,
  HUDSectionTitle,
  HUDStatRow,
  HUDBadge,
  HUDDivider,
  SubNavPills,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
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

const SUB_NAV_OPTIONS = [
  { key: 'watchlist', label: 'WATCHLIST' },
  { key: 'crypto', label: 'CRYPTO' },
];

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
    const interval = setInterval(fetchData, 60000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  // Rotation flow active step
  const rotationSteps = ['BTC', 'ETH', 'ALTS', 'SMALL', 'MEME'];
  const rotationMap: Record<string, number> = {
    btc: 0, eth: 1, large_alts: 2, small_alts: 3, memecoins: 4,
  };
  const activeRotationIdx = cycle ? (rotationMap[cycle.rotation_phase] ?? -1) : -1;

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Sub-navigation pills */}
      <View style={styles.topPadding}>
        <SubNavPills
          options={SUB_NAV_OPTIONS}
          activeKey="crypto"
          onSelect={() => {}}
        />
      </View>

      {error && <ErrorState message={error} />}

      {/* ── Market Phase Card ── */}
      <HUDCard accentColor={cycle ? getPhaseColor(cycle.market_phase) : theme.colors.neonCyan}>
        <HUDSectionTitle title="FASE DE MERCADO" color={theme.colors.neonCyan} />
        <View style={styles.phaseCenter}>
          <HUDBadge
            label={cycle ? getPhaseLabel(cycle.market_phase) : '---'}
            color={cycle ? getPhaseColor(cycle.market_phase) : theme.colors.textMuted}
          />
        </View>
        {cycle?.halving_sentiment && (
          <Text style={[styles.sentimentText, { color: getSentimentColor(cycle.halving_sentiment) }]}>
            SENTIMIENTO: {cycle.halving_sentiment.toUpperCase().replace('_', ' ')}
          </Text>
        )}
        {cycle?.halving_phase_description && (
          <Text style={styles.phaseDescription}>{cycle.halving_phase_description}</Text>
        )}
      </HUDCard>

      {/* ── Halving Cycle Card ── */}
      <HUDCard>
        <HUDSectionTitle title="HALVING CYCLE" />
        <HUDStatRow
          label="FASE"
          value={cycle ? getHalvingLabel(cycle.halving_phase) : '---'}
          valueColor={theme.colors.cp2077Yellow}
        />
        <HUDStatRow
          label="SENTIMIENTO"
          value={cycle?.halving_sentiment?.toUpperCase().replace('_', ' ') || '---'}
          valueColor={cycle ? getSentimentColor(cycle.halving_sentiment) : theme.colors.textMuted}
        />
      </HUDCard>

      {/* ── BTC Dominance Card ── */}
      <HUDCard>
        <HUDSectionTitle title="BTC DOMINANCE" />
        <View style={styles.bigValueRow}>
          <Text style={styles.bigNumber}>
            {cycle?.btc_dominance != null ? `${cycle.btc_dominance.toFixed(1)}%` : '---'}
          </Text>
          <Text style={[styles.trendArrow, {
            color: cycle?.btc_dominance_trend === 'rising'
              ? theme.colors.neonGreen
              : cycle?.btc_dominance_trend === 'falling'
                ? theme.colors.neonRed
                : theme.colors.textMuted,
          }]}>
            {cycle?.btc_dominance_trend === 'rising' ? '  ▲' : cycle?.btc_dominance_trend === 'falling' ? '  ▼' : '  —'}
          </Text>
        </View>

        <HUDDivider />

        <View style={styles.badgeRow}>
          <HUDBadge
            label={cycle?.altcoin_season ? 'ALTSEASON' : 'NO ALTSEASON'}
            color={cycle?.altcoin_season ? theme.colors.neonGreen : theme.colors.neonRed}
          />
          {cycle?.usdt_dominance_rising != null && (
            <HUDBadge
              label={cycle.usdt_dominance_rising ? 'RISK-OFF' : 'RISK-ON'}
              color={cycle.usdt_dominance_rising ? theme.colors.neonOrange : theme.colors.neonGreen}
            />
          )}
        </View>

        {cycle?.usdt_dominance_rising != null && (
          <Text style={[styles.warningNote, {
            color: cycle.usdt_dominance_rising ? theme.colors.neonOrange : theme.colors.neonGreen,
          }]}>
            {cycle.usdt_dominance_rising
              ? 'USDT.D subiendo — capital saliendo a stablecoins'
              : 'USDT.D estable/bajando — capital fluyendo a crypto'}
          </Text>
        )}
      </HUDCard>

      {/* ── Capital Rotation Card ── */}
      <HUDCard>
        <HUDSectionTitle title="ROTACION DE CAPITAL" color={theme.colors.neonCyan} />

        {/* Flow diagram */}
        <View style={styles.rotationFlow}>
          {rotationSteps.map((step, idx) => (
            <React.Fragment key={step}>
              <View style={[
                styles.rotationNode,
                activeRotationIdx === idx && styles.rotationNodeActive,
              ]}>
                <Text style={[
                  styles.rotationNodeText,
                  activeRotationIdx === idx && styles.rotationNodeTextActive,
                ]}>
                  {step}
                </Text>
              </View>
              {idx < rotationSteps.length - 1 && (
                <Text style={styles.rotationArrow}>→</Text>
              )}
            </React.Fragment>
          ))}
        </View>

        <HUDDivider />

        <HUDStatRow
          label="FASE ACTUAL"
          value={cycle ? getRotationLabel(cycle.rotation_phase) : '---'}
          valueColor={theme.colors.neonCyan}
        />
        <HUDStatRow
          label="ETH vs BTC"
          value={cycle?.eth_outperforming_btc ? 'ETH LIDERA' : 'BTC LIDERA'}
          valueColor={cycle?.eth_outperforming_btc ? theme.colors.neonGreen : theme.colors.neonRed}
        />
      </HUDCard>

      {/* ── Crypto Indicators Grid ── */}
      <HUDCard>
        <HUDSectionTitle title="INDICADORES CRYPTO" />

        <View style={styles.indicatorGrid}>
          {/* BMSB */}
          <View style={styles.indicatorCell}>
            <Text style={styles.indicatorTitle}>BMSB</Text>
            <Text style={styles.indicatorSubtitle}>SMA 20 + EMA 21</Text>
            <HUDBadge
              label={cycle?.bmsb_status?.toUpperCase() || 'N/A'}
              color={
                cycle?.bmsb_status === 'bullish' ? theme.colors.neonGreen
                  : cycle?.bmsb_status === 'bearish' ? theme.colors.neonRed
                  : theme.colors.textMuted
              }
            />
            {(cycle?.bmsb_consecutive_bearish_closes ?? 0) > 0 && (
              <Text style={styles.indicatorNote}>
                {cycle?.bmsb_consecutive_bearish_closes} cierre(s) bajo BMSB
                {(cycle?.bmsb_consecutive_bearish_closes ?? 0) >= 2 ? ' CONFIRM' : ''}
              </Text>
            )}
          </View>

          {/* Pi Cycle */}
          <View style={styles.indicatorCell}>
            <Text style={styles.indicatorTitle}>PI CYCLE</Text>
            <Text style={styles.indicatorSubtitle}>Top / Bottom</Text>
            <HUDBadge
              label={
                cycle?.pi_cycle_status === 'near_top' ? 'CERCA TECHO'
                  : cycle?.pi_cycle_status === 'near_bottom' ? 'CERCA SUELO'
                  : 'NEUTRAL'
              }
              color={
                cycle?.pi_cycle_status === 'near_top' ? theme.colors.neonRed
                  : cycle?.pi_cycle_status === 'near_bottom' ? theme.colors.neonGreen
                  : theme.colors.textMuted
              }
            />
          </View>

          {/* EMA 8 Weekly */}
          <View style={styles.indicatorCell}>
            <Text style={styles.indicatorTitle}>EMA 8 WEEKLY</Text>
            <Text style={styles.indicatorSubtitle}>Soporte semanal</Text>
            <HUDBadge
              label={cycle?.ema8_weekly_broken ? 'ROTA' : 'INTACTA'}
              color={cycle?.ema8_weekly_broken ? theme.colors.neonRed : theme.colors.neonGreen}
            />
          </View>

          {/* SMA 200 Daily */}
          <View style={styles.indicatorCell}>
            <Text style={styles.indicatorTitle}>SMA 200 D</Text>
            <Text style={styles.indicatorSubtitle}>Tendencia largo plazo</Text>
            <HUDBadge
              label={
                cycle?.sma_d200_position === 'above' ? 'ENCIMA'
                  : cycle?.sma_d200_position === 'below' ? 'DEBAJO'
                  : 'N/A'
              }
              color={
                cycle?.sma_d200_position === 'above' ? theme.colors.neonGreen
                  : cycle?.sma_d200_position === 'below' ? theme.colors.neonRed
                  : theme.colors.textMuted
              }
            />
            {(cycle?.golden_cross || cycle?.death_cross) && (
              <HUDBadge
                label={cycle?.golden_cross ? 'GOLDEN CROSS' : 'DEATH CROSS'}
                color={cycle?.golden_cross ? theme.colors.neonGreen : theme.colors.neonRed}
                small
              />
            )}
          </View>

          {/* RSI 14 Daily */}
          <View style={styles.indicatorCell}>
            <Text style={styles.indicatorTitle}>RSI 14</Text>
            <Text style={styles.indicatorSubtitle}>BTC Daily</Text>
            <Text style={[styles.rsiValue, {
              color: (cycle?.btc_rsi_14 ?? 50) > 70
                ? theme.colors.neonRed
                : (cycle?.btc_rsi_14 ?? 50) < 30
                  ? theme.colors.neonGreen
                  : theme.colors.textWhite,
            }]}>
              {cycle?.btc_rsi_14 != null ? cycle.btc_rsi_14.toFixed(1) : '---'}
            </Text>
            {(cycle?.btc_rsi_14 ?? 50) > 70 && <HUDBadge label="SOBRECOMPRA" color={theme.colors.neonRed} small />}
            {(cycle?.btc_rsi_14 ?? 50) < 30 && <HUDBadge label="SOBREVENTA" color={theme.colors.neonGreen} small />}
            {(cycle?.rsi_diagonal_bearish || cycle?.rsi_diagonal_bullish) && (
              <HUDBadge
                label={cycle?.rsi_diagonal_bullish ? 'DIAG ALCISTA' : 'DIAG BAJISTA'}
                color={cycle?.rsi_diagonal_bullish ? theme.colors.neonGreen : theme.colors.neonRed}
                small
              />
            )}
          </View>

          {/* Placeholder for even grid */}
          <View style={styles.indicatorCell} />
        </View>
      </HUDCard>

      {/* ── Capital Allocation ── */}
      {allocation && (
        <HUDCard>
          <HUDSectionTitle title="ASIGNACION CAPITAL" />

          <View style={styles.allocationRow}>
            <View style={styles.allocItem}>
              <Text style={styles.allocPct}>{(allocation.trading_pct * 100).toFixed(0)}%</Text>
              <Text style={styles.allocLabel}>TRADING</Text>
            </View>
            <View style={styles.allocDivider} />
            <View style={styles.allocItem}>
              <Text style={styles.allocPct}>{(allocation.investment_pct * 100).toFixed(0)}%</Text>
              <Text style={styles.allocLabel}>INVERSION</Text>
            </View>
          </View>

          <HUDDivider />

          <HUDStatRow
            label="FOREX"
            value={`${(allocation.forex_pct * 100).toFixed(0)}%`}
            valueColor={theme.colors.textSecondary}
          />
          <HUDStatRow
            label="CRYPTO"
            value={`${(allocation.crypto_pct * 100).toFixed(0)}%`}
            valueColor={theme.colors.neonCyan}
          />
          <HUDStatRow
            label="ESTRATEGIA"
            value={allocation.crypto_default_strategy}
            valueColor={theme.colors.cp2077Yellow}
          />
          <HUDStatRow
            label="GESTION"
            value={(allocation.crypto_position_mgmt_style || 'cp').toUpperCase()}
            valueColor={theme.colors.textSecondary}
          />
          {allocation.memecoins_monitor_only && (
            <View style={{ marginTop: 6 }}>
              <HUDBadge label="MEMECOINS: SOLO MONITOREO" color={theme.colors.neonOrange} small />
            </View>
          )}
        </HUDCard>
      )}

      {/* Last Updated */}
      {cycle?.last_updated && (
        <Text style={styles.lastUpdated}>
          ACTUALIZADO: {new Date(cycle.last_updated).toLocaleTimeString()}
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
    paddingHorizontal: theme.spacing.md,
  },
  topPadding: {
    paddingTop: theme.spacing.lg,
  },

  // Phase card
  phaseCenter: {
    alignItems: 'center',
    marginVertical: theme.spacing.sm,
  },
  sentimentText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    textAlign: 'center',
    letterSpacing: 2,
    marginTop: 6,
  },
  phaseDescription: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    lineHeight: 18,
  },

  // Big value
  bigValueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'center',
    marginVertical: theme.spacing.sm,
  },
  bigNumber: {
    fontFamily: theme.fonts.mono,
    fontSize: 32,
    color: theme.colors.textWhite,
    fontWeight: '600',
  },
  trendArrow: {
    fontFamily: theme.fonts.heading,
    fontSize: 22,
  },

  // Badge row
  badgeRow: {
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
    marginTop: theme.spacing.xs,
  },
  warningNote: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    textAlign: 'center',
    letterSpacing: 1,
    marginTop: 8,
  },

  // Rotation flow
  rotationFlow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: theme.spacing.sm,
    flexWrap: 'wrap',
    gap: 2,
  },
  rotationNode: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.sm,
  },
  rotationNodeActive: {
    borderColor: theme.colors.neonCyan,
    backgroundColor: 'rgba(93, 244, 254, 0.15)',
  },
  rotationNodeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  rotationNodeTextActive: {
    color: theme.colors.neonCyan,
  },
  rotationArrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.cp2077YellowDim,
    marginHorizontal: 2,
  },

  // Indicator grid
  indicatorGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  indicatorCell: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: theme.colors.backgroundLight,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    gap: 4,
  },
  indicatorTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 2,
  },
  indicatorSubtitle: {
    fontFamily: theme.fonts.light,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    marginBottom: 4,
  },
  indicatorNote: {
    fontFamily: theme.fonts.light,
    fontSize: 9,
    color: theme.colors.neonOrange,
    marginTop: 2,
    letterSpacing: 1,
  },
  rsiValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 20,
    fontWeight: '600',
  },

  // Allocation
  allocationRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 24,
    marginVertical: theme.spacing.sm,
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
  allocDivider: {
    width: 1,
    height: 36,
    backgroundColor: theme.colors.border,
  },

  // Last updated
  lastUpdated: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: 8,
    letterSpacing: 2,
  },
});
