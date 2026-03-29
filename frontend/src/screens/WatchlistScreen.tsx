/**
 * NeonTrade AI - Watchlist Screen
 * Shows all watched pairs with analysis scores, strategy detections, and signals.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Alert,
  TouchableOpacity,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, authFetch, STRATEGY_COLORS, getScoreColor, getTrendColor, getTrendIcon } from '../services/api';

interface WatchlistItem {
  instrument: string;
  score: number;
  trend: string;
  convergence?: boolean;
  patterns?: string[];
  condition?: string;
  strategy_detected?: string | null;
  confidence_level?: string;
}

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

  const showInstrumentInfo = (item: WatchlistItem) => {
    const trend = item.trend === 'bullish' ? 'Alcista' : item.trend === 'bearish' ? 'Bajista' : 'Rango';
    const details = [
      `Tendencia: ${trend}`,
      `Score: ${item.score.toFixed(0)}`,
      item.convergence ? 'Convergencia: Si' : null,
      item.condition && item.condition !== 'neutral' ? `Condicion: ${item.condition === 'overbought' ? 'Sobrecompra' : 'Sobreventa'}` : null,
      item.strategy_detected ? `Estrategia: ${item.strategy_detected}` : null,
      item.confidence_level ? `Confianza: ${item.confidence_level}` : null,
    ].filter(Boolean).join('\n');
    Alert.alert(item.instrument.replace('_', '/'), details);
  };

  const renderItem = ({ item }: { item: WatchlistItem }) => (
    <TouchableOpacity
      style={[
        styles.item,
        item.strategy_detected ? { borderColor: STRATEGY_COLORS[item.strategy_detected] || theme.colors.border } : {},
      ]}
      onPress={() => showInstrumentInfo(item)}
    >
      <View style={styles.itemLeft}>
        <Text style={styles.pair}>
          {item.instrument.replace('_', '/')}
        </Text>
        <View style={styles.tagsRow}>
          <Text style={[styles.trend, { color: getTrendColor(item.trend) }]}>
            {getTrendIcon(item.trend)} {item.trend === 'bullish' ? 'ALCISTA' : item.trend === 'bearish' ? 'BAJISTA' : 'RANGO'}
          </Text>
          {item.convergence && (
            <Text style={styles.convergenceTag}>CONV</Text>
          )}
          {item.condition && item.condition !== 'neutral' && (
            <Text style={[styles.conditionTag, {
              color: item.condition === 'overbought' ? theme.colors.neonRed : theme.colors.neonGreen,
              borderColor: item.condition === 'overbought' ? theme.colors.neonRed : theme.colors.neonGreen,
            }]}>
              {item.condition === 'overbought' ? 'SOBRECOMPRA' : 'SOBREVENTA'}
            </Text>
          )}
        </View>
        {item.strategy_detected && (
          <View style={styles.strategyRow}>
            <View style={[styles.strategyDot, { backgroundColor: STRATEGY_COLORS[item.strategy_detected] || '#888' }]} />
            <Text style={[styles.strategyText, { color: STRATEGY_COLORS[item.strategy_detected] || '#888' }]}>
              {item.strategy_detected}
            </Text>
            {item.confidence_level && (
              <Text style={[styles.confidenceTag, { color: getConfidenceColor(item.confidence_level), borderColor: getConfidenceColor(item.confidence_level) }]}>
                {item.confidence_level}
              </Text>
            )}
          </View>
        )}
      </View>

      <View style={styles.itemRight}>
        <View style={styles.scoreContainer}>
          <Text style={[styles.score, { color: getScoreColor(item.score) }]}>
            {item.score.toFixed(0)}
          </Text>
          <Text style={styles.scoreLabel}>SCORE</Text>
        </View>
      </View>
    </TouchableOpacity>
  );

  const activeCount = watchlist.filter(i => i.strategy_detected).length;

  return (
    <View style={styles.container}>
      <Text style={styles.header}>WATCHLIST</Text>
      <Text style={styles.subheader}>
        {watchlist.length} pares monitoreados
        {activeCount > 0 ? ` · ${activeCount} con señal` : ''}
      </Text>

      {error && <Text style={{color: theme.colors.neonRed, fontFamily: theme.fonts.mono, fontSize: 11, textAlign: 'center', padding: 8, letterSpacing: 2}}>{error}</Text>}

      <FlatList
        data={watchlist}
        keyExtractor={(item) => item.instrument}
        renderItem={renderItem}
        style={styles.list}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.md,
  },
  header: {
    fontFamily: theme.fonts.mono,
    fontSize: 20,
    color: theme.colors.neonPink,
    letterSpacing: 4,
    marginTop: theme.spacing.lg,
  },
  subheader: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: theme.spacing.md,
  },
  list: {
    flex: 1,
  },
  item: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  itemLeft: {
    flex: 1,
  },
  pair: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  tagsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
    flexWrap: 'wrap',
  },
  trend: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 1,
  },
  convergenceTag: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.neonCyan,
    borderWidth: 1,
    borderColor: theme.colors.neonCyan,
    borderRadius: 3,
    paddingHorizontal: 4,
    paddingVertical: 1,
    letterSpacing: 1,
  },
  conditionTag: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    borderWidth: 1,
    borderRadius: 3,
    paddingHorizontal: 4,
    paddingVertical: 1,
    letterSpacing: 1,
  },
  strategyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 6,
  },
  strategyDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  strategyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1,
  },
  confidenceTag: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    borderWidth: 1,
    borderRadius: 3,
    paddingHorizontal: 4,
    paddingVertical: 1,
    letterSpacing: 1,
    marginLeft: 4,
  },
  itemRight: {
    alignItems: 'center',
  },
  scoreContainer: {
    alignItems: 'center',
  },
  score: {
    fontFamily: theme.fonts.mono,
    fontSize: 24,
    fontWeight: 'bold',
  },
  scoreLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
});
