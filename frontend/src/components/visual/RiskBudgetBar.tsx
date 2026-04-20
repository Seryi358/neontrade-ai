/**
 * V5 — RiskBudgetBar
 * Shows risk deployed today vs max, and remaining trade slots.
 *
 *   currentRiskDollars: risk exposed right now (sum of open positions risk)
 *   maxRiskDollars: maxTotalRisk * balance
 *   dayRiskPct: risk_day_trading (e.g. 0.01) for label
 *   maxTotalPct: max_total_risk (e.g. 0.05)
 *   executedToday / maxTrades: slot dots.
 */

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
} from 'react-native';
import { theme } from '../../theme/apple-glass';

interface RiskBudgetBarProps {
  currentRiskDollars: number;
  maxRiskDollars: number;
  dayRiskPct?: number | null;       // 0.01 → 1%
  maxTotalPct?: number | null;      // 0.05 → 5%
  executedToday: number;
  maxTrades: number;
}

function fillColor(ratio: number): string {
  if (ratio >= 0.8) return '#FF3B30';
  if (ratio >= 0.5) return '#FF9500';
  return '#00C853';
}

function fmtUsd(v: number): string {
  if (!isFinite(v)) return '$0.00';
  return `$${v.toFixed(2)}`;
}

export default function RiskBudgetBar({
  currentRiskDollars,
  maxRiskDollars,
  dayRiskPct,
  maxTotalPct,
  executedToday,
  maxTrades,
}: RiskBudgetBarProps) {
  const ratio = maxRiskDollars > 0
    ? Math.min(1, Math.max(0, currentRiskDollars / maxRiskDollars))
    : 0;
  const color = fillColor(ratio);
  const animated = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(animated, {
      toValue: ratio,
      duration: 600,
      useNativeDriver: false,
    }).start();
  }, [ratio, animated]);

  const width = animated.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });

  const pctLabel = (() => {
    const dayPct = dayRiskPct != null ? `${(dayRiskPct * 100).toFixed(1)}%` : '—';
    const maxPct = maxTotalPct != null ? `${(maxTotalPct * 100).toFixed(1)}%` : '—';
    return `(${dayPct}/${maxPct})`;
  })();

  const slots = Array.from({ length: Math.max(0, maxTrades) }, (_, i) => i < executedToday);

  return (
    <View style={styles.wrap}>
      <View style={styles.headerRow}>
        <Text style={styles.title}>RIESGO HOY</Text>
        <Text style={styles.subtitle}>
          {fmtUsd(currentRiskDollars)} / {fmtUsd(maxRiskDollars)} máx {pctLabel}
        </Text>
      </View>

      <View style={styles.track}>
        <Animated.View
          style={[
            styles.fill,
            { width: width as unknown as number, backgroundColor: color },
          ]}
        />
      </View>

      <View style={styles.slotsRow}>
        {slots.length === 0 ? (
          <Text style={styles.slotLabel}>Sin límite diario configurado</Text>
        ) : (
          <>
            <View style={styles.dotRow}>
              {slots.map((filled, idx) => (
                <View
                  key={idx}
                  style={[
                    styles.slotDot,
                    filled ? styles.slotDotFilled : styles.slotDotEmpty,
                  ]}
                />
              ))}
            </View>
            <Text style={styles.slotLabel}>
              {executedToday}/{maxTrades} trades hoy
            </Text>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 8,
  },
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
  },
  title: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    fontWeight: '500',
  },
  subtitle: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
    fontVariant: ['tabular-nums' as const],
  },
  track: {
    width: '100%',
    height: 10,
    backgroundColor: 'rgba(0,0,0,0.06)',
    borderRadius: 5,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 5,
  },
  slotsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  dotRow: {
    flexDirection: 'row',
    gap: 6,
  },
  slotDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  slotDotFilled: {
    backgroundColor: '#1E88E5',
  },
  slotDotEmpty: {
    backgroundColor: 'rgba(30, 136, 229, 0.18)',
    borderWidth: 1,
    borderColor: 'rgba(30, 136, 229, 0.35)',
  },
  slotLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 0.3,
  },
});
