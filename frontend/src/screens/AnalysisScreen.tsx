/**
 * NeonTrade AI - Analysis Screen
 * Detailed analysis for a selected instrument with strategy explanations in Spanish.
 * CP2077 HUD redesign with shared sub-navigation for TRADE tab views.
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
import { theme } from '../theme/apple-glass';
const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);
import {
  HUDCard,
  HUDHeader,
  HUDSectionTitle,
  HUDBadge,
  HUDProgressBar,
  HUDDivider,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
import { API_URL, authFetch, STRATEGY_COLORS, getScoreColor, getTrendColor, getTrendIcon } from '../services/api';

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

  // Fetch analysis for the selected instrument
  const fetchAnalysis = async () => {
    if (!selectedInstrument) return;
    setLoading(true);
    setError(null);
    try {
      const res = await authFetch(`${API_URL}/api/v1/analysis/${selectedInstrument}`);
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
        authFetch(`${API_URL}/api/v1/watchlist`),
        selectedInstrument ? authFetch(`${API_URL}/api/v1/analysis/${selectedInstrument}`) : Promise.resolve(null),
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
    const color = getScoreColor(score);

    return (
      <HUDCard accentColor={color}>
        <HUDSectionTitle title="SCORE DE ANALISIS" color={theme.colors.cp2077Yellow} />
        <View style={styles.gaugeContainer}>
          <Text style={[styles.gaugeScore, { color }]}>{safe(score, 0)}</Text>
          <Text style={styles.gaugeMax}>/100</Text>
        </View>
        <HUDProgressBar
          label=""
          value={score}
          color={color}
          showValue={false}
        />
        <View style={styles.gaugeLabels}>
          <Text style={styles.gaugeLabelText}>0</Text>
          <Text style={styles.gaugeLabelText}>25</Text>
          <Text style={styles.gaugeLabelText}>50</Text>
          <Text style={styles.gaugeLabelText}>75</Text>
          <Text style={styles.gaugeLabelText}>100</Text>
        </View>
      </HUDCard>
    );
  };

  // ── Trend Overview ────────────────────────────────────────────────────────

  const renderTrendOverview = () => {
    if (!analysis) return null;
    const { htf_trend, ltf_trend, convergence } = analysis;

    return (
      <HUDCard>
        <HUDSectionTitle title="TENDENCIA" />
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
              {convergence ? '\u2713' : '\u2717'}
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
      </HUDCard>
    );
  };

  // ── Timeframe Cards ───────────────────────────────────────────────────────

  const renderTimeframeCards = () => {
    const timeframes = analysis?.explanation?.timeframe_analysis;
    if (!timeframes || timeframes.length === 0) return null;

    return (
      <HUDCard>
        <HUDSectionTitle title="ANALISIS POR TEMPORALIDAD" />
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
                  <View style={styles.tfBadgeContainer}>
                    <Text style={styles.tfBadge}>{tf.timeframe}</Text>
                  </View>
                  <View style={styles.tfTrendRow}>
                    <Text style={[styles.tfTrendIcon, { color: getTrendColor(tf.trend) }]}>
                      {getTrendIcon(tf.trend)}
                    </Text>
                    <Text style={[styles.tfTrend, { color: getTrendColor(tf.trend) }]}>
                      {tf.trend?.toUpperCase()}
                    </Text>
                  </View>
                </View>
                <Text style={styles.tfChevron}>{isExpanded ? '\u25BE' : '\u25B8'}</Text>
              </TouchableOpacity>

              {isExpanded && (
                <View style={styles.tfBody}>
                  {/* Observations */}
                  {tf.observations && tf.observations.length > 0 && (
                    <View style={styles.tfSection}>
                      <Text style={styles.tfSectionTitle}>OBSERVACIONES</Text>
                      {tf.observations.map((obs, i) => (
                        <Text key={i} style={styles.tfBullet}>
                          {'  '}{'\u00B7'} {obs}
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
                          {tf.key_levels.support?.map((l: any) => safe(l, 5)).join(', ')}
                        </Text>
                      )}
                      {tf.key_levels?.resistance?.length > 0 && (
                        <Text style={styles.tfLevels}>
                          <Text style={{ color: theme.colors.neonRed }}>RESISTENCIA: </Text>
                          {tf.key_levels.resistance?.map((l: any) => safe(l, 5)).join(', ')}
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
      </HUDCard>
    );
  };

  // ── Strategy Detection ────────────────────────────────────────────────────

  const renderStrategy = () => {
    if (!analysis?.strategy) return null;
    const { strategy, explanation } = analysis;
    const stratColor = STRATEGY_COLORS[strategy.color?.toUpperCase()] || theme.colors.textMuted;
    const steps = strategy.steps || explanation?.strategy_steps || [];

    return (
      <HUDCard accentColor={stratColor} borderColor={stratColor}>
        <View style={styles.strategyHeader}>
          <View style={[styles.strategyColorDot, { backgroundColor: stratColor }]} />
          <HUDSectionTitle title="ESTRATEGIA DETECTADA" color={stratColor} />
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
                  {step.met ? '\u2713' : '\u2717'}
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
            <HUDDivider />
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
      </HUDCard>
    );
  };

  // ── Recommendation ────────────────────────────────────────────────────────

  const renderRecommendation = () => {
    if (!analysis?.explanation?.recommendation) return null;
    const confidenceColor = getConfidenceColor(analysis.confidence);

    return (
      <HUDCard accentColor={confidenceColor} borderColor={theme.colors.cp2077Yellow}>
        <View style={styles.recommendationHeader}>
          <HUDSectionTitle title="RECOMENDACION" />
          <HUDBadge label={analysis.confidence || '---'} color={confidenceColor} />
        </View>
        {analysis.htf_trend && (
          <View style={styles.directionBadgeRow}>
            <HUDBadge
              label={analysis.htf_trend === 'bullish' ? '\u25B2 COMPRA' : analysis.htf_trend === 'bearish' ? '\u25BC VENTA' : '\u25CF NEUTRAL'}
              color={getTrendColor(analysis.htf_trend)}
              small
            />
          </View>
        )}
        <Text style={styles.recommendationText}>
          {analysis.explanation.recommendation}
        </Text>
      </HUDCard>
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
        <View style={styles.pickerAccent} />
        <Text style={styles.pickerButtonText}>
          {selectedInstrument ? selectedInstrument.replace('_', '/') : 'Seleccionar par...'}
        </Text>
        <Text style={styles.pickerChevron}>{pickerOpen ? '\u25BE' : '\u25B8'}</Text>
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
                  {safe(item.score, 0)}
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
      {/* HUD Header */}
      <HUDHeader title="MARKET ANALYSIS // SCAN" subtitle="TRADE INTELLIGENCE SYSTEM" />

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
          <LoadingState message={`Analizando ${selectedInstrument.replace('_', '/')}...`} />
        ) : error ? (
          <View style={styles.centerMessage}>
            {error.includes('esperando') || error.includes('disponible') ? (
              <>
                <ActivityIndicator size="large" color={theme.colors.neonCyan} />
                <Text style={[styles.waitingText, { marginTop: 16 }]}>{error}</Text>
                <Text style={styles.waitingSubtext}>
                  El motor esta analizando los pares...
                </Text>
              </>
            ) : (
              <ErrorState message={error} onRetry={fetchAnalysis} />
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
    backgroundColor: '#f2f2f7',
  },
  scrollContent: {
    flex: 1,
  },
  scrollContentInner: {
    padding: 16,
  },

  // ── Picker ──────────────────────────────────────────
  pickerContainer: {
    paddingHorizontal: 16,
    paddingBottom: 8,
    zIndex: 100,
  },
  pickerButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: 14,
    paddingHorizontal: 16,
    paddingVertical: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    elevation: 4,
  },
  pickerAccent: {
    width: 3,
    height: 16,
    backgroundColor: '#007AFF',
    marginRight: 8,
    borderRadius: 2,
  },
  pickerButtonText: {
    flex: 1,
    fontSize: 16,
    fontWeight: '600',
    color: '#1d1d1f',
  },
  pickerChevron: {
    fontSize: 14,
    color: '#007AFF',
  },
  pickerDropdown: {
    backgroundColor: '#ffffff',
    borderRadius: 14,
    maxHeight: 240,
    marginTop: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 16,
    elevation: 6,
  },
  pickerScrollView: {
    maxHeight: 240,
  },
  pickerOption: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
  },
  pickerOptionActive: {
    backgroundColor: 'rgba(0,122,255,0.06)',
  },
  pickerOptionText: {
    fontSize: 15,
    color: '#86868b',
  },
  pickerOptionTextActive: {
    color: '#007AFF',
    fontWeight: '600',
  },
  pickerOptionScore: {
    fontSize: 15,
    fontWeight: '700',
  },

  // ── Score Gauge ─────────────────────────────────────
  gaugeContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'center',
    marginBottom: 8,
  },
  gaugeScore: {
    fontSize: 52,
    fontWeight: '700',
  },
  gaugeMax: {
    fontSize: 18,
    color: '#aeaeb2',
    marginLeft: 4,
  },
  gaugeLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 2,
  },
  gaugeLabelText: {
    fontSize: 9,
    color: '#aeaeb2',
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
    fontSize: 11,
    fontWeight: '500',
    color: '#aeaeb2',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  trendArrow: {
    fontSize: 24,
    marginBottom: 2,
  },
  trendValue: {
    fontSize: 12,
    fontWeight: '600',
  },
  trendDivider: {
    width: 1,
    height: 50,
    backgroundColor: 'rgba(0,0,0,0.04)',
  },

  // ── Timeframe Cards ─────────────────────────────────
  tfCard: {
    backgroundColor: '#f9f9f9',
    borderRadius: 14,
    marginBottom: 8,
    overflow: 'hidden',
  },
  tfHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  tfHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  tfBadgeContainer: {
    backgroundColor: 'rgba(0,122,255,0.08)',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  tfBadge: {
    fontSize: 13,
    color: '#007AFF',
    fontWeight: '600',
  },
  tfTrendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  tfTrendIcon: {
    fontSize: 13,
  },
  tfTrend: {
    fontSize: 12,
    fontWeight: '500',
  },
  tfChevron: {
    fontSize: 16,
    color: '#aeaeb2',
  },
  tfBody: {
    paddingHorizontal: 12,
    paddingBottom: 10,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.04)',
  },
  tfSection: {
    marginTop: 8,
  },
  tfSectionTitle: {
    fontSize: 11,
    fontWeight: '600',
    color: '#86868b',
    letterSpacing: 0.3,
    marginBottom: 4,
  },
  tfBullet: {
    fontSize: 13,
    color: '#86868b',
    lineHeight: 20,
  },
  tfLevels: {
    fontSize: 13,
    color: '#86868b',
    lineHeight: 20,
  },
  patternsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  patternTag: {
    backgroundColor: 'rgba(0,122,255,0.08)',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  patternText: {
    fontSize: 11,
    color: '#007AFF',
    fontWeight: '500',
  },
  tfConclusion: {
    fontSize: 13,
    color: '#1d1d1f',
    lineHeight: 20,
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
    marginBottom: 8,
  },
  strategyName: {
    fontSize: 20,
    fontWeight: '700',
    letterSpacing: -0.3,
    marginBottom: 16,
  },
  stepsContainer: {
    marginBottom: 16,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 6,
    gap: 8,
  },
  stepIcon: {
    fontSize: 14,
    fontWeight: '600',
    width: 18,
    textAlign: 'center',
  },
  stepText: {
    fontSize: 13,
    color: '#86868b',
    flex: 1,
    lineHeight: 20,
  },
  entrySection: {
    paddingTop: 4,
    marginBottom: 8,
  },
  entryRow: {
    marginBottom: 6,
  },
  entryLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#007AFF',
    letterSpacing: 0.3,
    marginBottom: 2,
  },
  entryValue: {
    fontSize: 13,
    color: '#86868b',
    lineHeight: 18,
  },
  riskBox: {
    backgroundColor: 'rgba(255,149,0,0.06)',
    borderRadius: 14,
    padding: 12,
    marginTop: 8,
  },
  riskLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: '#FF9500',
    letterSpacing: 0.3,
    marginBottom: 4,
  },
  riskText: {
    fontSize: 13,
    color: '#86868b',
    lineHeight: 18,
  },

  // ── Recommendation ──────────────────────────────────
  recommendationHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  directionBadgeRow: {
    marginBottom: 8,
  },
  recommendationText: {
    fontSize: 14,
    color: '#1d1d1f',
    lineHeight: 22,
  },

  // ── States ──────────────────────────────────────────
  centerMessage: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 96,
  },
  waitingText: {
    fontSize: 14,
    color: '#007AFF',
    textAlign: 'center',
  },
  waitingSubtext: {
    fontSize: 12,
    color: '#aeaeb2',
    marginTop: 8,
  },
  emptyText: {
    fontSize: 14,
    color: '#aeaeb2',
    textAlign: 'center',
  },
});
