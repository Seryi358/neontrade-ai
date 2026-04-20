/**
 * V4 — InstrumentChip
 * Row for an instrument in the watchlist showing status icon, symbol,
 * score pill, direction, and status text. 3px left border color reflects status.
 */

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  TouchableOpacity,
} from 'react-native';
import { theme } from '../../theme/apple-glass';
import type { InstrumentStatus, InstrumentStatusItem } from '../../hooks/useWatchlistStatus';

interface InstrumentChipProps {
  item: InstrumentStatusItem;
  onPress?: (instrument: string) => void;
}

interface StatusMeta {
  accent: string;
  badgeBg: string;
  glyph: string;
  labelAlt: string;
  pulse: boolean;
}

const META: Record<InstrumentStatus, StatusMeta> = {
  setup_queued: {
    accent: '#1E88E5',
    badgeBg: 'rgba(30, 136, 229, 0.12)',
    glyph: '\u27A4',       // ➤ send
    labelAlt: 'SETUP ENCOLADO',
    pulse: true,
  },
  ready_waiting: {
    accent: '#34C759',
    badgeBg: 'rgba(52, 199, 89, 0.12)',
    glyph: '\u25C9',       // ◉ radar
    labelAlt: 'LISTO',
    pulse: false,
  },
  forming: {
    accent: '#FF9500',
    badgeBg: 'rgba(255, 149, 0, 0.12)',
    glyph: '\u231B',       // ⌛ clock
    labelAlt: 'FORMANDO',
    pulse: false,
  },
  weak: {
    accent: '#BFBFC4',
    badgeBg: 'rgba(191, 191, 196, 0.18)',
    glyph: '\u2212',       // − minus
    labelAlt: 'DÉBIL',
    pulse: false,
  },
  no_pattern: {
    accent: '#86868b',
    badgeBg: 'rgba(134, 134, 139, 0.15)',
    glyph: '\u2A2F',       // ⨯ x-like
    labelAlt: 'SIN PATRÓN',
    pulse: false,
  },
};

function scoreColor(score: number): string {
  if (score >= 80) return '#34C759';
  if (score >= 60) return '#FFCC00';
  if (score >= 40) return '#FF9500';
  return '#FF3B30';
}

function directionGlyph(trend: string): { icon: string; color: string } {
  const up = (trend || '').toLowerCase();
  if (up === 'bullish') return { icon: '\u2191', color: '#34C759' };
  if (up === 'bearish') return { icon: '\u2193', color: '#FF3B30' };
  return { icon: '\u00B1', color: theme.colors.textSecondary };
}

export default function InstrumentChip({ item, onPress }: InstrumentChipProps) {
  const meta = META[item.status] || META.no_pattern;
  const dir = directionGlyph(item.htf_trend);
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (meta.pulse) {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.12, duration: 900, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration: 900, useNativeDriver: true }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    pulse.setValue(1);
    return undefined;
  }, [meta.pulse, pulse]);

  const content = (
    <View style={[styles.row, { borderLeftColor: meta.accent }]}>
      <Animated.View
        style={[
          styles.badge,
          { backgroundColor: meta.badgeBg, transform: [{ scale: pulse }] },
        ]}
      >
        <Text style={[styles.badgeIcon, { color: meta.accent }]}>{meta.glyph}</Text>
      </Animated.View>
      <View style={styles.body}>
        <View style={styles.topLine}>
          <Text style={styles.symbol}>
            {item.instrument.replace('_', '/')}
          </Text>
          <View style={[styles.scorePill, { backgroundColor: scoreColor(item.score) + '1A' }]}>
            <Text style={[styles.scoreText, { color: scoreColor(item.score) }]}>
              {item.score.toFixed(0)}
            </Text>
          </View>
          <Text style={[styles.direction, { color: dir.color }]}>{dir.icon}</Text>
          {item.convergence && (
            <View style={styles.convPill}>
              <Text style={styles.convText}>CONV</Text>
            </View>
          )}
        </View>
        <Text style={styles.statusText} numberOfLines={2}>
          {item.status_text}
        </Text>
      </View>
    </View>
  );

  if (onPress) {
    return (
      <TouchableOpacity activeOpacity={0.85} onPress={() => onPress(item.instrument)}>
        {content}
      </TouchableOpacity>
    );
  }
  return content;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderLeftWidth: 3,
    backgroundColor: 'rgba(255,255,255,0.6)',
    borderRadius: 10,
    marginBottom: 8,
    gap: 10,
  },
  badge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeIcon: {
    fontSize: 14,
    fontWeight: '700',
  },
  body: {
    flex: 1,
  },
  topLine: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  symbol: {
    fontFamily: theme.fonts.semibold,
    fontSize: 15,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    letterSpacing: -0.1,
  },
  scorePill: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 6,
  },
  scoreText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
    fontVariant: ['tabular-nums' as const],
  },
  direction: {
    fontSize: 13,
    fontWeight: '600',
  },
  convPill: {
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
    backgroundColor: 'rgba(0, 122, 255, 0.12)',
  },
  convText: {
    fontFamily: theme.fonts.medium,
    fontSize: 9,
    fontWeight: '700',
    letterSpacing: 0.4,
    color: '#007AFF',
  },
  statusText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginTop: 2,
    lineHeight: 16,
  },
});
