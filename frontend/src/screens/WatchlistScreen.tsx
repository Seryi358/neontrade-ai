/**
 * Atlas - Watchlist Screen
 * Shows all watched pairs with analysis scores, strategy detections, and signals.
 * CyberPunk 2077 HUD redesign with sub-navigation pills.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
} from 'react-native';
import { theme } from '../theme/apple-glass';
const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);
import {
  HUDCard,
  HUDHeader,
  HUDStatRow,
  HUDBadge,
  HUDDivider,
  SubNavPills,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
import StrategyBadge, { ConfidenceBadge } from '../components/StrategyBadge';
import { API_URL, authFetch, STRATEGY_COLORS, getScoreColor, getTrendColor, getTrendIcon } from '../services/api';

interface StrategyChecklistEntry {
  strategy: string;
  htf_passed: boolean;
  setup_found: boolean;
}

interface WatchlistItem {
  instrument: string;
  score: number;
  trend: string;
  convergence?: boolean;
  patterns?: string[];
  condition?: string;
  strategy_detected?: string | null;
  confidence_level?: string;
  strategy_checklist?: StrategyChecklistEntry[];
}

const SUB_NAV_OPTIONS = [
  { key: 'watchlist', label: 'WATCHLIST' },
  { key: 'crypto', label: 'CRYPTO' },
];

export default function WatchlistScreen() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchWatchlist = async () => {
      try {
        setError(null);
        const res = await authFetch(`${API_URL}/api/v1/watchlist`);
        if (!res.ok) throw new Error('Error del servidor');
        const data = await res.json();
        setWatchlist(data);
      } catch (err) {
        console.error('Failed to fetch watchlist:', err);
        setError('Error al cargar datos');
      }
    };
    fetchWatchlist();
    const interval = setInterval(fetchWatchlist, 10000);
    return () => clearInterval(interval);
  }, []);

  const getConfidenceColor = (level?: string) => {
    if (level === 'ALTA') return theme.colors.neonGreen;
    if (level === 'MEDIA') return theme.colors.neonYellow;
    return theme.colors.neonRed;
  };

  const getConvergenceLabel = (item: WatchlistItem): string | null => {
    if (!item.convergence) return null;
    return 'HTF/LTF CONV';
  };

  const activeCount = watchlist.filter(i => i.strategy_detected).length;

  const renderItem = ({ item }: { item: WatchlistItem }) => (
    <TouchableOpacity activeOpacity={0.85}>
      <HUDCard
        accentColor={
          item.strategy_detected
            ? STRATEGY_COLORS[item.strategy_detected] || theme.colors.cp2077Yellow
            : theme.colors.cp2077Yellow
        }
        borderColor={
          item.strategy_detected
            ? STRATEGY_COLORS[item.strategy_detected] || theme.colors.border
            : undefined
        }
      >
        {/* Top row: instrument name + score */}
        <View style={styles.topRow}>
          <Text style={styles.instrumentName}>
            {item.instrument.replace('_', '/')}
          </Text>
          <View style={styles.scoreBox}>
            <Text style={[styles.scoreNumber, { color: getScoreColor(item.score) }]}>
              {safe(item.score, 0)}
            </Text>
            <Text style={styles.scoreLabel}>SCORE</Text>
          </View>
        </View>

        {/* Tags row: trend + convergence + OB/OS */}
        <View style={styles.tagsRow}>
          {/* Trend */}
          <Text style={[styles.trendTag, { color: getTrendColor(item.trend) }]}>
            {getTrendIcon(item.trend)}{' '}
            {item.trend === 'bullish' ? 'ALCISTA' : item.trend === 'bearish' ? 'BAJISTA' : 'RANGO'}
          </Text>

          {/* Convergence */}
          {item.convergence && (
            <HUDBadge label="HTF/LTF CONV" color={theme.colors.neonCyan} small />
          )}

          {/* OB/OS condition */}
          {item.condition && item.condition !== 'neutral' && (
            <HUDBadge
              label={item.condition === 'overbought' ? 'SOBRECOMPRA' : 'SOBREVENTA'}
              color={item.condition === 'overbought' ? theme.colors.neonRed : theme.colors.neonGreen}
              small
            />
          )}
        </View>

        {/* Strategy detection row */}
        {item.strategy_detected && (
          <View style={styles.strategyRow}>
            <StrategyBadge strategy={item.strategy_detected} size="sm" />
            {item.confidence_level && (
              <ConfidenceBadge level={item.confidence_level} />
            )}
          </View>
        )}

        {/* Strategy checklist — shows which strategies pass/fail HTF */}
        {item.strategy_checklist && item.strategy_checklist.length > 0 && (
          <View style={styles.checklistRow}>
            {item.strategy_checklist.map((c: any) => (
              <View key={c.strategy} style={styles.checklistItem}>
                <Text style={[
                  styles.checklistDot,
                  { color: c.setup_found ? theme.colors.neonGreen : c.htf_passed ? theme.colors.neonCyan : theme.colors.textMuted }
                ]}>
                  {c.setup_found ? '✓' : c.htf_passed ? '◐' : '✗'}
                </Text>
                <Text style={[
                  styles.checklistLabel,
                  { color: c.setup_found ? theme.colors.neonGreen : c.htf_passed ? theme.colors.neonCyan : theme.colors.textMuted }
                ]}>
                  {c.strategy}
                </Text>
              </View>
            ))}
          </View>
        )}
      </HUDCard>
    </TouchableOpacity>
  );

  return (
    <View style={styles.container}>
      {/* Sub-navigation pills */}
      <SubNavPills
        options={SUB_NAV_OPTIONS}
        activeKey="watchlist"
        onSelect={() => {}}
      />

      {/* Header stats */}
      <HUDCard accentColor={theme.colors.neonCyan}>
        <View style={styles.headerStatsRow}>
          <View style={styles.headerStat}>
            <Text style={styles.headerStatValue}>{watchlist.length}</Text>
            <Text style={styles.headerStatLabel}>PARES</Text>
          </View>
          <View style={styles.headerStatDivider} />
          <View style={styles.headerStat}>
            <Text style={[styles.headerStatValue, { color: activeCount > 0 ? theme.colors.neonGreen : theme.colors.textMuted }]}>
              {activeCount}
            </Text>
            <Text style={styles.headerStatLabel}>SENALES</Text>
          </View>
        </View>
      </HUDCard>

      {error && <ErrorState message={error} />}

      {/* Instrument list */}
      <FlatList
        data={watchlist}
        keyExtractor={(item) => item.instrument}
        renderItem={renderItem}
        style={styles.list}
        showsVerticalScrollIndicator={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
    padding: 16,
    paddingTop: 24,
  },
  list: {
    flex: 1,
  },
  // Top row
  topRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  instrumentName: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1d1d1f',
    letterSpacing: -0.2,
  },
  scoreBox: {
    alignItems: 'center',
  },
  scoreNumber: {
    fontSize: 26,
    fontWeight: '700',
  },
  scoreLabel: {
    fontSize: 10,
    fontWeight: '500',
    color: '#aeaeb2',
    letterSpacing: 0.3,
  },
  // Tags row
  tagsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 6,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  trendTag: {
    fontSize: 12,
    fontWeight: '600',
  },
  // Strategy row
  strategyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginTop: 8,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.04)',
  },
  // Strategy checklist
  checklistRow: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 8,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.04)',
    flexWrap: 'wrap',
  },
  checklistItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  checklistDot: {
    fontSize: 11,
  },
  checklistLabel: {
    fontSize: 10,
    fontWeight: '500',
  },
  // Header stats
  headerStatsRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 24,
  },
  headerStat: {
    alignItems: 'center',
  },
  headerStatValue: {
    fontSize: 22,
    color: '#007AFF',
    fontWeight: '700',
  },
  headerStatLabel: {
    fontSize: 10,
    fontWeight: '500',
    color: '#aeaeb2',
    letterSpacing: 0.3,
  },
  headerStatDivider: {
    width: 1,
    height: 30,
    backgroundColor: 'rgba(0,0,0,0.04)',
  },
});
