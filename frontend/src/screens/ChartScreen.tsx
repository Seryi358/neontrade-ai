/**
 * NeonTrade AI - Chart Screen
 * Custom candlestick chart view with key levels, EMAs, and strategy info.
 * Built entirely with React Native View primitives (no external chart libraries).
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Dimensions,
  RefreshControl,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, authFetch, getScoreColor, getTrendColor, getTrendIcon } from '../services/api';

// ─── Types ──────────────────────────────────────────────────────────────────

interface WatchlistItem {
  instrument: string;
  score: number;
  trend: string;
}

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface PriceData {
  instrument: string;
  bid: number;
  ask: number;
  spread: number;
}

interface KeyLevels {
  support: number[];
  resistance: number[];
}

interface AnalysisSummary {
  score: number;
  trend: string;
  strategy_name: string | null;
  strategy_color: string | null;
  key_levels: KeyLevels;
  ema_20: number[];
  ema_50: number[];
}

// ─── Constants ──────────────────────────────────────────────────────────────

const SCREEN_WIDTH = Dimensions.get('window').width;
const SCREEN_HEIGHT = Dimensions.get('window').height;

const TIMEFRAMES = ['M5', 'M15', 'H1', 'H4', 'D', 'W'] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

const GRANULARITY_MAP: Record<Timeframe, string> = {
  M5: 'M5',
  M15: 'M15',
  H1: 'H1',
  H4: 'H4',
  D: 'D',
  W: 'W',
};

const CHART_PADDING_TOP = 20;
const CHART_PADDING_BOTTOM = 20;
const CANDLE_COUNT = 80;
const PRICE_LABEL_WIDTH = 65;

// ─── Helpers ────────────────────────────────────────────────────────────────

const formatPrice = (price: number, instrument: string) => {
  // JPY pairs have 3 decimals, others 5
  const isJpy = instrument?.toUpperCase().includes('JPY');
  return price.toFixed(isJpy ? 3 : 5);
};

const _strategyColor = (name: string | null): string | null => {
  if (!name) return null;
  const upper = name.toUpperCase();
  if (upper.includes('BLUE')) return '#00f0ff';
  if (upper.includes('RED')) return '#ff2e63';
  if (upper.includes('GREEN')) return '#00ff88';
  if (upper.includes('PINK')) return '#eb4eca';
  if (upper.includes('WHITE')) return '#f0e6ff';
  if (upper.includes('BLACK')) return '#888888';
  return '#eb4eca';
};

// ─── Component ──────────────────────────────────────────────────────────────

export default function ChartScreen() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selectedInstrument, setSelectedInstrument] = useState<string>('');
  const [timeframe, setTimeframe] = useState<Timeframe>('H1');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [price, setPrice] = useState<PriceData | null>(null);
  const [analysisSummary, setAnalysisSummary] = useState<AnalysisSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  // ── Data Fetching ───────────────────────────────────────────────────────

  // Load watchlist once
  useEffect(() => {
    const loadWatchlist = async () => {
      try {
        const res = await authFetch(`${API_URL}/api/v1/watchlist`);
        if (!res.ok) return;
        const data = await res.json();
        setWatchlist(Array.isArray(data) ? data : []);
        if (data.length > 0) {
          setSelectedInstrument((prev) => prev || data[0].instrument);
        }
      } catch (err) {
        console.error('Failed to fetch watchlist:', err);
      }
    };
    loadWatchlist();
  }, []);

  // Fetch chart data when instrument or timeframe changes
  const fetchChartData = useCallback(async () => {
    if (!selectedInstrument) return;
    setLoading(true);
    setError(null);
    try {
      const [candlesRes, priceRes, analysisRes] = await Promise.all([
        authFetch(
          `${API_URL}/api/v1/candles/${selectedInstrument}?granularity=${GRANULARITY_MAP[timeframe]}&count=${CANDLE_COUNT + 50}`
        ),
        authFetch(`${API_URL}/api/v1/price/${selectedInstrument}`),
        authFetch(`${API_URL}/api/v1/analysis/${selectedInstrument}`),
      ]);

      if (candlesRes.ok) {
        const candleData = await candlesRes.json();
        setCandles(Array.isArray(candleData) ? candleData : candleData.candles || []);
      }
      if (priceRes.ok) {
        setPrice(await priceRes.json());
      }
      if (analysisRes.ok) {
        const analysisData = await analysisRes.json();
        // Extract key levels from analysis (API uses "supports"/"resistances" plural)
        const keyLevels = analysisData.key_levels || {};
        const supports = keyLevels.supports || keyLevels.support || [];
        const resistances = keyLevels.resistances || keyLevels.resistance || [];

        // Extract EMA values from the ema_values dict
        // The API returns: {"EMA_H1_20": val, "EMA_H1_50": val, "EMA_H4_20": val, ...}
        const emaValues = analysisData.ema_values || {};
        const ema20Val = emaValues[`EMA_H1_20`] || emaValues[`EMA_H4_20`] || null;
        const ema50Val = emaValues[`EMA_H1_50`] || emaValues[`EMA_H4_50`] || null;

        // Strategy info from explanation
        const strategyDetected = analysisData.explanation?.strategy_detected || null;

        setAnalysisSummary({
          score: analysisData.score ?? 0,
          trend: analysisData.htf_trend ?? 'neutral',
          strategy_name: strategyDetected,
          strategy_color: strategyDetected ? _strategyColor(strategyDetected) : null,
          key_levels: {
            support: supports,
            resistance: resistances,
          },
          ema_20: ema20Val ? [ema20Val] : [],
          ema_50: ema50Val ? [ema50Val] : [],
        });
      }
    } catch (err: any) {
      console.error('Failed to fetch chart data:', err);
      setError(err.message || 'Error al cargar datos');
    } finally {
      setLoading(false);
    }
  }, [selectedInstrument, timeframe]);

  useEffect(() => {
    if (selectedInstrument) {
      fetchChartData();
      const interval = setInterval(fetchChartData, 10000);
      return () => clearInterval(interval);
    }
  }, [selectedInstrument, timeframe, fetchChartData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchChartData();
    setRefreshing(false);
  };

  // ── Chart Calculations ────────────────────────────────────────────────────

  const chartWidth = SCREEN_WIDTH - theme.spacing.md * 2 - PRICE_LABEL_WIDTH;
  const chartHeight = SCREEN_HEIGHT * 0.48;

  const visibleCandles = useMemo(() => {
    return candles.slice(-CANDLE_COUNT);
  }, [candles]);

  const { priceMin, priceMax, priceRange } = useMemo(() => {
    if (visibleCandles.length === 0) return { priceMin: 0, priceMax: 1, priceRange: 1 };

    let min = Infinity;
    let max = -Infinity;
    for (const c of visibleCandles) {
      if (c.low < min) min = c.low;
      if (c.high > max) max = c.high;
    }

    // Include key levels in range
    if (analysisSummary?.key_levels) {
      for (const s of analysisSummary.key_levels.support) {
        if (s < min) min = s;
        if (s > max) max = s;
      }
      for (const r of analysisSummary.key_levels.resistance) {
        if (r < min) min = r;
        if (r > max) max = r;
      }
    }

    const range = max - min;
    const padding = range * 0.08;
    return {
      priceMin: min - padding,
      priceMax: max + padding,
      priceRange: range + padding * 2,
    };
  }, [visibleCandles, analysisSummary]);

  const priceToY = useCallback(
    (p: number) => {
      if (priceRange === 0) return chartHeight / 2;
      return (
        CHART_PADDING_TOP +
        ((priceMax - p) / priceRange) * (chartHeight - CHART_PADDING_TOP - CHART_PADDING_BOTTOM)
      );
    },
    [priceMax, priceRange, chartHeight]
  );

  const candleWidth = useMemo(() => {
    if (visibleCandles.length === 0) return 6;
    const w = Math.floor(chartWidth / visibleCandles.length);
    return Math.max(3, Math.min(w, 14));
  }, [chartWidth, visibleCandles.length]);

  const bodyWidth = Math.max(1, candleWidth - 2);
  const wickWidth = 1;

  // ── EMA line Y values ─────────────────────────────────────────────────────

  const ema20Points = useMemo(() => {
    if (!analysisSummary?.ema_20 || analysisSummary.ema_20.length === 0) return [];
    return analysisSummary.ema_20.slice(-visibleCandles.length);
  }, [analysisSummary, visibleCandles.length]);

  const ema50Points = useMemo(() => {
    if (!analysisSummary?.ema_50 || analysisSummary.ema_50.length === 0) return [];
    return analysisSummary.ema_50.slice(-visibleCandles.length);
  }, [analysisSummary, visibleCandles.length]);

  // ── Price Grid Lines ──────────────────────────────────────────────────────

  const gridLines = useMemo(() => {
    if (priceRange === 0) return [];
    const lines: number[] = [];
    const step = priceRange / 5;
    for (let i = 0; i <= 5; i++) {
      lines.push(priceMin + step * i);
    }
    return lines;
  }, [priceMin, priceRange]);

  // ── Render Methods ────────────────────────────────────────────────────────

  const renderPicker = () => (
    <View style={styles.pickerContainer}>
      <TouchableOpacity
        style={styles.pickerButton}
        onPress={() => setPickerOpen(!pickerOpen)}
        activeOpacity={0.7}
      >
        <Text style={styles.pickerText}>
          {selectedInstrument ? selectedInstrument.replace('_', '/') : 'Seleccionar...'}
        </Text>
        <Text style={styles.pickerChevron}>{pickerOpen ? '▾' : '▸'}</Text>
      </TouchableOpacity>

      {pickerOpen && (
        <View style={styles.pickerDropdown}>
          <ScrollView style={styles.pickerScroll} nestedScrollEnabled>
            {watchlist.map((item) => (
              <TouchableOpacity
                key={item.instrument}
                style={[
                  styles.pickerOption,
                  item.instrument === selectedInstrument && styles.pickerOptionActive,
                ]}
                onPress={() => {
                  setSelectedInstrument(item.instrument);
                  setPickerOpen(false);
                }}
              >
                <Text
                  style={[
                    styles.pickerOptionText,
                    item.instrument === selectedInstrument && { color: theme.colors.neonPink },
                  ]}
                >
                  {item.instrument.replace('_', '/')}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}
    </View>
  );

  const renderTimeframeButtons = () => (
    <View style={styles.tfButtonRow}>
      {TIMEFRAMES.map((tf) => (
        <TouchableOpacity
          key={tf}
          style={[styles.tfButton, tf === timeframe && styles.tfButtonActive]}
          onPress={() => setTimeframe(tf)}
          activeOpacity={0.7}
        >
          <Text style={[styles.tfButtonText, tf === timeframe && styles.tfButtonTextActive]}>
            {tf}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderPriceOverlay = () => {
    if (!price) return null;
    const spread = price.spread ?? (price.ask - price.bid);
    return (
      <View style={styles.priceOverlay}>
        <Text style={styles.priceBid}>
          BID {formatPrice(price.bid, selectedInstrument)}
        </Text>
        <Text style={styles.priceSpread}>
          SPR {typeof spread === 'number' ? spread.toFixed(1) : '---'}
        </Text>
        <Text style={styles.priceAsk}>
          ASK {formatPrice(price.ask, selectedInstrument)}
        </Text>
      </View>
    );
  };

  const renderChart = () => {
    if (visibleCandles.length === 0) return null;

    return (
      <View style={[styles.chartArea, { height: chartHeight }]}>
        {/* Grid lines */}
        {gridLines.map((p, i) => {
          const y = priceToY(p);
          return (
            <View key={`grid-${i}`} style={[styles.gridLine, { top: y }]}>
              <View style={styles.gridDash} />
            </View>
          );
        })}

        {/* Price labels on right side */}
        <View style={styles.priceLabelsColumn}>
          {gridLines.map((p, i) => {
            const y = priceToY(p);
            return (
              <Text
                key={`label-${i}`}
                style={[styles.priceLabel, { top: y - 6 }]}
              >
                {formatPrice(p, selectedInstrument)}
              </Text>
            );
          })}
        </View>

        {/* Key Levels */}
        {analysisSummary?.key_levels?.support?.map((level, i) => {
          const y = priceToY(level);
          if (y < 0 || y > chartHeight) return null;
          return (
            <View key={`sup-${i}`} style={[styles.keyLevel, styles.supportLevel, { top: y }]}>
              <Text style={styles.supportLevelText}>S {formatPrice(level, selectedInstrument)}</Text>
            </View>
          );
        })}
        {analysisSummary?.key_levels?.resistance?.map((level, i) => {
          const y = priceToY(level);
          if (y < 0 || y > chartHeight) return null;
          return (
            <View key={`res-${i}`} style={[styles.keyLevel, styles.resistanceLevel, { top: y }]}>
              <Text style={styles.resistanceLevelText}>R {formatPrice(level, selectedInstrument)}</Text>
            </View>
          );
        })}

        {/* EMA Lines (horizontal lines at current EMA values) */}
        {ema20Points.length > 0 && (() => {
          const y = priceToY(ema20Points[0]);
          if (y < 0 || y > chartHeight) return null;
          return (
            <View key="ema20-line" style={[styles.emaLine, { top: y, borderColor: theme.colors.neonCyan }]}>
              <Text style={[styles.emaLabel, { color: theme.colors.neonCyan }]}>EMA 20</Text>
            </View>
          );
        })()}
        {ema50Points.length > 0 && (() => {
          const y = priceToY(ema50Points[0]);
          if (y < 0 || y > chartHeight) return null;
          return (
            <View key="ema50-line" style={[styles.emaLine, { top: y, borderColor: theme.colors.neonPink }]}>
              <Text style={[styles.emaLabel, { color: theme.colors.neonPink }]}>EMA 50</Text>
            </View>
          );
        })()}

        {/* Candlesticks */}
        {visibleCandles.map((candle, i) => {
          const isBullish = candle.close >= candle.open;
          const color = isBullish ? theme.colors.chartBullish : theme.colors.chartBearish;

          const bodyTop = priceToY(Math.max(candle.open, candle.close));
          const bodyBottom = priceToY(Math.min(candle.open, candle.close));
          const bodyHeight = Math.max(1, bodyBottom - bodyTop);

          const wickTop = priceToY(candle.high);
          const wickBottom = priceToY(candle.low);
          const wickHeight = Math.max(1, wickBottom - wickTop);

          const x = i * candleWidth;

          return (
            <View key={i} style={{ position: 'absolute', left: x, width: candleWidth }}>
              {/* Wick */}
              <View
                style={{
                  position: 'absolute',
                  left: (candleWidth - wickWidth) / 2,
                  top: wickTop,
                  width: wickWidth,
                  height: wickHeight,
                  backgroundColor: color,
                }}
              />
              {/* Body */}
              <View
                style={{
                  position: 'absolute',
                  left: (candleWidth - bodyWidth) / 2,
                  top: bodyTop,
                  width: bodyWidth,
                  height: bodyHeight,
                  backgroundColor: isBullish ? 'transparent' : color,
                  borderWidth: 1,
                  borderColor: color,
                }}
              />
            </View>
          );
        })}

        {/* Current price line */}
        {price && (
          <View
            style={[
              styles.currentPriceLine,
              { top: priceToY(price.bid) },
            ]}
          >
            <View style={styles.currentPriceDash} />
            <View style={styles.currentPriceTag}>
              <Text style={styles.currentPriceText}>
                {formatPrice(price.bid, selectedInstrument)}
              </Text>
            </View>
          </View>
        )}
      </View>
    );
  };

  const renderEmaLegend = () => {
    if (ema20Points.length === 0 && ema50Points.length === 0) return null;
    return (
      <View style={styles.emaLegend}>
        {ema20Points.length > 0 && (
          <View style={styles.emaLegendItem}>
            <View style={[styles.emaLegendDot, { backgroundColor: theme.colors.neonCyan }]} />
            <Text style={styles.emaLegendText}>EMA 20</Text>
          </View>
        )}
        {ema50Points.length > 0 && (
          <View style={styles.emaLegendItem}>
            <View style={[styles.emaLegendDot, { backgroundColor: theme.colors.neonPink }]} />
            <Text style={styles.emaLegendText}>EMA 50</Text>
          </View>
        )}
      </View>
    );
  };

  const renderBottomBar = () => {
    if (!analysisSummary) return null;

    const stratColor = analysisSummary.strategy_color
      ? {
          BLUE: '#0088ff',
          RED: '#ff2e63',
          PINK: '#ff69b4',
          WHITE: '#ffffff',
          BLACK: '#333333',
          GREEN: '#00ff88',
        }[analysisSummary.strategy_color.toUpperCase()] || theme.colors.textMuted
      : theme.colors.textMuted;

    return (
      <View style={styles.bottomBar}>
        <View style={styles.bottomItem}>
          <Text style={styles.bottomLabel}>TREND</Text>
          <Text style={[styles.bottomValue, { color: getTrendColor(analysisSummary.trend) }]}>
            {getTrendIcon(analysisSummary.trend)} {analysisSummary.trend?.toUpperCase() || '---'}
          </Text>
        </View>
        <View style={styles.bottomDivider} />
        <View style={styles.bottomItem}>
          <Text style={styles.bottomLabel}>SCORE</Text>
          <Text style={[styles.bottomValue, { color: getScoreColor(analysisSummary.score) }]}>
            {analysisSummary.score.toFixed(0)}
          </Text>
        </View>
        <View style={styles.bottomDivider} />
        <View style={styles.bottomItem}>
          <Text style={styles.bottomLabel}>ESTRATEGIA</Text>
          {analysisSummary.strategy_name ? (
            <View style={styles.bottomStratRow}>
              <View style={[styles.stratDot, { backgroundColor: stratColor }]} />
              <Text style={[styles.bottomValue, { color: stratColor, fontSize: 10 }]} numberOfLines={1}>
                {analysisSummary.strategy_name}
              </Text>
            </View>
          ) : (
            <Text style={[styles.bottomValue, { color: theme.colors.textMuted }]}>---</Text>
          )}
        </View>
      </View>
    );
  };

  // ── Main Render ───────────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>CHART</Text>
      </View>

      {/* Instrument Picker */}
      {renderPicker()}

      <ScrollView
        style={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      >
        {/* Timeframe Buttons */}
        {renderTimeframeButtons()}

        {/* Price Overlay */}
        {renderPriceOverlay()}

        {loading && candles.length === 0 ? (
          <View style={styles.centerMessage}>
            <ActivityIndicator size="large" color={theme.colors.neonPink} />
            <Text style={styles.loadingText}>Cargando velas...</Text>
          </View>
        ) : error && candles.length === 0 ? (
          <View style={styles.centerMessage}>
            <Text style={styles.errorIcon}>!</Text>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={fetchChartData}>
              <Text style={styles.retryButtonText}>REINTENTAR</Text>
            </TouchableOpacity>
          </View>
        ) : visibleCandles.length > 0 ? (
          <>
            {/* Chart Container */}
            <View style={styles.chartContainer}>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={{
                  width: Math.max(chartWidth, visibleCandles.length * candleWidth + PRICE_LABEL_WIDTH),
                }}
              >
                {renderChart()}
              </ScrollView>
            </View>

            {/* EMA Legend */}
            {renderEmaLegend()}
          </>
        ) : (
          <View style={styles.centerMessage}>
            <Text style={styles.emptyText}>Selecciona un instrumento</Text>
          </View>
        )}

        {/* Bottom Info Bar */}
        {renderBottomBar()}

        <View style={{ height: theme.spacing.xxl }} />
      </ScrollView>
    </View>
  );
}

