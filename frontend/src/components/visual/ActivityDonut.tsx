/**
 * V6 — ActivityDonut
 * Donut chart showing scan/filter/execute ratios. Uses react-native-svg.
 * 3 colored arcs (executed / filtered / remaining) + center label with scans count.
 */

import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Svg, { Circle, G } from 'react-native-svg';
import { theme } from '../../theme/apple-glass';

interface ActivityDonutProps {
  scansCompleted: number;
  setupsFound: number;
  setupsExecuted: number;
  setupsFiltered: number;
  size?: number;
  strokeWidth?: number;
}

const COLOR_EXECUTED = '#00C853';
const COLOR_FILTERED = '#FF9500';
const COLOR_REMAINING = '#1E88E5';
const COLOR_EMPTY = 'rgba(0,0,0,0.08)';

function arc(
  radius: number,
  circumference: number,
  offset: number,
  length: number,
  color: string,
  key: string,
) {
  if (length <= 0) return null;
  return (
    <Circle
      key={key}
      cx={0}
      cy={0}
      r={radius}
      fill="none"
      stroke={color}
      strokeWidth={10}
      strokeDasharray={`${length} ${circumference}`}
      strokeDashoffset={-offset}
      strokeLinecap="butt"
    />
  );
}

export default function ActivityDonut({
  scansCompleted,
  setupsFound,
  setupsExecuted,
  setupsFiltered,
  size = 120,
  strokeWidth = 12,
}: ActivityDonutProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const total = Math.max(0, setupsFound);
  const executed = Math.max(0, Math.min(setupsExecuted, total));
  const filtered = Math.max(0, Math.min(setupsFiltered, Math.max(0, total - executed)));
  const remaining = Math.max(0, total - executed - filtered);

  const hasActivity = total > 0;

  // Compute arc lengths
  const lenExec = hasActivity ? (executed / total) * circumference : 0;
  const lenFilt = hasActivity ? (filtered / total) * circumference : 0;
  const lenRem = hasActivity ? (remaining / total) * circumference : 0;

  return (
    <View style={styles.row}>
      <View style={{ width: size, height: size }}>
        <Svg width={size} height={size} viewBox={`${-size / 2} ${-size / 2} ${size} ${size}`}>
          <G rotation={-90}>
            {/* background ring */}
            <Circle
              cx={0}
              cy={0}
              r={radius}
              fill="none"
              stroke={COLOR_EMPTY}
              strokeWidth={strokeWidth}
            />
            {hasActivity && arc(radius, circumference, 0, lenExec, COLOR_EXECUTED, 'exec')}
            {hasActivity && arc(radius, circumference, lenExec, lenFilt, COLOR_FILTERED, 'filt')}
            {hasActivity && arc(radius, circumference, lenExec + lenFilt, lenRem, COLOR_REMAINING, 'rem')}
          </G>
        </Svg>
        <View style={styles.center} pointerEvents="none">
          <Text style={styles.centerNumber}>{scansCompleted}</Text>
          <Text style={styles.centerLabel}>scans</Text>
        </View>
      </View>

      <View style={styles.legend}>
        {!hasActivity ? (
          <Text style={styles.emptyText}>Sin actividad todavía</Text>
        ) : (
          <>
            <LegendItem color={COLOR_EXECUTED} label="Ejecutados" value={executed} />
            <LegendItem color={COLOR_FILTERED} label="Filtrados" value={filtered} />
            <LegendItem color={COLOR_REMAINING} label="Pendientes" value={remaining} />
            <View style={styles.totalRow}>
              <Text style={styles.totalLabel}>Setups totales</Text>
              <Text style={styles.totalValue}>{setupsFound}</Text>
            </View>
          </>
        )}
      </View>
    </View>
  );
}

function LegendItem({
  color,
  label,
  value,
}: { color: string; label: string; value: number }) {
  return (
    <View style={styles.legendRow}>
      <View style={[styles.legendSwatch, { backgroundColor: color }]} />
      <Text style={styles.legendLabel}>{label}</Text>
      <Text style={styles.legendValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  center: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    alignItems: 'center',
    justifyContent: 'center',
  },
  centerNumber: {
    fontFamily: theme.fonts.heading,
    fontSize: 26,
    fontWeight: '700',
    color: theme.colors.textPrimary,
    letterSpacing: -0.4,
    fontVariant: ['tabular-nums' as const],
  },
  centerLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.textSecondary,
    letterSpacing: 0.3,
    marginTop: -2,
  },
  legend: {
    flex: 1,
    gap: 6,
  },
  legendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  legendSwatch: {
    width: 10,
    height: 10,
    borderRadius: 3,
  },
  legendLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
    flex: 1,
  },
  legendValue: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    fontVariant: ['tabular-nums' as const],
  },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
    paddingTop: 6,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.06)',
  },
  totalLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  totalValue: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '700',
    color: theme.colors.textPrimary,
    fontVariant: ['tabular-nums' as const],
  },
  emptyText: {
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    color: theme.colors.textMuted,
    textAlign: 'center',
  },
});
