/**
 * NeonTrade AI - Chart Screen
 * Professional TradingView lightweight-charts integration with cyberpunk theme.
 *
 * Web: Uses lightweight-charts directly in a DOM div.
 * Native: Falls back to the custom React Native candlestick renderer.
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Dimensions,
  RefreshControl,
  Platform,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, authFetch, getScoreColor, getTrendColor, getTrendIcon, STRATEGY_COLORS } from '../services/api';

// ─── TradingView lightweight-charts (web only) ─────────────────────────────
let createChart: any;
let ColorType: any;
let CrosshairMode: any;
let LineStyle: any;
let PriceScaleMode: any;

if (Platform.OS === 'web') {
  try {
    const lc = require('lightweight-charts');
    createChart = lc.createChart;
    ColorType = lc.ColorType;
    CrosshairMode = lc.CrosshairMode;
    LineStyle = lc.LineStyle;
    PriceScaleMode = lc.PriceScaleMode;
  } catch (e) {
    console.warn('lightweight-charts not available:', e);
  }
}

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

interface PivotPoints {
  P?: number;
  S1?: number;
  S2?: number;
  S3?: number;
  R1?: number;
  R2?: number;
  R3?: number;
}

interface AnalysisSummary {
  score: number;
  trend: string;
  strategy_name: string | null;
  strategy_color: string | null;
  key_levels: KeyLevels;
  ema_20: number[];
  ema_50: number[];
  pivot_points: PivotPoints;
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

const CANDLE_COUNT = 120;

// ─── Chart Color Theme ─────────────────────────────────────────────────────

const CHART_COLORS = {
  background: '#0a0713',
  gridLines: '#1a1535',
  candleUp: '#00ff88',
  candleDown: '#ff2e63',
  volumeUp: 'rgba(0, 255, 136, 0.3)',
  volumeDown: 'rgba(255, 46, 99, 0.3)',
  crosshair: '#eb4eca',
  ema20: '#00f0ff',
  ema50: '#eb4eca',
  support: '#00ff88',
  resistance: '#ff2e63',
  pivot: '#ffb800',
  textColor: '#8892a0',
  currentPrice: '#00f0ff',
};

// ─── Helpers ────────────────────────────────────────────────────────────────

const formatPrice = (price: number, instrument: string) => {
  const isJpy = instrument?.toUpperCase().includes('JPY');
  return price.toFixed(isJpy ? 3 : 5);
};

const _strategyColor = (name: string | null): string | null => {
  if (!name) return null;
  const upper = name.toUpperCase();
  if (upper.includes('BLUE')) return STRATEGY_COLORS.BLUE;
  if (upper.includes('RED')) return STRATEGY_COLORS.RED;
  if (upper.includes('GREEN')) return STRATEGY_COLORS.GREEN;
  if (upper.includes('PINK')) return STRATEGY_COLORS.PINK;
  if (upper.includes('WHITE')) return STRATEGY_COLORS.WHITE;
  if (upper.includes('BLACK')) return STRATEGY_COLORS.BLACK;
  return STRATEGY_COLORS.DETECTED;
};

/**
 * Convert candle time string to a lightweight-charts compatible timestamp.
 * lightweight-charts v4 expects Unix timestamp in seconds (UTCTimestamp).
 */
const parseCandleTime = (timeStr: string): number => {
  const d = new Date(timeStr);
  return Math.floor(d.getTime() / 1000);
};

/**
 * Calculate EMA from close prices.
 */
const calculateEMA = (closes: number[], period: number): number[] => {
  if (closes.length === 0) return [];
  const k = 2 / (period + 1);
  const ema: number[] = [closes[0]];
  for (let i = 1; i < closes.length; i++) {
    ema.push(closes[i] * k + ema[i - 1] * (1 - k));
  }
  return ema;
};

// ─── Native Chart Helpers (fallback for non-web) ───────────────────────────

