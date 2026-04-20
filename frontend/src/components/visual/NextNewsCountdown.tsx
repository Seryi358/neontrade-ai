/**
 * V9 — NextNewsCountdown
 * Compact widget for the next high-impact news event. Shows countdown HH:MM:SS,
 * flag+title, impact stars, sand-clock progress bar.
 * Highlights if <60 min, pulses red if <5 min.
 */

import React, { useEffect, useMemo, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
} from 'react-native';
import { theme } from '../../theme/apple-glass';
import { flagForCurrency, impactStars } from '../../utils/flags';
import { useCountdown } from '../../hooks/useCountdown';
import type { NewsEvent } from '../../hooks/useEngineState';

interface NextNewsCountdownProps {
  event: NewsEvent | null;
  /** Longest expected horizon in minutes — used for progress bar. Default 8h. */
  horizonMinutes?: number;
}

function truncate(s: string, max = 30): string {
  if (!s) return '';
  if (s.length <= max) return s;
  return s.slice(0, max - 1).trim() + '…';
}

export default function NextNewsCountdown({
  event,
  horizonMinutes = 480,
}: NextNewsCountdownProps) {
  const countdown = useCountdown(event?.time_utc ?? null);
  const pulse = useRef(new Animated.Value(0)).current;

  const urgency: 'normal' | 'warn' | 'critical' = (() => {
    if (!event) return 'normal';
    if (countdown.totalSeconds <= 5 * 60) return 'critical';
    if (countdown.totalSeconds <= 60 * 60) return 'warn';
    return 'normal';
  })();

  useEffect(() => {
    if (urgency === 'critical') {
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1, duration: 500, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 0, duration: 500, useNativeDriver: true }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    pulse.setValue(0);
    return undefined;
  }, [urgency, pulse]);

  // Progress bar: fraction of horizon remaining (full → time far away)
  const progress = useMemo(() => {
    if (!event) return 0;
    const minutesRemain = countdown.totalSeconds / 60;
    return Math.max(0, Math.min(1, minutesRemain / horizonMinutes));
  }, [countdown.totalSeconds, horizonMinutes, event]);

  if (!event) {
    return (
      <View style={[styles.wrap, styles.wrapNormal]}>
        <Text style={styles.emptyText}>Sin próximos eventos de alto impacto</Text>
      </View>
    );
  }

  const borderColor =
    urgency === 'critical' ? '#FF3B30' :
    urgency === 'warn' ? '#FF9500' :
    'rgba(0,0,0,0.06)';

  const countdownColor =
    urgency === 'critical' ? '#FF3B30' :
    urgency === 'warn' ? '#FF9500' :
    theme.colors.textPrimary;

  return (
    <Animated.View
      style={[
        styles.wrap,
        { borderColor, shadowColor: borderColor },
        urgency !== 'normal' && {
          shadowOpacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.15, 0.4] }),
          shadowRadius: 14,
        },
      ]}
    >
      <View style={styles.topRow}>
        <Text style={styles.flag}>{flagForCurrency(event.currency)}</Text>
        <View style={styles.titleBlock}>
          <Text style={styles.title} numberOfLines={1}>
            {truncate(event.title, 34)}
          </Text>
          <Text style={styles.stars}>
            {impactStars(event.impact)}
            <Text style={styles.currency}>  {event.currency}</Text>
          </Text>
        </View>
      </View>

      <Text style={[styles.countdown, { color: countdownColor }]}>
        {countdown.hhmmss}
      </Text>

      <View style={styles.progressTrack}>
        <View
          style={[
            styles.progressFill,
            {
              width: `${progress * 100}%`,
              backgroundColor:
                urgency === 'critical' ? '#FF3B30' :
                urgency === 'warn' ? '#FF9500' :
                '#1E88E5',
            },
          ]}
        />
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    backgroundColor: 'rgba(255,255,255,0.75)',
    borderRadius: 14,
    borderWidth: 1,
    padding: 12,
    gap: 6,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  wrapNormal: {
    borderColor: 'rgba(0,0,0,0.06)',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  flag: {
    fontSize: 20,
  },
  titleBlock: {
    flex: 1,
  },
  title: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    letterSpacing: -0.1,
  },
  stars: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textSecondary,
    marginTop: 1,
  },
  currency: {
    fontFamily: theme.fonts.medium,
    fontSize: 10,
    letterSpacing: 0.4,
    color: theme.colors.textMuted,
  },
  countdown: {
    fontFamily: theme.fonts.heading,
    fontSize: 22,
    fontWeight: '700',
    letterSpacing: -0.4,
    fontVariant: ['tabular-nums' as const],
  },
  progressTrack: {
    height: 4,
    width: '100%',
    backgroundColor: 'rgba(0,0,0,0.06)',
    borderRadius: 2,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 2,
  },
  emptyText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
    paddingVertical: 8,
  },
});
