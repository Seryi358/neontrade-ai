/**
 * NeonTrade AI - History Screen
 * Trade history with performance stats and filtering by strategy color.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
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
        authFetch(`${API_URL}/api/v1/history?limit=50${strategyParam}`),
        authFetch(`${API_URL}/api/v1/history/stats?days=30`),
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

  const renderStatsCard = () => {
    if (!stats) return null;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>RENDIMIENTO (30 DIAS)</Text>
        <View style={styles.statsGrid}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>TRADES</Text>
            <Text style={styles.statValue}>{stats.total_trades}</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>WIN RATE</Text>
            <Text style={[
              styles.statValue,
              stats.win_rate >= 50 ? styles.profit : styles.loss,
            ]}>
              {stats.win_rate.toFixed(1)}%
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>P&L TOTAL</Text>
            <Text style={[
              styles.statValue,
              stats.total_pnl >= 0 ? styles.profit : styles.loss,
            ]}>
              ${stats.total_pnl.toFixed(2)}
            </Text>
          </View>
        </View>
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>MEJOR TRADE</Text>
            <Text style={[styles.statValueSm, styles.profit]}>
              +${stats.best_trade.toFixed(2)}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>PEOR TRADE</Text>
            <Text style={[styles.statValueSm, styles.loss]}>
              ${stats.worst_trade.toFixed(2)}
            </Text>
          </View>
        </View>
      </View>
    );
  };

  const renderFilterBar = () => (
    <View style={styles.filterBar}>
      {STRATEGY_FILTERS.map((f) => (
        <TouchableOpacity
          key={f.key}
          style={[
            styles.filterTab,
            activeFilter === f.key && styles.filterTabActive,
          ]}
          onPress={() => setActiveFilter(f.key)}
        >
          {f.key !== 'ALL' && (
            <View style={[styles.filterDot, { backgroundColor: f.color }]} />
          )}
          <Text style={[
            styles.filterLabel,
            activeFilter === f.key && styles.filterLabelActive,
          ]}>
            {f.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderTradeItem = ({ item }: { item: Trade }) => (
    <View style={styles.tradeItem}>
      <View style={styles.tradeHeader}>
        <View style={styles.tradeLeft}>
          <View style={styles.tradeInstrumentRow}>
            <View style={[styles.strategyDot, { backgroundColor: getStrategyDotColor(item.strategy_color) }]} />
            <Text style={styles.tradeInstrument}>
              {item.instrument.replace('_', '/')}
            </Text>
          </View>
          <View style={styles.tradeTagsRow}>
            <Text style={[
              styles.tradeDirection,
              item.direction === 'BUY' ? styles.profit : styles.loss,
            ]}>
              {item.direction}
            </Text>
            <View style={styles.modeBadge}>
              <Text style={styles.modeBadgeText}>{item.mode}</Text>
            </View>
          </View>
        </View>
        <View style={styles.tradeRight}>
          <Text style={[
            styles.tradePnl,
            item.pnl >= 0 ? styles.profit : styles.loss,
          ]}>
            {item.pnl >= 0 ? '+' : ''}${item.pnl.toFixed(2)}
          </Text>
          <Text style={styles.tradeDate}>{formatDate(item.closed_at)}</Text>
        </View>
      </View>
      <View style={styles.tradePrices}>
        <Text style={styles.tradePriceText}>
          {item.entry_price.toFixed(5)} → {item.exit_price.toFixed(5)}
        </Text>
      </View>
    </View>
  );

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.cp2077Yellow} />
        <Text style={styles.loadingText}>Cargando historial...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorIcon}>⚠</Text>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={fetchData}>
          <Text style={styles.retryBtnText}>REINTENTAR</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.header}>HISTORIAL</Text>
      <Text style={styles.subheader}>Operaciones cerradas</Text>

      {error && <Text style={{color: theme.colors.neonRed, fontFamily: theme.fonts.primary, fontSize: 11, textAlign: 'center', padding: 8, letterSpacing: 2}}>{error}</Text>}

      {renderStatsCard()}
      {renderFilterBar()}

      {trades.length > 0 ? (
        <FlatList
          data={trades}
          keyExtractor={(item) => item.id}
          renderItem={renderTradeItem}
          style={styles.list}
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
  },
  centered: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.md,
  },
  header: {
    fontFamily: theme.fonts.heading,
    fontSize: 20,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 4,
    marginTop: theme.spacing.lg,
  },
  subheader: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: theme.spacing.md,
  },
  // Stats card
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.cp2077Yellow,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
  },
  cardTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 3,
    marginBottom: theme.spacing.sm,
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.sm,
  },
  stat: {
    alignItems: 'center',
    flex: 1,
  },
  statLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  statValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.textSecondary,
    marginTop: 4,
  },
  statValueSm: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    marginTop: 4,
  },
  profit: {
    color: theme.colors.profit,
  },
  loss: {
    color: theme.colors.loss,
  },
  // Filter bar
  filterBar: {
    flexDirection: 'row',
    marginBottom: theme.spacing.md,
    flexWrap: 'wrap',
    gap: 6,
  },
  filterTab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: theme.borderRadius.round,
    borderWidth: 1,
    borderColor: theme.colors.border,
    gap: 4,
  },
  filterTabActive: {
    borderColor: theme.colors.cp2077Yellow,
    backgroundColor: 'rgba(252, 238, 9, 0.15)',
  },
  filterDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  filterLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  filterLabelActive: {
    color: theme.colors.cp2077Yellow,
  },
  // Trade list
  list: {
    flex: 1,
  },
  tradeItem: {
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  tradeHeader: {
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
  },
  tradeInstrument: {
    fontFamily: theme.fonts.primary,
    fontSize: 15,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  tradeTagsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  tradeDirection: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    letterSpacing: 1,
  },
  modeBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: theme.colors.textMuted,
  },
  modeBadgeText: {
    fontFamily: theme.fonts.primary,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  tradeRight: {
    alignItems: 'flex-end',
  },
  tradePnl: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: 'bold',
  },
  tradeDate: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    marginTop: 4,
  },
  tradePrices: {
    marginTop: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.xs,
  },
  tradePriceText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
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
  // Loading / Error
  loadingText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: theme.spacing.md,
    letterSpacing: 2,
  },
  errorIcon: {
    fontSize: 40,
    color: theme.colors.neonRed,
    marginBottom: theme.spacing.md,
  },
  errorText: {
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    color: theme.colors.neonRed,
    textAlign: 'center',
  },
  retryBtn: {
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.cp2077Yellow,
    borderRadius: theme.borderRadius.md,
  },
  retryBtnText: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 2,
  },
});
