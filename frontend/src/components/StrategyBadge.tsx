/**
 * NeonTrade AI - Strategy Badge Component
 * Shows a colored badge for each trading strategy.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { theme } from '../theme/cyberpunk';
import { STRATEGY_COLORS as BASE_STRATEGY_COLORS } from '../services/api';

const STRATEGY_COLORS: Record<string, string> = {
  ...BASE_STRATEGY_COLORS,
  BLUE_A: BASE_STRATEGY_COLORS.BLUE,
  BLUE_B: BASE_STRATEGY_COLORS.BLUE,
  BLUE_C: BASE_STRATEGY_COLORS.BLUE,
};

const STRATEGY_NAMES: Record<string, string> = {
  BLUE: 'BLUE',
  BLUE_A: 'BLUE A',
  BLUE_B: 'BLUE B',
  BLUE_C: 'BLUE C',
  RED: 'RED',
  PINK: 'PINK',
  WHITE: 'WHITE',
  BLACK: 'BLACK',
  GREEN: 'GREEN',
};

interface Props {
  strategy: string;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export default function StrategyBadge({ strategy, size = 'md', showLabel = true }: Props) {
  const color = STRATEGY_COLORS[strategy] || theme.colors.textMuted;
  const label = STRATEGY_NAMES[strategy] || strategy;

  const dotSize = size === 'sm' ? 8 : size === 'md' ? 12 : 16;
  const fontSize = size === 'sm' ? 9 : size === 'md' ? 11 : 14;

  return (
    <View style={styles.container}>
      <View
        style={[
          styles.dot,
          {
            width: dotSize,
            height: dotSize,
            borderRadius: dotSize / 2,
            backgroundColor: color,
            shadowColor: color,
            shadowOffset: { width: 0, height: 0 },
            shadowOpacity: 0.8,
            shadowRadius: 4,
          },
        ]}
      />
      {showLabel && (
        <Text style={[styles.label, { fontSize, color }]}>{label}</Text>
      )}
    </View>
  );
}

export function ConfidenceBadge({ level }: { level: string }) {
  const color =
    level === 'ALTA' ? theme.colors.neonGreen :
    level === 'MEDIA' ? theme.colors.neonYellow :
    theme.colors.neonRed;

  return (
    <View style={[styles.confidenceBadge, { borderColor: color }]}>
      <Text style={[styles.confidenceText, { color }]}>{level}</Text>
    </View>
  );
}

export function DirectionBadge({ direction }: { direction: string }) {
  const isBuy = direction === 'BUY';
  return (
    <Text style={[styles.direction, { color: isBuy ? theme.colors.profit : theme.colors.loss }]}>
      {isBuy ? '▲ COMPRA' : '▼ VENTA'}
    </Text>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dot: {},
  label: {
    fontFamily: theme.fonts.bold,
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  confidenceBadge: {
    borderWidth: 1,
    borderRadius: theme.borderRadius.sm,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  confidenceText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 10,
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  direction: {
    fontFamily: theme.fonts.bold,
    fontSize: 13,
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
});
