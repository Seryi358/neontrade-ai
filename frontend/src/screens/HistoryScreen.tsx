/**
 * Atlas - History Screen
 * Trade history with performance stats and filtering by strategy color.
 * CyberPunk 2077 HUD redesign with sub-navigation pills.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ScrollView,
} from 'react-native';
import { theme } from '../theme/apple-glass';

const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);
import {
  HUDCard,
  HUDSectionTitle,
  HUDStatRow,
  HUDBadge,
  HUDDivider,
  SubNavPills,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
import { API_URL, authFetch, STRATEGY_COLORS } from '../services/api';

// Types
interface Trade {
  id: string;
  instrument: string;
  strategy_color: string;
  direction: 'BUY' | 'SELL';
  entry_price: number;
  exit_price: number;
  pnl: number;
  closed_at: string;
  mode: 'AUTO' | 'MANUAL';
}

interface HistoryStats {
  total_trades: number;
  win_rate: number;
  total_pnl: number;
  best_trade: number;
  worst_trade: number;
  avg_risk_reward?: number;
  winning_trades?: number;
  losing_trades?: number;
}

const STRATEGY_FILTERS = [
  { key: 'ALL', label: 'ALL', color: theme.colors.textWhite },
  { key: 'BLUE', label: 'BLUE', color: STRATEGY_COLORS.BLUE },
  { key: 'RED', label: 'RED', color: STRATEGY_COLORS.RED },
  { key: 'PINK', label: 'PINK', color: STRATEGY_COLORS.PINK },
  { key: 'WHITE', label: 'WHITE', color: STRATEGY_COLORS.WHITE },
  { key: 'BLACK', label: 'BLACK', color: STRATEGY_COLORS.BLACK },
  { key: 'GREEN', label: 'GREEN', color: STRATEGY_COLORS.GREEN },
];

const getStrategyDotColor = (color: string): string => {
  return STRATEGY_COLORS[color?.toUpperCase()] || theme.colors.textMuted;
};

const SUB_NAV_OPTIONS = [
  { key: 'history', label: 'HISTORY' },
  { key: 'journal', label: 'JOURNAL' },
];

export default function HistoryScreen() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [stats, setStats] = useState<HistoryStats | null>(null);
  const [activeFilter, setActiveFilter] = useState('ALL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const strategyParam = activeFilter !== 'ALL' ? `&strategy=${activeFilter}` : '';
      const [tradesRes, statsRes] = await Promise.all([
        authFetch(`${API_URL}/api/v1/history?limit=200${strategyParam}`),
        authFetch(`${API_URL}/api/v1/history/stats?days=90`),
      ]);

      if (!tradesRes.ok || !statsRes.ok) {
        throw new Error('Error al cargar datos');
      }

      setTrades(await tradesRes.json());
      setStats(await statsRes.json());
    } catch (err) {
      console.error('Failed to fetch history:', err);
      setError('No se pudo conectar al servidor');
    } finally {
      setLoading(false);
    }
  }, [activeFilter]);

  useEffect(() => {
    setLoading(true);
    fetchData();
  }, [fetchData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('es-CO', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  // ── Performance Summary ─────────────────────────────────────────
  const renderPerformanceSummary = () => {
    if (!stats) return null;

    const avgRR = stats.avg_risk_reward && stats.avg_risk_reward > 0
      ? stats.avg_risk_reward.toFixed(2)
      : '---';

    return (
      <HUDCard accentColor={theme.colors.neonCyan}>
        <HUDSectionTitle title="RENDIMIENTO (30 DIAS)" color={theme.colors.neonCyan} />
        <HUDStatRow
          label="TRADES"
          value={stats.total_trades}
          valueColor={theme.colors.textWhite}
        />
        <HUDStatRow
          label="WIN RATE"
          value={`${safe(stats.win_rate, 1)}%`}
          valueColor={stats.win_rate >= 50 ? theme.colors.profit : theme.colors.loss}
        />
        <HUDStatRow
          label="P&L TOTAL"
          value={`$${safe(stats.total_pnl)}`}
          valueColor={stats.total_pnl >= 0 ? theme.colors.profit : theme.colors.loss}
          large
        />
        <HUDStatRow
          label="AVG R:R"
          value={avgRR}
          valueColor={theme.colors.cp2077Yellow}
        />
      </HUDCard>
    );
  };

  // ── Strategy Filter Bar ─────────────────────────────────────────
  const renderFilterBar = () => (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.filterScroll}
    >
      {STRATEGY_FILTERS.map((f) => (
        <TouchableOpacity
          key={f.key}
          style={[
            styles.filterPill,
            activeFilter === f.key && styles.filterPillActive,
            activeFilter === f.key && f.key !== 'ALL' && { borderColor: f.color, backgroundColor: `${f.color}18` },
          ]}
          onPress={() => setActiveFilter(f.key)}
        >
          {f.key !== 'ALL' && (
            <View style={[styles.filterDot, { backgroundColor: f.color }]} />
          )}
          <Text style={[
            styles.filterLabel,
            activeFilter === f.key && styles.filterLabelActive,
            activeFilter === f.key && f.key !== 'ALL' && { color: f.color },
          ]}>
            {f.label}
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  // ── Trade Item ──────────────────────────────────────────────────
  const renderTradeItem = ({ item }: { item: Trade }) => (
    <HUDCard
      accentColor={getStrategyDotColor(item.strategy_color)}
    >
      {/* Row 1: Strategy dot + instrument + date */}
      <View style={styles.tradeTopRow}>
        <View style={styles.tradeLeft}>
          <View style={styles.tradeInstrumentRow}>
            <View style={[styles.strategyDot, { backgroundColor: getStrategyDotColor(item.strategy_color) }]} />
            <Text style={styles.tradeInstrument}>
              {item.instrument.replace('_', '/')}
            </Text>
          </View>
          <Text style={styles.tradeDate}>{formatDate(item.closed_at)}</Text>
        </View>

        {/* P&L (large, colored) */}
        <Text style={[styles.tradePnl, {
          color: item.pnl >= 0 ? theme.colors.profit : theme.colors.loss,
        }]}>
          {item.pnl >= 0 ? '+' : ''}${safe(item.pnl)}
        </Text>
      </View>

      {/* Row 2: Direction badge + Mode badge + prices */}
      <View style={styles.tradeBottomRow}>
        <View style={styles.tradeBadges}>
          <HUDBadge
            label={item.direction}
            color={item.direction === 'BUY' ? theme.colors.profit : theme.colors.loss}
            small
          />
          <HUDBadge
            label={item.mode}
            color={theme.colors.textMuted}
            small
          />
        </View>
        <Text style={styles.tradePrices}>
          {safe(item.entry_price, 5)} → {safe(item.exit_price, 5)}
        </Text>
      </View>
    </HUDCard>
  );

  // ── Loading State ───────────────────────────────────────────────
  if (loading) {
    return (
      <View style={styles.centeredContainer}>
        <LoadingState message="Cargando historial..." />
      </View>
    );
  }

  // ── Error State ─────────────────────────────────────────────────
  if (error && trades.length === 0) {
    return (
      <View style={styles.centeredContainer}>
        <SubNavPills options={SUB_NAV_OPTIONS} activeKey="history" onSelect={() => {}} />
        <ErrorState message={error} onRetry={fetchData} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Sub-navigation pills */}
      <SubNavPills options={SUB_NAV_OPTIONS} activeKey="history" onSelect={() => {}} />

      {renderPerformanceSummary()}
      {renderFilterBar()}

      {trades.length > 0 ? (
        <FlatList
          data={trades}
          keyExtractor={(item) => item.id}
          renderItem={renderTradeItem}
          style={styles.list}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
        />
      ) : (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyIcon}>▤</Text>
          <Text style={styles.emptyText}>No hay historial de operaciones</Text>
          <Text style={styles.emptySubtext}>
            Las operaciones cerradas apareceran aqui
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.md,
    paddingTop: theme.spacing.lg,
  },
  centeredContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.md,
  },
  list: {
    flex: 1,
  },

  // Filter bar
  filterScroll: {
    paddingBottom: theme.spacing.md,
    gap: 6,
  },
  filterPill: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: theme.borderRadius.round,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 5,
  },
  filterPillActive: {
    borderColor: theme.colors.cp2077Yellow,
    backgroundColor: 'rgba(93, 244, 254, 0.12)',
  },
  filterDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  filterLabel: {
    fontFamily: theme.fonts.heading,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  filterLabelActive: {
    color: theme.colors.cp2077Yellow,
  },

  // Trade items
  tradeTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  tradeLeft: {
    flex: 1,
  },
  tradeInstrumentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  strategyDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 4,
    elevation: 4,
  },
  tradeInstrument: {
    fontFamily: theme.fonts.heading,
    fontSize: 16,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  tradeDate: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    marginTop: 2,
    marginLeft: 18,
  },
  tradePnl: {
    fontFamily: theme.fonts.mono,
    fontSize: 20,
    fontWeight: 'bold',
  },
  tradeBottomRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  tradeBadges: {
    flexDirection: 'row',
    gap: 6,
  },
  tradePrices: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },

  // Empty state
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: theme.spacing.xxl,
  },
  emptyIcon: {
    fontSize: 48,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.md,
  },
  emptyText: {
    fontFamily: theme.fonts.primary,
    fontSize: 14,
    color: theme.colors.textMuted,
    textAlign: 'center',
  },
  emptySubtext: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    opacity: 0.6,
  },
});