const CHART_PADDING_TOP = 20;
const CHART_PADDING_BOTTOM = 20;
const PRICE_LABEL_WIDTH = 65;

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

  // Refs for TradingView chart (web only)
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<any>(null);
  const candlestickSeriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const ema20SeriesRef = useRef<any>(null);
  const ema50SeriesRef = useRef<any>(null);
  const priceLinesRef = useRef<any[]>([]);
  const chartCleanupRef = useRef<(() => void) | null>(null);

  // ── Data Fetching ───────────────────────────────────────────────────────

  useEffect(() => {
    const FALLBACK_PAIRS = [
      'EUR_USD', 'GBP_USD', 'USD_JPY', 'AUD_USD', 'USD_CAD',
      'EUR_GBP', 'EUR_JPY', 'GBP_JPY',
    ];
    const loadWatchlist = async () => {
      try {
        const res = await authFetch(`${API_URL}/api/v1/watchlist`);
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : [];
          if (items.length > 0) {
            setWatchlist(items);
            setSelectedInstrument((prev) => prev || items[0].instrument);
            return;
          }
        }
      } catch (err) {
        console.error('Failed to fetch watchlist:', err);
      }
      const fallback = FALLBACK_PAIRS.map(p => ({ instrument: p, score: 0, trend: 'neutral' }));
      setWatchlist(fallback);
      setSelectedInstrument((prev) => prev || fallback[0].instrument);
    };
    loadWatchlist();
  }, []);

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
      } else {
        const errData = await candlesRes.json().catch(() => ({ detail: '' }));
        setError(errData.detail || `Error al cargar velas (HTTP ${candlesRes.status})`);
      }
      if (priceRes.ok) {
        setPrice(await priceRes.json());
      }
      if (analysisRes.ok) {
        const analysisData = await analysisRes.json();
        const keyLevels = analysisData.key_levels || {};
        const supports = keyLevels.supports || keyLevels.support || [];
        const resistances = keyLevels.resistances || keyLevels.resistance || [];

        const emaValues = analysisData.ema_values || {};
        const ema20Val = emaValues[`EMA_H1_20`] || emaValues[`EMA_H4_20`] || null;
        const ema50Val = emaValues[`EMA_H1_50`] || emaValues[`EMA_H4_50`] || null;

        const strategyDetected = analysisData.explanation?.strategy_detected || null;
        const pivotPoints = analysisData.pivot_points || {};

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
          pivot_points: pivotPoints,
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

  // ── TradingView Chart (Web) ─────────────────────────────────────────────

  // Initialize chart via callback ref — fires when the div actually mounts in the DOM.
  // This fixes the timing issue where useEffect([]) ran before the div existed.
  const initChartRef = useCallback((el: HTMLDivElement | null) => {
    // Cleanup previous instance
    if (chartCleanupRef.current) {
      chartCleanupRef.current();
      chartCleanupRef.current = null;
    }

    if (!el) {
      chartContainerRef.current = null;
      return;
    }
    if (Platform.OS !== 'web' || !createChart) return;

    chartContainerRef.current = el;

    const chartWidth = el.clientWidth || SCREEN_WIDTH - 32;
    const chartHeight = Math.min(SCREEN_HEIGHT * 0.55, 500);

    const chart = createChart(el, {
      width: chartWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: CHART_COLORS.background },
        textColor: CHART_COLORS.textColor,
        fontFamily: "'Terminess Nerd Font', 'Fira Code', 'Courier New', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: CHART_COLORS.gridLines, style: 1 },
        horzLines: { color: CHART_COLORS.gridLines, style: 1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: CHART_COLORS.crosshair,
          width: 1,
          style: 2,
          labelBackgroundColor: CHART_COLORS.crosshair,
        },
        horzLine: {
          color: CHART_COLORS.crosshair,
          width: 1,
          style: 2,
          labelBackgroundColor: CHART_COLORS.crosshair,
        },
      },
      rightPriceScale: {
        borderColor: CHART_COLORS.gridLines,
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: CHART_COLORS.gridLines,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 5,
        barSpacing: 8,
      },
      handleScale: {
        axisPressedMouseMove: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
      },
    });

    // Candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: CHART_COLORS.candleUp,
      downColor: CHART_COLORS.candleDown,
      borderUpColor: CHART_COLORS.candleUp,
      borderDownColor: CHART_COLORS.candleDown,
      wickUpColor: CHART_COLORS.candleUp,
      wickDownColor: CHART_COLORS.candleDown,
    });

    // Volume series (histogram in separate pane area via priceScaleId)
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });

    // Configure volume scale
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
      drawTicks: false,
    });

    // EMA 20 line
    const ema20Series = chart.addLineSeries({
      color: CHART_COLORS.ema20,
      lineWidth: 1,
      lineStyle: 0, // solid
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    // EMA 50 line
    const ema50Series = chart.addLineSeries({
      color: CHART_COLORS.ema50,
      lineWidth: 1,
      lineStyle: 0,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    chartRef.current = chart;
    candlestickSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    ema20SeriesRef.current = ema20Series;
    ema50SeriesRef.current = ema50Series;

    // Handle resize
    const handleResize = () => {
      if (chartRef.current && el) {
        chartRef.current.applyOptions({
          width: el.clientWidth,
        });
      }
    };
    window.addEventListener('resize', handleResize);

    // Store cleanup for later
    chartCleanupRef.current = () => {
      window.removeEventListener('resize', handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      candlestickSeriesRef.current = null;
      volumeSeriesRef.current = null;
      ema20SeriesRef.current = null;
      ema50SeriesRef.current = null;
    };
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (chartCleanupRef.current) {
        chartCleanupRef.current();
      }
    };
  }, []);

  // Update chart data when candles, analysis, or price change
  useEffect(() => {
    if (Platform.OS !== 'web' || !chartRef.current || !candlestickSeriesRef.current) return;

    const candleSeries = candlestickSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const ema20Series = ema20SeriesRef.current;
    const ema50Series = ema50SeriesRef.current;
    const chart = chartRef.current;

    if (candles.length === 0) return;

    // Sort candles by time and remove duplicates
    const sorted = [...candles]
      .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime());

    const seen = new Set<number>();
    const uniqueCandles = sorted.filter(c => {
      const t = parseCandleTime(c.time);
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });

    // Candlestick data
    const candleData = uniqueCandles.map(c => ({
      time: parseCandleTime(c.time) as any,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    // Volume data
    const volumeData = uniqueCandles.map(c => ({
      time: parseCandleTime(c.time) as any,
      value: c.volume,
      color: c.close >= c.open ? CHART_COLORS.volumeUp : CHART_COLORS.volumeDown,
    }));

    candleSeries.setData(candleData);
    volumeSeries.setData(volumeData);

    // Calculate and set EMAs from candle close prices
    const closes = uniqueCandles.map(c => c.close);
    const ema20Values = calculateEMA(closes, 20);
    const ema50Values = calculateEMA(closes, 50);

    const ema20Data = uniqueCandles.map((c, i) => ({
      time: parseCandleTime(c.time) as any,
      value: ema20Values[i],
    })).filter((_, i) => i >= 19); // EMA needs warmup

    const ema50Data = uniqueCandles.map((c, i) => ({
      time: parseCandleTime(c.time) as any,
      value: ema50Values[i],
    })).filter((_, i) => i >= 49);

    ema20Series.setData(ema20Data);
    ema50Series.setData(ema50Data);

    // Remove old price lines
    for (const line of priceLinesRef.current) {
      try {
        candleSeries.removePriceLine(line);
      } catch (_) {}
    }
    priceLinesRef.current = [];

    // Support lines
    if (analysisSummary?.key_levels?.support) {
      for (const level of analysisSummary.key_levels.support) {
        const line = candleSeries.createPriceLine({
          price: level,
          color: CHART_COLORS.support,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'S',
        });
        priceLinesRef.current.push(line);
      }
    }

    // Resistance lines
    if (analysisSummary?.key_levels?.resistance) {
      for (const level of analysisSummary.key_levels.resistance) {
        const line = candleSeries.createPriceLine({
          price: level,
          color: CHART_COLORS.resistance,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: 'R',
        });
        priceLinesRef.current.push(line);
      }
    }

    // Pivot Points
    if (analysisSummary?.pivot_points) {
      const pivots = analysisSummary.pivot_points;
      const pivotEntries: Array<{ key: string; value: number }> = [];
      if (pivots.P) pivotEntries.push({ key: 'PP', value: pivots.P });
      if (pivots.S1) pivotEntries.push({ key: 'S1', value: pivots.S1 });
      if (pivots.S2) pivotEntries.push({ key: 'S2', value: pivots.S2 });
      if (pivots.S3) pivotEntries.push({ key: 'S3', value: pivots.S3 });
      if (pivots.R1) pivotEntries.push({ key: 'R1', value: pivots.R1 });
      if (pivots.R2) pivotEntries.push({ key: 'R2', value: pivots.R2 });
      if (pivots.R3) pivotEntries.push({ key: 'R3', value: pivots.R3 });

      for (const entry of pivotEntries) {
        const line = candleSeries.createPriceLine({
          price: entry.value,
          color: CHART_COLORS.pivot,
          lineWidth: 1,
          lineStyle: LineStyle.SparseDotted,
          axisLabelVisible: true,
          title: entry.key,
        });
        priceLinesRef.current.push(line);
      }
    }

    // Current price line
    if (price) {
      const line = candleSeries.createPriceLine({
        price: price.bid,
        color: CHART_COLORS.currentPrice,
        lineWidth: 2,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: '',
      });
      priceLinesRef.current.push(line);
    }

    // Scroll to latest
    chart.timeScale().scrollToRealTime();
  }, [candles, analysisSummary, price]);

  // ── Native Chart Calculations (fallback) ─────────────────────────────────

  const chartWidth = SCREEN_WIDTH - theme.spacing.md * 2 - PRICE_LABEL_WIDTH;
  const chartHeight = SCREEN_HEIGHT * 0.48;
  const NATIVE_CANDLE_COUNT = 80;

  const visibleCandles = useMemo(() => {
    return candles.slice(-NATIVE_CANDLE_COUNT);
  }, [candles]);

  const { priceMin, priceMax, priceRange } = useMemo(() => {
    if (visibleCandles.length === 0) return { priceMin: 0, priceMax: 1, priceRange: 1 };
    let min = Infinity;
    let max = -Infinity;
    for (const c of visibleCandles) {
      if (c.low < min) min = c.low;
      if (c.high > max) max = c.high;
    }
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
    return { priceMin: min - padding, priceMax: max + padding, priceRange: range + padding * 2 };
  }, [visibleCandles, analysisSummary]);

  const priceToY = useCallback(
    (p: number) => {
      if (priceRange === 0) return chartHeight / 2;
      return CHART_PADDING_TOP + ((priceMax - p) / priceRange) * (chartHeight - CHART_PADDING_TOP - CHART_PADDING_BOTTOM);
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

  const gridLines = useMemo(() => {
    if (priceRange === 0) return [];
    const lines: number[] = [];
    const step = priceRange / 5;
    for (let i = 0; i <= 5; i++) lines.push(priceMin + step * i);
    return lines;
  }, [priceMin, priceRange]);

  // ── Render: Instrument Picker ────────────────────────────────────────────

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
        <Text style={styles.pickerChevron}>{pickerOpen ? '\u25BE' : '\u25B8'}</Text>
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

  // ── Render: Timeframe Buttons ────────────────────────────────────────────

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

  // ── Render: Price Overlay ────────────────────────────────────────────────

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

  // ── Render: TradingView Chart (Web) ──────────────────────────────────────

  const renderWebChart = () => {
    const chartHeightPx = Math.min(SCREEN_HEIGHT * 0.55, 500);
    return (
      <View style={styles.tvChartWrapper}>
        <div
          ref={initChartRef}
          style={{
            width: '100%',
            height: chartHeightPx,
            borderRadius: 8,
            overflow: 'hidden',
            border: `1px solid ${theme.colors.border}`,
          }}
        />
        {/* EMA Legend */}
        <View style={styles.emaLegend}>
          <View style={styles.emaLegendItem}>
            <View style={[styles.emaLegendDot, { backgroundColor: CHART_COLORS.ema20 }]} />
            <Text style={styles.emaLegendText}>EMA 20</Text>
          </View>
          <View style={styles.emaLegendItem}>
            <View style={[styles.emaLegendDot, { backgroundColor: CHART_COLORS.ema50 }]} />
            <Text style={styles.emaLegendText}>EMA 50</Text>
          </View>
          {analysisSummary?.pivot_points?.P && (
            <View style={styles.emaLegendItem}>
              <View style={[styles.emaLegendDot, { backgroundColor: CHART_COLORS.pivot }]} />
              <Text style={styles.emaLegendText}>PIVOTS</Text>
            </View>
          )}
        </View>
      </View>
    );
  };

  // ── Render: Native Chart (React Native fallback) ─────────────────────────

  const renderNativeChart = () => {
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

        {/* Price labels */}
        <View style={styles.priceLabelsColumn}>
          {gridLines.map((p, i) => {
            const y = priceToY(p);
            return (
              <Text key={`label-${i}`} style={[styles.priceLabel, { top: y - 6 }]}>
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

        {/* Pivot Points (native) */}
        {analysisSummary?.pivot_points && Object.entries(analysisSummary.pivot_points).map(([key, val]) => {
          if (!val || typeof val !== 'number') return null;
          const y = priceToY(val);
          if (y < 0 || y > chartHeight) return null;
          return (
            <View key={`piv-${key}`} style={[styles.keyLevel, styles.pivotLevel, { top: y }]}>
              <Text style={styles.pivotLevelText}>{key} {formatPrice(val, selectedInstrument)}</Text>
            </View>
          );
        })}

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
          <View style={[styles.currentPriceLine, { top: priceToY(price.bid) }]}>
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

  // ── Render: Bottom Info Bar ──────────────────────────────────────────────

  const renderBottomBar = () => {
    if (!analysisSummary) return null;
    const stratColorMap: Record<string, string> = {
      BLUE: STRATEGY_COLORS.BLUE,
      RED: STRATEGY_COLORS.RED,
      PINK: STRATEGY_COLORS.PINK,
      WHITE: STRATEGY_COLORS.WHITE,
      BLACK: STRATEGY_COLORS.BLACK,
      GREEN: STRATEGY_COLORS.GREEN,
    };
    const stratColor = analysisSummary.strategy_color
      ? stratColorMap[analysisSummary.strategy_color.toUpperCase()] || theme.colors.textMuted
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

  const isWeb = Platform.OS === 'web';
  const hasCandles = candles.length > 0;

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

        {loading && !hasCandles ? (
          <View style={styles.centerMessage}>
            <ActivityIndicator size="large" color={theme.colors.neonPink} />
            <Text style={styles.loadingText}>Cargando velas...</Text>
          </View>
        ) : error && !hasCandles ? (
          <View style={styles.centerMessage}>
            <Text style={styles.errorIcon}>!</Text>
            <Text style={styles.errorText}>{error}</Text>
            <TouchableOpacity style={styles.retryButton} onPress={fetchChartData}>
              <Text style={styles.retryButtonText}>REINTENTAR</Text>
            </TouchableOpacity>
          </View>
        ) : hasCandles ? (
          <>
            {isWeb && createChart ? (
              renderWebChart()
            ) : (
              <View style={[styles.chartContainer, { height: chartHeight + 4 }]}>
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  contentContainerStyle={{
                    width: Math.max(chartWidth, visibleCandles.length * candleWidth + PRICE_LABEL_WIDTH),
                    height: chartHeight,
                  }}
                >
                  {renderNativeChart()}
                </ScrollView>
              </View>
            )}
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

  // ── TradingView Chart Wrapper (web) ─────────────────
  tvChartWrapper: {
    marginBottom: theme.spacing.sm,
  },

  // ── Native Chart ────────────────────────────────────
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
    borderColor: 'rgba(0, 255, 136, 0.5)',
  },
  resistanceLevel: {
    borderTopWidth: 1,
    borderStyle: 'dashed' as any,
    borderColor: 'rgba(255, 46, 99, 0.5)',
  },
  pivotLevel: {
    borderTopWidth: 1,
    borderStyle: 'dashed' as any,
    borderColor: 'rgba(255, 184, 0, 0.5)',
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
  pivotLevelText: {
    fontFamily: theme.fonts.mono,
    fontSize: 7,
    color: '#ffb800',
    backgroundColor: theme.colors.backgroundDark,
    paddingHorizontal: 2,
    position: 'absolute',
    left: 2,
    top: -8,
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
    width: 12,
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
