/**
 * NeonTrade AI - Analysis Screen
 * Detailed analysis for a selected instrument with strategy explanations in Spanish.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Dimensions,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, STRATEGY_COLORS, getScoreColor, getTrendColor, getTrendIcon } from '../services/api';

// ─── Types ──────────────────────────────────────────────────────────────────

interface WatchlistItem {
  instrument: string;
  score: number;
  trend: string;
}

interface TimeframeAnalysis {
  timeframe: string;
  trend: string;
  observations: string[];
  key_levels: { support: number[]; resistance: number[] };
  patterns: string[];
  conclusion: string;
}

interface StrategyStep {
  description: string;
  met: boolean;
}

interface StrategyInfo {
  name: string;
  color: string;
  steps: StrategyStep[];
  entry_explanation: string;
  sl_explanation: string;
  tp_explanation: string;
  risk_assessment: string;
}

interface AnalysisExplanation {
  timeframe_analysis: TimeframeAnalysis[];
  strategy_steps: StrategyStep[];
  recommendation: string;
}

interface AnalysisData {
  instrument: string;
  score: number;
  confidence: string; // 'ALTA' | 'MEDIA' | 'BAJA'
  htf_trend: string;
  ltf_trend: string;
  convergence: boolean;
  strategy: StrategyInfo | null;
  explanation: AnalysisExplanation;
}

// ─── Constants ──────────────────────────────────────────────────────────────

const SCREEN_WIDTH = Dimensions.get('window').width;

// ─── Helpers ────────────────────────────────────────────────────────────────

const getConfidenceColor = (confidence: string) => {
  switch (confidence?.toUpperCase()) {
    case 'ALTA': return theme.colors.neonGreen;
    case 'MEDIA': return theme.colors.neonYellow;
    case 'BAJA': return theme.colors.neonRed;
    default: return theme.colors.textMuted;
  }
};

// ─── Component ──────────────────────────────────────────────────────────────

export default function AnalysisScreen() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selectedInstrument, setSelectedInstrument] = useState<string>('');
  const [analysis, setAnalysis] = useState<AnalysisData | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [expandedTimeframes, setExpandedTimeframes] = useState<Record<string, boolean>>({});

  // Fetch watchlist for the instrument picker (runs once)
  useEffect(() => {
    const loadWatchlist = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/watchlist`);
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

  // Fetch analysis for the selected instrument
  const fetchAnalysis = async () => {
    if (!selectedInstrument) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/analysis/${selectedInstrument}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      // If backend returned a "no data yet" placeholder, show waiting message
      if (data.message && data.score === 0) {
        setAnalysis(null);
        setError(data.message);
      } else {
        setAnalysis(data);
      }
    } catch (err: any) {
      console.error('Failed to fetch analysis:', err);
      setError(err.message || 'Error al cargar el analisis');
      setAnalysis(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedInstrument) return;
    fetchAnalysis();
    const interval = setInterval(fetchAnalysis, 15000);
    return () => clearInterval(interval);
  }, [selectedInstrument]);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      const [wlRes, anRes] = await Promise.all([
        fetch(`${API_URL}/api/v1/watchlist`),
        selectedInstrument ? fetch(`${API_URL}/api/v1/analysis/${selectedInstrument}`) : Promise.resolve(null),
      ]);
      if (wlRes.ok) {
        const wlData = await wlRes.json();
        setWatchlist(Array.isArray(wlData) ? wlData : []);
      }
      if (anRes && anRes.ok) {
        setAnalysis(await anRes.json());
      }
    } catch (err) {
      console.error('Refresh failed:', err);
    }
    setRefreshing(false);
  };

  const toggleTimeframe = (tf: string) => {
    setExpandedTimeframes((prev) => ({ ...prev, [tf]: !prev[tf] }));
  };

  // ── Score Gauge ───────────────────────────────────────────────────────────

  const renderScoreGauge = (score: number) => {
    const gaugeWidth = SCREEN_WIDTH - theme.spacing.md * 4 - 2; // account for card padding & border
    const fillWidth = (score / 100) * gaugeWidth;
    const color = getScoreColor(score);

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>SCORE DE ANALISIS</Text>
        <View style={styles.gaugeContainer}>
          <Text style={[styles.gaugeScore, { color }]}>{score.toFixed(0)}</Text>
          <Text style={styles.gaugeMax}>/100</Text>
        </View>
        <View style={styles.gaugeTrack}>
          <View
            style={[
              styles.gaugeFill,
              { width: fillWidth > 0 ? fillWidth : 0, backgroundColor: color },
            ]}
          />
        </View>
        <View style={styles.gaugeLabels}>
          <Text style={styles.gaugeLabelText}>0</Text>
          <Text style={styles.gaugeLabelText}>25</Text>
          <Text style={styles.gaugeLabelText}>50</Text>
          <Text style={styles.gaugeLabelText}>75</Text>
          <Text style={styles.gaugeLabelText}>100</Text>
        </View>
      </View>
    );
  };

  // ── Trend Overview ────────────────────────────────────────────────────────

  const renderTrendOverview = () => {
    if (!analysis) return null;
    const { htf_trend, ltf_trend, convergence } = analysis;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>TENDENCIA</Text>
        <View style={styles.trendRow}>
          <View style={styles.trendItem}>
            <Text style={styles.trendLabel}>HTF</Text>
            <Text style={[styles.trendArrow, { color: getTrendColor(htf_trend) }]}>
              {getTrendIcon(htf_trend)}
            </Text>
            <Text style={[styles.trendValue, { color: getTrendColor(htf_trend) }]}>
              {htf_trend?.toUpperCase() || '---'}
            </Text>
          </View>
          <View style={styles.trendDivider} />
          <View style={styles.trendItem}>
            <Text style={styles.trendLabel}>LTF</Text>
            <Text style={[styles.trendArrow, { color: getTrendColor(ltf_trend) }]}>
              {getTrendIcon(ltf_trend)}
            </Text>
            <Text style={[styles.trendValue, { color: getTrendColor(ltf_trend) }]}>
              {ltf_trend?.toUpperCase() || '---'}
            </Text>
          </View>
          <View style={styles.trendDivider} />
          <View style={styles.trendItem}>
            <Text style={styles.trendLabel}>CONVERGENCIA</Text>
            <Text
              style={[
                styles.trendArrow,
                { color: convergence ? theme.colors.neonGreen : theme.colors.neonRed },
              ]}
            >
              {convergence ? '✓' : '✗'}
            </Text>
            <Text
              style={[
                styles.trendValue,
                { color: convergence ? theme.colors.neonGreen : theme.colors.neonRed },
              ]}
            >
              {convergence ? 'SI' : 'NO'}
            </Text>
          </View>
        </View>
      </View>
    );
  };

  // ── Timeframe Cards ───────────────────────────────────────────────────────

  const renderTimeframeCards = () => {
    const timeframes = analysis?.explanation?.timeframe_analysis;
    if (!timeframes || timeframes.length === 0) return null;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ANALISIS POR TEMPORALIDAD</Text>
        {timeframes.map((tf, idx) => {
          const isExpanded = expandedTimeframes[tf.timeframe] ?? false;
          return (
            <View key={idx} style={styles.tfCard}>
              <TouchableOpacity
                style={styles.tfHeader}
                onPress={() => toggleTimeframe(tf.timeframe)}
                activeOpacity={0.7}
              >
                <View style={styles.tfHeaderLeft}>
                  <Text style={styles.tfBadge}>{tf.timeframe}</Text>
                  <Text style={[styles.tfTrend, { color: getTrendColor(tf.trend) }]}>
                    {getTrendIcon(tf.trend)} {tf.trend?.toUpperCase()}
                  </Text>
                </View>
                <Text style={styles.tfChevron}>{isExpanded ? '▾' : '▸'}</Text>
              </TouchableOpacity>

              {isExpanded && (
                <View style={styles.tfBody}>
                  {/* Observations */}
                  {tf.observations && tf.observations.length > 0 && (
                    <View style={styles.tfSection}>
                      <Text style={styles.tfSectionTitle}>OBSERVACIONES</Text>
                      {tf.observations.map((obs, i) => (
                        <Text key={i} style={styles.tfBullet}>
                          {'  '}· {obs}
                        </Text>
                      ))}
                    </View>
                  )}

                  {/* Key Levels */}
                  {tf.key_levels && (
                    <View style={styles.tfSection}>
                      <Text style={styles.tfSectionTitle}>NIVELES CLAVE</Text>
                      {tf.key_levels?.support?.length > 0 && (
                        <Text style={styles.tfLevels}>
                          <Text style={{ color: theme.colors.neonGreen }}>SOPORTE: </Text>
                          {tf.key_levels.support?.map((l) => l.toFixed(5)).join(', ')}
                        </Text>
                      )}
                      {tf.key_levels?.resistance?.length > 0 && (
                        <Text style={styles.tfLevels}>
                          <Text style={{ color: theme.colors.neonRed }}>RESISTENCIA: </Text>
                          {tf.key_levels.resistance?.map((l) => l.toFixed(5)).join(', ')}
                        </Text>
                      )}
                    </View>
                  )}

                  {/* Patterns */}
                  {tf.patterns && tf.patterns.length > 0 && (
                    <View style={styles.tfSection}>
                      <Text style={styles.tfSectionTitle}>PATRONES</Text>
                      <View style={styles.patternsRow}>
                        {tf.patterns.map((p, i) => (
                          <View key={i} style={styles.patternTag}>
                            <Text style={styles.patternText}>{p}</Text>
                          </View>
                        ))}
                      </View>
                    </View>
                  )}

                  {/* Conclusion */}
                  {tf.conclusion && (
                    <View style={styles.tfSection}>
                      <Text style={styles.tfSectionTitle}>CONCLUSION</Text>
                      <Text style={styles.tfConclusion}>{tf.conclusion}</Text>
                    </View>
                  )}
                </View>
              )}
            </View>
          );
        })}
      </View>
    );
  };

  // ── Strategy Detection ────────────────────────────────────────────────────

  const renderStrategy = () => {
    if (!analysis?.strategy) return null;
    const { strategy, explanation } = analysis;
    const stratColor = STRATEGY_COLORS[strategy.color?.toUpperCase()] || theme.colors.textMuted;
    const steps = strategy.steps || explanation?.strategy_steps || [];

    return (
      <View style={[styles.card, { borderColor: stratColor, borderWidth: 1 }]}>
        <View style={styles.strategyHeader}>
          <View style={[styles.strategyColorDot, { backgroundColor: stratColor }]} />
          <Text style={styles.cardTitle}>ESTRATEGIA DETECTADA</Text>
        </View>

        <Text style={[styles.strategyName, { color: stratColor }]}>
          {strategy.name}
        </Text>

        {/* Step-by-step checklist */}
        {steps.length > 0 && (
          <View style={styles.stepsContainer}>
            <Text style={styles.tfSectionTitle}>CONDICIONES</Text>
            {steps.map((step, idx) => (
              <View key={idx} style={styles.stepRow}>
                <Text
                  style={[
                    styles.stepIcon,
                    { color: step.met ? theme.colors.neonGreen : theme.colors.neonRed },
                  ]}
                >
                  {step.met ? '✓' : '✗'}
                </Text>
                <Text
                  style={[
                    styles.stepText,
                    !step.met && { color: theme.colors.textMuted },
                  ]}
                >
                  {step.description}
                </Text>
              </View>
            ))}
          </View>
        )}

        {/* Entry / SL / TP */}
        {(strategy.entry_explanation || strategy.sl_explanation || strategy.tp_explanation) && (
          <View style={styles.entrySection}>
            {strategy.entry_explanation && (
              <View style={styles.entryRow}>
                <Text style={styles.entryLabel}>ENTRADA</Text>
                <Text style={styles.entryValue}>{strategy.entry_explanation}</Text>
              </View>
            )}
            {strategy.sl_explanation && (
              <View style={styles.entryRow}>
                <Text style={[styles.entryLabel, { color: theme.colors.neonRed }]}>SL</Text>
                <Text style={styles.entryValue}>{strategy.sl_explanation}</Text>
              </View>
            )}
            {strategy.tp_explanation && (
              <View style={styles.entryRow}>
                <Text style={[styles.entryLabel, { color: theme.colors.neonGreen }]}>TP</Text>
                <Text style={styles.entryValue}>{strategy.tp_explanation}</Text>
              </View>
            )}
          </View>
        )}

        {/* Risk Assessment */}
        {strategy.risk_assessment && (
          <View style={styles.riskBox}>
            <Text style={styles.riskLabel}>RIESGO</Text>
            <Text style={styles.riskText}>{strategy.risk_assessment}</Text>
          </View>
        )}
      </View>
    );
  };

  // ── Recommendation ────────────────────────────────────────────────────────

  const renderRecommendation = () => {
    if (!analysis?.explanation?.recommendation) return null;
    const confidenceColor = getConfidenceColor(analysis.confidence);

    return (
      <View style={[styles.card, styles.recommendationCard]}>
        <View style={styles.recommendationHeader}>
          <Text style={styles.cardTitle}>RECOMENDACION</Text>
          <View style={[styles.confidenceBadge, { borderColor: confidenceColor }]}>
            <Text style={[styles.confidenceText, { color: confidenceColor }]}>
              {analysis.confidence || '---'}
            </Text>
          </View>
        </View>
        <Text style={styles.recommendationText}>
          {analysis.explanation.recommendation}
        </Text>
      </View>
    );
  };

  // ── Instrument Picker ─────────────────────────────────────────────────────

  const renderPicker = () => (
    <View style={styles.pickerContainer}>
      <TouchableOpacity
        style={styles.pickerButton}
        onPress={() => setPickerOpen(!pickerOpen)}
        activeOpacity={0.7}
      >
        <Text style={styles.pickerButtonText}>
          {selectedInstrument ? selectedInstrument.replace('_', '/') : 'Seleccionar par...'}
        </Text>
        <Text style={styles.pickerChevron}>{pickerOpen ? '▾' : '▸'}</Text>
      </TouchableOpacity>

      {pickerOpen && (
        <View style={styles.pickerDropdown}>
          <ScrollView style={styles.pickerScrollView} nestedScrollEnabled>
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
                    item.instrument === selectedInstrument && styles.pickerOptionTextActive,
                  ]}
                >
                  {item.instrument.replace('_', '/')}
                </Text>
                <Text style={[styles.pickerOptionScore, { color: getScoreColor(item.score) }]}>
                  {item.score.toFixed(0)}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      )}
    </View>
  );

  // ── Main Render ───────────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>ANALISIS</Text>
        <Text style={styles.subtitle}>DETALLE DE INSTRUMENTO</Text>
      </View>

      {/* Instrument Picker */}
      {renderPicker()}

      <ScrollView
        style={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
        contentContainerStyle={styles.scrollContentInner}
      >
        {loading && !analysis ? (
          <View style={styles.centerMessage}>
            <ActivityIndicator size="large" color={theme.colors.neonPink} />
            <Text style={styles.loadingText}>Analizando {selectedInstrument.replace('_', '/')}...</Text>
          </View>
        ) : error ? (
          <View style={styles.centerMessage}>
            {error.includes('esperando') || error.includes('disponible') ? (
              <>
                <ActivityIndicator size="large" color={theme.colors.neonCyan} />
                <Text style={[styles.loadingText, { color: theme.colors.neonCyan, marginTop: 16 }]}>{error}</Text>
                <Text style={[styles.loadingText, { marginTop: 8, fontSize: 10 }]}>
                  El motor esta analizando los pares...
                </Text>
              </>
            ) : (
              <>
                <Text style={styles.errorIcon}>!</Text>
                <Text style={styles.errorText}>{error}</Text>
                <TouchableOpacity style={styles.retryButton} onPress={fetchAnalysis}>
                  <Text style={styles.retryButtonText}>REINTENTAR</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        ) : analysis ? (
          <>
            {renderScoreGauge(analysis.score)}
            {renderTrendOverview()}
            {renderTimeframeCards()}
            {renderStrategy()}
            {renderRecommendation()}
            <View style={{ height: theme.spacing.xxl }} />
          </>
        ) : (
          <View style={styles.centerMessage}>
            <Text style={styles.emptyText}>Selecciona un instrumento para ver el analisis</Text>
          </View>
        )}
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
    paddingBottom: theme.spacing.sm,
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
  subtitle: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 4,
    marginTop: 2,
  },
  scrollContent: {
    flex: 1,
  },
  scrollContentInner: {
    padding: theme.spacing.md,
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
    paddingVertical: theme.spacing.sm + 2,
  },
  pickerButtonText: {
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
    maxHeight: 240,
  },
  pickerScrollView: {
    maxHeight: 240,
  },
  pickerOption: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm + 2,
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
  pickerOptionTextActive: {
    color: theme.colors.neonPink,
  },
  pickerOptionScore: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    fontWeight: 'bold',
  },

  // ── Card ────────────────────────────────────────────
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.borderRadius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
  },
  cardTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonPink,
    letterSpacing: 3,
    marginBottom: theme.spacing.sm,
  },

  // ── Score Gauge ─────────────────────────────────────
  gaugeContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'center',
    marginBottom: theme.spacing.sm,
  },
  gaugeScore: {
    fontFamily: theme.fonts.mono,
    fontSize: 48,
    fontWeight: 'bold',
  },
  gaugeMax: {
    fontFamily: theme.fonts.mono,
    fontSize: 18,
    color: theme.colors.textMuted,
    marginLeft: 4,
  },
  gaugeTrack: {
    height: 8,
    backgroundColor: theme.colors.backgroundDark,
    borderRadius: theme.borderRadius.sm,
    overflow: 'hidden',
  },
  gaugeFill: {
    height: '100%',
    borderRadius: theme.borderRadius.sm,
  },
  gaugeLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  gaugeLabelText: {
    fontFamily: theme.fonts.mono,
    fontSize: 8,
    color: theme.colors.textMuted,
  },

  // ── Trend Overview ──────────────────────────────────
  trendRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  trendItem: {
    alignItems: 'center',
    flex: 1,
  },
  trendLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: 4,
  },
  trendArrow: {
    fontFamily: theme.fonts.mono,
    fontSize: 24,
    marginBottom: 2,
  },
  trendValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    letterSpacing: 1,
  },
  trendDivider: {
    width: 1,
    height: 50,
    backgroundColor: theme.colors.border,
  },

  // ── Timeframe Cards ─────────────────────────────────
  tfCard: {
    backgroundColor: theme.colors.backgroundDark,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    marginBottom: theme.spacing.sm,
    overflow: 'hidden',
  },
  tfHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: theme.spacing.sm + 2,
    paddingVertical: theme.spacing.sm,
  },
  tfHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  tfBadge: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.neonCyan,
    fontWeight: 'bold',
    letterSpacing: 1,
    borderWidth: 1,
    borderColor: theme.colors.neonCyan,
    borderRadius: 3,
    paddingHorizontal: 6,
    paddingVertical: 2,
    overflow: 'hidden',
  },
  tfTrend: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    letterSpacing: 1,
  },
  tfChevron: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.textMuted,
  },
  tfBody: {
    paddingHorizontal: theme.spacing.sm + 2,
    paddingBottom: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  tfSection: {
    marginTop: theme.spacing.sm,
  },
  tfSectionTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.neonPink,
    letterSpacing: 2,
    marginBottom: 4,
  },
  tfBullet: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 18,
  },
  tfLevels: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 18,
  },
  patternsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  patternTag: {
    backgroundColor: theme.colors.backgroundLight,
    borderRadius: 3,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderWidth: 1,
    borderColor: theme.colors.neonPinkDim,
  },
  patternText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.neonPink,
    letterSpacing: 1,
  },
  tfConclusion: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textWhite,
    lineHeight: 18,
    fontStyle: 'italic',
  },

  // ── Strategy ────────────────────────────────────────
  strategyHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  strategyColorDot: {
    width: 14,
    height: 14,
    borderRadius: 7,
    marginBottom: theme.spacing.sm,
  },
  strategyName: {
    fontFamily: theme.fonts.mono,
    fontSize: 18,
    fontWeight: 'bold',
    letterSpacing: 2,
    marginBottom: theme.spacing.md,
  },
  stepsContainer: {
    marginBottom: theme.spacing.md,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 6,
    gap: 8,
  },
  stepIcon: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    fontWeight: 'bold',
    width: 18,
    textAlign: 'center',
  },
  stepText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textSecondary,
    flex: 1,
    lineHeight: 18,
  },
  entrySection: {
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  entryRow: {
    marginBottom: 6,
  },
  entryLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.neonCyan,
    letterSpacing: 2,
    marginBottom: 2,
  },
  entryValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 16,
  },
  riskBox: {
    backgroundColor: theme.colors.backgroundDark,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.neonOrange,
    padding: theme.spacing.sm,
  },
  riskLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.neonOrange,
    letterSpacing: 2,
    marginBottom: 4,
  },
  riskText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 16,
  },

  // ── Recommendation ──────────────────────────────────
  recommendationCard: {
    borderColor: theme.colors.neonPink,
    borderWidth: 1,
  },
  recommendationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  confidenceBadge: {
    borderWidth: 1,
    borderRadius: theme.borderRadius.round,
    paddingHorizontal: theme.spacing.sm + 2,
    paddingVertical: 2,
    marginBottom: theme.spacing.sm,
  },
  confidenceText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    fontWeight: 'bold',
    letterSpacing: 2,
  },
  recommendationText: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.textWhite,
    lineHeight: 20,
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
