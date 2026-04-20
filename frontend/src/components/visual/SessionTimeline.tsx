/**
 * V3 — SessionTimeline
 * 24-hour horizontal bar showing trading sessions, news blackouts, and now-marker.
 * Pure View-based rendering (no SVG needed for simple segmented bar).
 */

import React, { useMemo, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
} from 'react-native';
import { theme } from '../../theme/apple-glass';
import { flagForCurrency } from '../../utils/flags';

export interface CalendarEventLite {
  time_utc?: string;
  currency?: string;
  title?: string;
  impact?: string;
}

interface SessionTimelineProps {
  nowUtc?: string | null;
  tradingHoursUtc?: string | null;   // "07:00-21:00"
  calendar?: CalendarEventLite[];    // today's events (optional)
}

const LONDON_START = 7;             // UTC
const LONDON_END = 13;
const OVERLAP_START = 13;
const OVERLAP_END = 17;
const NY_START = 17;
const NY_END = 21;

const COLOR_ASIA = '#E5E5EA';
const COLOR_LONDON = '#1E88E5';
const COLOR_OVERLAP = '#AF52DE';
const COLOR_NY = '#00C853';
const COLOR_OUT = '#E5E5EA';
const COLOR_NEWS = 'rgba(255, 149, 0, 0.55)';
const COLOR_NOW = '#FF3B30';

function hourColor(h: number, tradingStart: number, tradingEnd: number): string {
  if (h < tradingStart || h >= tradingEnd) return COLOR_OUT;
  if (h >= OVERLAP_START && h < OVERLAP_END) return COLOR_OVERLAP;
  if (h >= NY_START && h < NY_END) return COLOR_NY;
  if (h >= LONDON_START && h < LONDON_END) return COLOR_LONDON;
  return COLOR_ASIA;
}

function sessionNameForHour(h: number, tradingStart: number, tradingEnd: number): string {
  if (h < tradingStart || h >= tradingEnd) return 'Fuera de trading';
  if (h >= OVERLAP_START && h < OVERLAP_END) return 'London / NY overlap';
  if (h >= NY_START && h < NY_END) return 'New York';
  if (h >= LONDON_START && h < LONDON_END) return 'London';
  return 'Asia';
}

function parseTradingHours(range?: string | null): { start: number; end: number } {
  if (!range) return { start: 7, end: 21 };
  const m = /(\d{1,2}):\d{2}\s*-\s*(\d{1,2}):\d{2}/.exec(range);
  if (!m) return { start: 7, end: 21 };
  return { start: Number(m[1]), end: Number(m[2]) };
}

function nowHourUtc(nowUtc?: string | null): { h: number; m: number; totalFrac: number } {
  let d: Date;
  if (nowUtc) {
    const parsed = new Date(nowUtc);
    d = isNaN(parsed.getTime()) ? new Date() : parsed;
  } else {
    d = new Date();
  }
  const h = d.getUTCHours();
  const m = d.getUTCMinutes();
  return { h, m, totalFrac: (h + m / 60) / 24 };
}

