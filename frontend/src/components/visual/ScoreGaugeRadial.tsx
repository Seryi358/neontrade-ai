/**
 * V8 — ScoreGaugeRadial
 * Semi-circle gauge with 4 colored zones (0-40 gray, 40-70 amber,
 * 70-85 light green, 85-100 strong green). Animated needle.
 *
 * Uses react-native-svg. Compatible with Expo Web.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  Pressable,
} from 'react-native';
import Svg, { Path, Circle, Line, G } from 'react-native-svg';
import { theme } from '../../theme/apple-glass';

// AnimatedG not used — we animate the rotation via listener to setNativeProps-free
// state-driven rotate string to stay cross-platform compatible.

interface ScoreGaugeRadialProps {
  score: number;         // 0-100
  label?: string;        // instrument or context
  size?: number;
}

// Semicircle path: 180° arc
function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startAngle: number, endAngle: number): string {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const large = endAngle - startAngle <= 180 ? 0 : 1;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${large} 0 ${end.x} ${end.y}`;
}

const ZONES = [
  { from: 0, to: 40, color: '#D1D1D6', label: 'Débil (0–40)' },
  { from: 40, to: 70, color: '#FF9500', label: 'Atento (40–70)' },
  { from: 70, to: 85, color: '#34C759', label: 'Alto (70–85)' },
  { from: 85, to: 100, color: '#00C853', label: 'Máximo (85+)' },
];

// 180° → left side (180), 0° → right side
// Mapping score 0 → 180°, 100 → 0°
function scoreToAngle(score: number): number {
  const clamped = Math.min(100, Math.max(0, score));
  return 180 - (clamped / 100) * 180;
}

export default function ScoreGaugeRadial({
  score,
  label,
  size = 200,
}: ScoreGaugeRadialProps) {
  const cx = size / 2;
  const cy = size / 2 + 10;
  const radius = size / 2 - 18;
  const strokeWidth = 14;

  const anim = useRef(new Animated.Value(0)).current;
  const [animScore, setAnimScore] = useState(0);
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    const listener = anim.addListener(({ value }) => setAnimScore(value));
    Animated.spring(anim, {
      toValue: score,
      friction: 7,
      tension: 40,
      useNativeDriver: false,
    }).start();
    return () => anim.removeListener(listener);
  }, [score, anim]);

  // Needle: rotate from -90 (score 0) to +90 (score 100) around (cx, cy).
  const needleAngleDeg = -90 + (Math.min(100, Math.max(0, animScore)) / 100) * 180;

  return (
    <View style={styles.wrap}>
      <Svg width={size} height={size / 2 + 30} viewBox={`0 0 ${size} ${size / 2 + 30}`}>
        {/* Zones */}
        {ZONES.map((z, i) => {
          const a1 = scoreToAngle(z.to);
          const a2 = scoreToAngle(z.from);
          return (
            <Path
              key={i}
              d={describeArc(cx, cy, radius, a1, a2)}
              stroke={z.color}
              strokeWidth={strokeWidth}
              strokeLinecap="butt"
              fill="none"
            />
          );
        })}
        {/* Needle (rotates around gauge origin) */}
        <G
          originX={cx}
          originY={cy}
          rotation={needleAngleDeg}
        >
          <Line
            x1={cx}
            y1={cy}
            x2={cx}
            y2={cy - radius + 4}
            stroke="#1d1d1f"
            strokeWidth={3}
            strokeLinecap="round"
          />
          <Circle cx={cx} cy={cy} r={5} fill="#1d1d1f" />
          <Circle cx={cx} cy={cy} r={2} fill="#ffffff" />
        </G>
      </Svg>

      <Pressable onPress={() => setShowInfo(v => !v)} style={styles.valueOverlay}>
        <Text style={styles.scoreValue}>{Math.round(score)}</Text>
        <Text style={styles.scoreUnit}>/100</Text>
        {label != null && <Text style={styles.label}>{label}</Text>}
      </Pressable>

      {showInfo && (
        <View style={styles.tooltip}>
          <Text style={styles.tooltipTitle}>Zonas del score</Text>
          {ZONES.map((z, i) => (
            <View key={i} style={styles.tooltipRow}>
              <View style={[styles.tooltipSwatch, { backgroundColor: z.color }]} />
              <Text style={styles.tooltipText}>{z.label}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignItems: 'center',
    paddingTop: 4,
  },
  valueOverlay: {
    position: 'absolute',
    top: 48,
    alignItems: 'center',
    justifyContent: 'center',
  },
  scoreValue: {
    fontFamily: theme.fonts.heading,
    fontSize: 42,
    fontWeight: '700',
    color: theme.colors.textPrimary,
    letterSpacing: -1,
    fontVariant: ['tabular-nums' as const],
  },
  scoreUnit: {
    fontFamily: theme.fonts.medium,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: -4,
    letterSpacing: 0.5,
  },
  label: {
    fontFamily: theme.fonts.medium,
    fontSize: 13,
    color: theme.colors.textSecondary,
    marginTop: 4,
    letterSpacing: 0.3,
  },
  tooltip: {
    marginTop: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
    backgroundColor: 'rgba(255,255,255,0.85)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.04)',
    gap: 4,
  },
  tooltipTitle: {
    fontFamily: theme.fonts.semibold,
    fontSize: 12,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    marginBottom: 4,
  },
  tooltipRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tooltipSwatch: {
    width: 10,
    height: 10,
    borderRadius: 3,
  },
  tooltipText: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
});
