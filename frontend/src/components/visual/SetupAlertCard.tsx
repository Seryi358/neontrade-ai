/**
 * V7 — SetupAlertCard
 * Slide-in entry card for a freshly-arrived setup. Spring translate from top,
 * 2.5s pulsing shadow glow colored by strategy. Tap handlers optional.
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
import { STRATEGY_COLORS } from '../../services/api';

export interface SetupPayload {
  id?: string;
  instrument?: string;
  strategy?: string;
  direction?: string;         // BUY | SELL
  entry?: number;
  sl?: number;
  tp1?: number;
  tp_max?: number;
  rr?: number;
}

interface SetupAlertCardProps {
  setup: SetupPayload;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onPress?: (id: string) => void;
}

function fmt(v: number | undefined, d = 5): string {
  if (v == null || isNaN(v)) return '—';
  return v.toFixed(d);
}

export default function SetupAlertCard({
  setup,
  onApprove,
  onReject,
  onPress,
}: SetupAlertCardProps) {
  const translate = useRef(new Animated.Value(-60)).current;
  const opacity = useRef(new Animated.Value(0)).current;
  const glow = useRef(new Animated.Value(0)).current;

  const strategyKey = (setup.strategy || 'BLUE').split('_')[0].toUpperCase();
  const accent = STRATEGY_COLORS[strategyKey] || '#1E88E5';

  useEffect(() => {
    Animated.parallel([
      Animated.spring(translate, {
        toValue: 0,
        friction: 7,
        tension: 60,
        useNativeDriver: true,
      }),
      Animated.timing(opacity, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }),
    ]).start();

    // Glow pulse for 2.5s
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(glow, { toValue: 1, duration: 500, useNativeDriver: false }),
        Animated.timing(glow, { toValue: 0.3, duration: 500, useNativeDriver: false }),
      ]),
      { iterations: 3 },
    );
    pulse.start();
    return () => pulse.stop();
  }, [translate, opacity, glow]);

  const id = setup.id || '';

  return (
    <Animated.View
      style={[
        styles.wrap,
        {
          transform: [{ translateY: translate }],
          opacity,
          shadowColor: accent,
          shadowOpacity: glow.interpolate({ inputRange: [0, 1], outputRange: [0.12, 0.4] }),
          shadowRadius: glow.interpolate({ inputRange: [0, 1], outputRange: [8, 18] }),
          borderColor: accent,
        },
      ]}
    >
      <TouchableOpacity
        activeOpacity={0.9}
        onPress={() => onPress && id && onPress(id)}
        style={styles.inner}
      >
        <View style={[styles.leftBand, { backgroundColor: accent }]} />
        <View style={styles.content}>
          <View style={styles.headerRow}>
            <Text style={[styles.strategy, { color: accent }]}>{strategyKey}</Text>
            <Text style={styles.instrument}>{setup.instrument || '—'}</Text>
            <View
              style={[
                styles.dirPill,
                {
                  backgroundColor:
                    setup.direction === 'BUY' ? 'rgba(52,199,89,0.12)' : 'rgba(255,59,48,0.12)',
                },
              ]}
            >
              <Text
                style={[
                  styles.dirText,
                  { color: setup.direction === 'BUY' ? '#00C853' : '#FF3B30' },
                ]}
              >
                {setup.direction || '—'}
              </Text>
            </View>
          </View>

          <View style={styles.priceRow}>
            <PriceCol label="Entry" value={fmt(setup.entry)} color={theme.colors.textPrimary} />
            <PriceCol label="SL" value={fmt(setup.sl)} color="#FF3B30" />
            <PriceCol label="TP1" value={fmt(setup.tp1)} color="#00C853" />
            {setup.rr != null && (
              <PriceCol label="R:R" value={`1:${setup.rr.toFixed(2)}`} color="#1E88E5" />
            )}
          </View>

          {(onApprove || onReject) && id && (
            <View style={styles.actionRow}>
              {onApprove && (
                <TouchableOpacity
                  style={[styles.actionBtn, styles.approveBtn]}
                  onPress={() => onApprove(id)}
                >
                  <Text style={styles.approveText}>Aprobar</Text>
                </TouchableOpacity>
              )}
              {onReject && (
                <TouchableOpacity
                  style={[styles.actionBtn, styles.rejectBtn]}
                  onPress={() => onReject(id)}
                >
                  <Text style={styles.rejectText}>Rechazar</Text>
                </TouchableOpacity>
              )}
            </View>
          )}
        </View>
      </TouchableOpacity>
    </Animated.View>
  );
}

function PriceCol({
  label,
  value,
  color,
}: { label: string; value: string; color: string }) {
  return (
    <View style={styles.priceCol}>
      <Text style={styles.priceLabel}>{label}</Text>
      <Text style={[styles.priceValue, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: '#ffffff',
    borderRadius: 16,
    borderWidth: 1,
    marginBottom: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 4,
    overflow: 'hidden',
  },
  inner: {
    flexDirection: 'row',
  },
  leftBand: {
    width: 4,
  },
  content: {
    flex: 1,
    padding: 14,
    gap: 10,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  strategy: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  instrument: {
    fontFamily: theme.fonts.semibold,
    fontSize: 15,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    flex: 1,
  },
  dirPill: {
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
  },
  dirText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.4,
  },
  priceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  priceCol: {
    alignItems: 'flex-start',
  },
  priceLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 0.3,
    textTransform: 'uppercase',
  },
  priceValue: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '600',
    marginTop: 1,
    fontVariant: ['tabular-nums' as const],
  },
  actionRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 4,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: 'center',
  },
  approveBtn: {
    backgroundColor: 'rgba(52, 199, 89, 0.12)',
  },
  approveText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '600',
    color: '#00C853',
  },
  rejectBtn: {
    backgroundColor: 'rgba(255, 59, 48, 0.08)',
  },
  rejectText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '600',
    color: '#FF3B30',
  },
});