export default function SessionTimeline({
  nowUtc,
  tradingHoursUtc,
  calendar = [],
}: SessionTimelineProps) {
  const { start: tradingStart, end: tradingEnd } = parseTradingHours(tradingHoursUtc);
  const { h: nowH, totalFrac } = nowHourUtc(nowUtc);
  const [selectedHour, setSelectedHour] = useState<number | null>(null);

  // news events mapped by UTC hour
  const eventsByHour = useMemo(() => {
    const byHour: Record<number, CalendarEventLite[]> = {};
    for (const ev of calendar) {
      if (!ev?.time_utc) continue;
      const d = new Date(ev.time_utc);
      if (isNaN(d.getTime())) continue;
      const now = new Date();
      // only keep events from today (UTC date)
      if (d.getUTCFullYear() !== now.getUTCFullYear() ||
          d.getUTCMonth() !== now.getUTCMonth() ||
          d.getUTCDate() !== now.getUTCDate()) continue;
      const h = d.getUTCHours();
      if (!byHour[h]) byHour[h] = [];
      byHour[h].push(ev);
    }
    return byHour;
  }, [calendar]);

  const hours = Array.from({ length: 24 }, (_, i) => i);
  const selectedEvents = selectedHour != null ? eventsByHour[selectedHour] || [] : [];

  return (
    <View style={styles.wrap}>
      <View style={styles.labelRow}>
        <Text style={styles.sessionLabel}>
          {sessionNameForHour(nowH, tradingStart, tradingEnd).toUpperCase()}
        </Text>
        <Text style={styles.nowLabel}>
          {String(nowH).padStart(2, '0')}:{String(nowHourUtc(nowUtc).m).padStart(2, '0')} UTC
        </Text>
      </View>

      <View style={styles.barOuter}>
        <View style={styles.bar}>
          {hours.map((h) => {
            const base = hourColor(h, tradingStart, tradingEnd);
            const hasNews = !!eventsByHour[h];
            return (
              <TouchableOpacity
                key={h}
                activeOpacity={0.7}
                onPress={() => setSelectedHour(selectedHour === h ? null : h)}
                style={[styles.segment, { backgroundColor: base }]}
              >
                {hasNews && <View style={styles.newsOverlay} />}
              </TouchableOpacity>
            );
          })}
        </View>
        {/* Now-marker */}
        <View
          pointerEvents="none"
          style={[
            styles.nowMarker,
            { left: `${totalFrac * 100}%` },
          ]}
        />
      </View>

      <View style={styles.tickRow}>
        {[0, 6, 12, 18, 24].map((h) => (
          <Text key={h} style={[styles.tickLabel, { left: `${(h / 24) * 100}%` }]}>
            {String(h % 24).padStart(2, '0')}
          </Text>
        ))}
      </View>

      <View style={styles.legend}>
        <LegendDot color={COLOR_LONDON} label="London" />
        <LegendDot color={COLOR_OVERLAP} label="Overlap" />
        <LegendDot color={COLOR_NY} label="NY" />
        <LegendDot color={COLOR_NEWS} label="News" />
      </View>

      {selectedHour != null && (
        <View style={styles.tooltip}>
          <Text style={styles.tooltipTitle}>
            {String(selectedHour).padStart(2, '0')}:00 · {sessionNameForHour(selectedHour, tradingStart, tradingEnd)}
          </Text>
          {selectedEvents.length === 0 ? (
            <Text style={styles.tooltipBody}>Sin eventos de alto impacto</Text>
          ) : (
            selectedEvents.map((ev, i) => (
              <Text key={i} style={styles.tooltipBody} numberOfLines={2}>
                {flagForCurrency(ev.currency)}  {ev.title}
              </Text>
            ))
          )}
        </View>
      )}
    </View>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendSwatch, { backgroundColor: color }]} />
      <Text style={styles.legendLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 6,
  },
  labelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'baseline',
    marginBottom: 4,
  },
  sessionLabel: {
    fontFamily: theme.fonts.semibold,
    fontSize: 13,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    letterSpacing: 0.3,
  },
  nowLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.textSecondary,
    letterSpacing: 0.3,
    fontVariant: ['tabular-nums' as const],
  },
  barOuter: {
    position: 'relative',
    width: '100%',
    height: 22,
  },
  bar: {
    flexDirection: 'row',
    width: '100%',
    height: '100%',
    borderRadius: 4,
    overflow: 'hidden',
    backgroundColor: COLOR_ASIA,
  },
  segment: {
    flex: 1,
    height: '100%',
    marginRight: 1,
  },
  newsOverlay: {
    position: 'absolute',
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    backgroundColor: COLOR_NEWS,
  },
  nowMarker: {
    position: 'absolute',
    top: -3,
    bottom: -3,
    width: 2,
    marginLeft: -1,
    backgroundColor: COLOR_NOW,
    borderRadius: 1,
  },
  tickRow: {
    position: 'relative',
    height: 14,
    marginTop: 2,
  },
  tickLabel: {
    position: 'absolute',
    fontFamily: theme.fonts.medium,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 0.3,
    transform: [{ translateX: -8 }],
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 4,
    gap: 10,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  legendSwatch: {
    width: 8,
    height: 8,
    borderRadius: 2,
  },
  legendLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
  tooltip: {
    marginTop: 6,
    paddingVertical: 8,
    paddingHorizontal: 10,
    backgroundColor: 'rgba(255,255,255,0.75)',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.04)',
  },
  tooltipTitle: {
    fontFamily: theme.fonts.semibold,
    fontSize: 12,
    fontWeight: '600',
    color: theme.colors.textPrimary,
    marginBottom: 2,
  },
  tooltipBody: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textSecondary,
    marginTop: 1,
  },
});
