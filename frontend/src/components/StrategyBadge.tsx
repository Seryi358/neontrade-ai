/**
 * Atlas - Strategy Badge Component
 * Shows a colored badge for each trading strategy.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { theme } from '../theme/apple-glass';
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

  const pillBg = `${color}14`; // ~8% opacity

  return (
    <View style={[styles.container, { backgroundColor: pillBg, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 }]}>
      <View
        style={[
          styles.dot,
          {
            width: dotSize,
            height: dotSize,
            borderRadius: dotSize / 2,
            backgroundColor: color,
          },
        ]}
      />
      {showLabel && (
        <Text style={[styles.label, { fontSize, color }]}>{label}</Text>
      )}
    </View>
  );
}

export function DirectionBadge({ direction }: { direction: string }) {
  const isBuy = direction === 'BUY';
  return (
    <Text style={[styles.direction, { color: isBuy ? theme.colors.profit : theme.colors.loss }]}>
      {isBuy ? 'COMPRA' : 'VENTA'}
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
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  direction: {
    fontSize: 13,
    fontWeight: '600',
  },
});