// ─── Styles ─────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  header: {
    alignItems: 'center',
    paddingTop: theme.spacing.xl,
    paddingBottom: theme.spacing.xs,
    paddingHorizontal: theme.spacing.md,
  },
  title: {
    fontFamily: theme.fonts.primary,
    fontSize: 24,
    color: theme.colors.neonPink,
    letterSpacing: 6,
    textShadowColor: theme.colors.neonPinkGlow,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 15,
  },
  scrollContent: {
    flex: 1,
    paddingHorizontal: theme.spacing.md,
  },

  // ── Picker ──────────────────────────────────────────
  pickerContainer: {
    paddingHorizontal: theme.spacing.md,
    paddingTop: theme.spacing.sm,
    zIndex: 100,
  },
  pickerButton: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.neonPink,
    borderRadius: theme.borderRadius.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  pickerText: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
  pickerChevron: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.neonPink,
  },
  pickerDropdown: {
    backgroundColor: theme.colors.backgroundDark,
    borderWidth: 1,
    borderColor: theme.colors.neonPink,
    borderTopWidth: 0,
    borderBottomLeftRadius: theme.borderRadius.md,
    borderBottomRightRadius: theme.borderRadius.md,
    maxHeight: 200,
  },
  pickerScroll: {
    maxHeight: 200,
  },
  pickerOption: {
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  pickerOptionActive: {
    backgroundColor: theme.colors.backgroundLight,
  },
  pickerOptionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.textSecondary,
    letterSpacing: 1,
  },

  // ── Timeframe Buttons ───────────────────────────────
  tfButtonRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
    gap: 4,
  },
  tfButton: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: theme.spacing.sm - 2,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    backgroundColor: theme.colors.backgroundCard,
  },
  tfButtonActive: {
    borderColor: theme.colors.neonPink,
    backgroundColor: theme.colors.backgroundLight,
  },
  tfButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  tfButtonTextActive: {
    color: theme.colors.neonPink,
  },

  // ── Price Overlay ───────────────────────────────────
  priceOverlay: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: 10,
    marginBottom: theme.spacing.xs,
  },
  priceBid: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonGreen,
    letterSpacing: 1,
  },
  priceSpread: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  priceAsk: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonRed,
    letterSpacing: 1,
  },

  // ── Chart ───────────────────────────────────────────
  chartContainer: {
    backgroundColor: theme.colors.backgroundDark,
    borderRadius: theme.borderRadius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    overflow: 'hidden',
  },
  chartArea: {
    position: 'relative',
    overflow: 'hidden',
  },
  gridLine: {
    position: 'absolute',
    left: 0,
    right: PRICE_LABEL_WIDTH,
    height: 1,
  },
  gridDash: {
    flex: 1,
    height: 1,
    backgroundColor: theme.colors.chartGrid,
    opacity: 0.5,
  },
  priceLabelsColumn: {
    position: 'absolute',
    right: 0,
    top: 0,
    bottom: 0,
    width: PRICE_LABEL_WIDTH,
  },
  priceLabel: {
    position: 'absolute',
    right: 4,
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
  },

  // ── Key Levels ──────────────────────────────────────
  keyLevel: {
    position: 'absolute',
    left: 0,
    right: PRICE_LABEL_WIDTH,
    height: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  supportLevel: {
    borderTopWidth: 1,
    borderStyle: 'dashed' as any,
    borderColor: 'rgba(57, 255, 20, 0.4)',
  },
  resistanceLevel: {
    borderTopWidth: 1,
    borderStyle: 'dashed' as any,
    borderColor: 'rgba(255, 7, 58, 0.4)',
  },
  supportLevelText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: theme.colors.neonGreen,
    backgroundColor: theme.colors.backgroundDark,
    paddingHorizontal: 2,
    position: 'absolute',
    left: 2,
    top: -8,
  },
  resistanceLevelText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: theme.colors.neonRed,
    backgroundColor: theme.colors.backgroundDark,
    paddingHorizontal: 2,
    position: 'absolute',
    left: 2,
    top: -8,
  },

  // ── EMA Dots ────────────────────────────────────────
  emaDot: {
    position: 'absolute',
    width: 2,
    height: 2,
    borderRadius: 1,
  },
  emaLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 0,
    borderTopWidth: 1,
    borderStyle: 'dashed',
    flexDirection: 'row',
    alignItems: 'center',
  },
  emaLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    position: 'absolute',
    right: 2,
    top: -10,
    opacity: 0.8,
  },

  // ── Current Price Line ──────────────────────────────
  currentPriceLine: {
    position: 'absolute',
    left: 0,
    right: 0,
    height: 1,
    flexDirection: 'row',
    alignItems: 'center',
  },
  currentPriceDash: {
    flex: 1,
    height: 1,
    backgroundColor: theme.colors.neonCyan,
    opacity: 0.5,
  },
  currentPriceTag: {
    backgroundColor: theme.colors.neonCyan,
    paddingHorizontal: 4,
    paddingVertical: 1,
    borderRadius: 2,
  },
  currentPriceText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.backgroundDark,
    fontWeight: 'bold',
  },

  // ── EMA Legend ──────────────────────────────────────
  emaLegend: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 16,
    marginTop: theme.spacing.xs,
    marginBottom: theme.spacing.xs,
  },
  emaLegendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  emaLegendDot: {
    width: 8,
    height: 3,
    borderRadius: 1,
  },
  emaLegendText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },

  // ── Bottom Bar ──────────────────────────────────────
  bottomBar: {
    flexDirection: 'row',
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.borderRadius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing.sm + 2,
    marginTop: theme.spacing.sm,
    alignItems: 'center',
  },
  bottomItem: {
    flex: 1,
    alignItems: 'center',
  },
  bottomLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: 2,
  },
  bottomValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  bottomDivider: {
    width: 1,
    height: 28,
    backgroundColor: theme.colors.border,
  },
  bottomStratRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  stratDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },

  // ── States ──────────────────────────────────────────
  centerMessage: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.xxl * 2,
  },
  loadingText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginTop: theme.spacing.md,
  },
  errorIcon: {
    fontFamily: theme.fonts.mono,
    fontSize: 36,
    color: theme.colors.neonRed,
    fontWeight: 'bold',
    borderWidth: 2,
    borderColor: theme.colors.neonRed,
    borderRadius: 20,
    width: 40,
    height: 40,
    textAlign: 'center',
    lineHeight: 38,
    marginBottom: theme.spacing.md,
  },
  errorText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.neonRed,
    letterSpacing: 1,
    textAlign: 'center',
    marginBottom: theme.spacing.md,
  },
  retryButton: {
    borderWidth: 1,
    borderColor: theme.colors.neonPink,
    borderRadius: theme.borderRadius.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
  },
  retryButtonText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.neonPink,
    letterSpacing: 2,
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
  },
});
