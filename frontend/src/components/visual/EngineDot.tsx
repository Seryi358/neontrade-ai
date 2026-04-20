/**
 * V2 — EngineDot
 * Small colored pulsing dot reflecting engine state.
 *
 *   running, no pause          → green, pulse
 *   news_blackout / cooldown   → amber, static
 *   out_of_hours / friday_*    → gray, static
 *   !running                   → red, slow pulse
 *
 * Tap/hover shows a tooltip with paused_reason_text.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  Pressable,
} from 'react-native';
import { theme } from '../../theme/apple-glass';
import type { EngineState } from '../../hooks/useEngineState';

interface EngineDotProps {
  state: EngineState | null;
  size?: number;
  label?: string;
}

type DotVariant = 'running' | 'warning' | 'idle' | 'error';

function classify(state: EngineState | null): DotVariant {
  if (!state) return 'idle';
  if (!state.running) return 'error';
  const r = state.paused_reason;
  if (!r) return 'running';
  if (r === 'news_blackout' || r === 'cooldown_after_losses' || r === 'max_trades_reached' || r === 'friday_no_new_trades') {
    return 'warning';
  }
  if (r === 'out_of_hours' || r === 'friday_close') {
    return 'idle';
  }
  return 'warning';
}

const COLORS: Record<DotVariant, string> = {
  running: '#00C853',
  warning: '#FF9500',
  idle: theme.colors.textSecondary,
  error: '#FF3B30',
};

export default function EngineDot({ state, size = 10, label }: EngineDotProps) {
  const variant = classify(state);
  const color = COLORS[variant];
  const pulse = useRef(new Animated.Value(1)).current;
  const [tooltipVisible, setTooltipVisible] = useState(false);

  useEffect(() => {
    if (variant === 'running' || variant === 'error') {
      const duration = variant === 'running' ? 1000 : 1600;
      const loop = Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.2, duration, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration, useNativeDriver: true }),
        ])
      );
      loop.start();
      return () => loop.stop();
    }
    pulse.setValue(1);
    return undefined;
  }, [variant, pulse]);

  const tooltipText =
    state?.paused_reason_text ||
    (variant === 'running' ? 'Engine activo — escaneando' :
     variant === 'error' ? 'Engine detenido' :
     variant === 'idle' ? 'Engine en pausa' :
     'Engine en pausa');

  return (
    <View style={styles.wrap}>
      <Pressable
        onPressIn={() => setTooltipVisible(true)}
        onPressOut={() => setTooltipVisible(false)}
        onHoverIn={() => setTooltipVisible(true)}
        onHoverOut={() => setTooltipVisible(false)}
        style={styles.touch}
      >
        <View style={styles.inline}>
          <View style={{ width: size * 1.6, height: size * 1.6, alignItems: 'center', justifyContent: 'center' }}>
            <Animated.View
              style={[
                styles.dot,
                {
                  width: size,
                  height: size,
                  borderRadius: size / 2,
                  backgroundColor: color,
                  transform: [{ scale: pulse }],
                  shadowColor: color,
                },
              ]}
            />
          </View>
          {label != null && (
            <Text style={[styles.label, { color }]} numberOfLines={1}>
              {label}
            </Text>
          )}
        </View>
      </Pressable>
      {tooltipVisible && (
        <View style={styles.tooltip}>
          <Text style={styles.tooltipText} numberOfLines={2}>
            {tooltipText}
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'relative',
  },
  touch: {
    paddingVertical: 4,
  },
  inline: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.35,
    shadowRadius: 4,
    elevation: 2,
  },
  label: {
    fontFamily: theme.fonts.medium,
    fontSize: 12,
    fontWeight: '600',
    letterSpacing: 0.1,
  },
  tooltip: {
    position: 'absolute',
    top: 26,
    right: 0,
    minWidth: 180,
    maxWidth: 280,
    paddingHorizontal: 10,
    paddingVertical: 6,
    backgroundColor: 'rgba(29, 29, 31, 0.92)',
    borderRadius: 8,
    zIndex: 10000,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 6,
  },
  tooltipText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: '#ffffff',
    lineHeight: 16,
  },
});
