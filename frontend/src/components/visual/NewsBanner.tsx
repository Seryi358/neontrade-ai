/**
 * V1 — NewsBanner / PauseBanner
 * Shown at the top of screens when the engine is paused (news, off-hours,
 * Friday close, daily cap, cooldown). Shows a live countdown to resume.
 */

import React, { useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Animated,
} from 'react-native';
import { theme } from '../../theme/apple-glass';
import { useCountdown } from '../../hooks/useCountdown';
import type { EngineState, PausedReason } from '../../hooks/useEngineState';
import { flagForCurrency, impactStars } from '../../utils/flags';

interface NewsBannerProps {
  state: EngineState | null;
}

interface ReasonCopy {
  icon: string;
  title: string;
  subtitle: string;
  accent: string;     // left border color
  bg: string;         // background tint
}

const AMBER_BG = '#FFF6E5';
const AMBER_ACCENT = '#FF9500';
const GRAY_BG = '#F0F0F4';
const GRAY_ACCENT = '#86868b';
const GREEN_BG = '#E8F8EE';
const GREEN_ACCENT = '#34C759';
const SHIELD_BG = '#FFF1F0';
const SHIELD_ACCENT = '#FF3B30';

function formatResumeHHMM(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm} UTC`;
}

function reasonCopy(state: EngineState): ReasonCopy | null {
  const reason: PausedReason = state.paused_reason;
  if (!reason && state.market_notice) {
    return {
      icon: state.market_notice.country || 'CAL',
      title: state.market_notice.title,
      subtitle: state.market_notice.message,
      accent: AMBER_ACCENT,
      bg: AMBER_BG,
    };
  }
  if (!reason) return null;

  const resumeAt = formatResumeHHMM(state.resumes_at_utc);
  const news = state.news?.active;

  if (reason === 'news_blackout') {
    const flag = news ? flagForCurrency(news.currency) : 'NEWS';
    const title = news ? `${flag} ${news.title}` : 'News blackout activo';
    return {
      icon: 'N',
      title,
      subtitle: `Sin nuevos trades hasta ${resumeAt}`,
      accent: AMBER_ACCENT,
      bg: AMBER_BG,
    };
  }
  if (reason === 'out_of_hours') {
    return {
      icon: 'OFF',
      title: 'Engine inactivo',
      subtitle: `Reanuda a las ${resumeAt}`,
      accent: GRAY_ACCENT,
      bg: GRAY_BG,
    };
  }
  if (reason === 'weekend_closed') {
    return {
      icon: 'WKND',
      title: 'Mercado cerrado',
      subtitle: `Fin de semana — reanuda el lunes ${resumeAt}`,
      accent: GRAY_ACCENT,
      bg: GRAY_BG,
    };
  }
  if (reason === 'friday_close') {
    return {
      icon: 'FRI',
      title: 'Fin de semana',
      subtitle: `Mercado cerrado — reanuda el lunes ${resumeAt}`,
      accent: GRAY_ACCENT,
      bg: GRAY_BG,
    };
  }
  if (reason === 'friday_no_new_trades') {
    return {
      icon: 'FRI',
      title: 'Viernes: sin nuevos trades',
      subtitle: `Cierre de semana a las ${resumeAt}`,
      accent: AMBER_ACCENT,
      bg: AMBER_BG,
    };
  }
  if (reason === 'max_trades_reached') {
    return {
      icon: 'MAX',
      title: `${state.setups_executed_today}/${state.max_trades_per_day} trades ejecutados hoy`,
      subtitle: `Reanuda mañana ${resumeAt}`,
      accent: GREEN_ACCENT,
      bg: GREEN_BG,
    };
  }
  if (reason === 'cooldown_after_losses') {
    return {
      icon: 'DD',
      title: 'Cooldown post-pérdidas',
      subtitle: `Reanuda ${resumeAt}`,
      accent: SHIELD_ACCENT,
      bg: SHIELD_BG,
    };
  }
  return null;
}

export default function NewsBanner({ state }: NewsBannerProps) {
  const [expanded, setExpanded] = useState(false);
  const fade = useRef(new Animated.Value(0)).current;

  const copy = state ? reasonCopy(state) : null;
  const countdown = useCountdown(state?.resumes_at_utc ?? null);
  const visible = !!copy;

  // Fade in on mount / reason change
  useEffect(() => {
    if (visible) {
      Animated.timing(fade, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }).start();
    } else {
      Animated.timing(fade, {
        toValue: 0,
        duration: 1000,
        useNativeDriver: true,
      }).start();
    }
  }, [visible, fade]);

  if (!state || !copy) return null;

  const news = state.news?.active;
  const showCountdown = !!state.paused_reason;
  const countdownDisplay = countdown.totalSeconds > 0 ? countdown.mmss : '00:00';

  return (
    <Animated.View style={[styles.wrap, { opacity: fade }]}>
      <TouchableOpacity
        activeOpacity={0.85}
        onPress={() => setExpanded(v => !v)}
        style={[
          styles.banner,
          {
            backgroundColor: copy.bg,
            borderLeftColor: copy.accent,
          },
        ]}
      >
        <View style={styles.iconWrap}>
          <Text style={[styles.icon, { color: copy.accent }]}>{copy.icon}</Text>
        </View>
        <View style={styles.textBlock}>
          <Text style={styles.title} numberOfLines={2}>
            {copy.title}
          </Text>
          <Text style={styles.subtitle} numberOfLines={2}>
            {copy.subtitle}
          </Text>
        </View>
        {showCountdown ? (
          <View style={styles.countdownWrap}>
            <Text style={[styles.countdown, { color: copy.accent }]}>{countdownDisplay}</Text>
            <Text style={styles.countdownLabel}>restante</Text>
          </View>
        ) : (
          <View style={styles.countdownWrap}>
            <Text style={[styles.countdown, { color: copy.accent }]}>INFO</Text>
            <Text style={styles.countdownLabel}>aviso</Text>
          </View>
        )}
      </TouchableOpacity>
      {expanded && (
        <View style={[styles.details, { borderLeftColor: copy.accent }]}>
          {state.paused_reason_text && (
            <Text style={styles.detailText}>{state.paused_reason_text}</Text>
          )}
          {news && (
            <>
              <Text style={styles.detailRow}>
                {flagForCurrency(news.currency)}  {news.currency} · {impactStars(news.impact)}
              </Text>
              {news.time_utc && (
                <Text style={styles.detailRow}>
                  Horario: {formatResumeHHMM(news.time_utc)}
                </Text>
              )}
              <Text style={styles.detailRow}>
                Regla mentoría: sin nuevos trades ±30 min
              </Text>
            </>
          )}
          {!news && state.paused_reason === 'cooldown_after_losses' && (
            <Text style={styles.detailRow}>
              Pérdidas consecutivas: {state.consecutive_losses_today}
            </Text>
          )}
          {state.market_notice && !state.paused_reason && (
            <Text style={styles.detailRow}>{state.market_notice.message}</Text>
          )}
        </View>
      )}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginBottom: 12,
  },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 64,
    borderLeftWidth: 4,
    borderRadius: 14,
    paddingVertical: 10,
    paddingHorizontal: 14,
    gap: 12,
    // iOS 26 Liquid Glass subtle shadow
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  iconWrap: {
    width: 36,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(255,255,255,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: {
    fontSize: 11,
    fontWeight: '600',
  },
  textBlock: {
    flex: 1,
    flexDirection: 'column',
  },
  title: {
    fontFamily: theme.fonts.semibold,
    fontSize: 15,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    letterSpacing: 0,
  },
  subtitle: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    fontWeight: '400',
    color: theme.colors.textSecondary,
    marginTop: 2,
  },
  countdownWrap: {
    alignItems: 'flex-end',
    minWidth: 54,
  },
  countdown: {
    fontFamily: theme.fonts.semibold,
    fontSize: 17,
    fontWeight: '700',
    fontVariant: ['tabular-nums' as const],
    letterSpacing: 0,
  },
  countdownLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 0.3,
    marginTop: 2,
  },
  details: {
    marginTop: 6,
    marginLeft: 8,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: 'rgba(255,255,255,0.65)',
    borderLeftWidth: 2,
    borderRadius: 10,
  },
  detailText: {
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    color: theme.colors.textPrimary,
    marginBottom: 4,
  },
  detailRow: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
    marginTop: 2,
  },
});
