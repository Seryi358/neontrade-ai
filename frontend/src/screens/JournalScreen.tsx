/**
 * NeonTrade AI - Journal Screen
 * Comprehensive trade journal with stats, trade list, and emotional notes.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  TextInput,
  Linking,
  Alert,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, authFetch, api, STRATEGY_COLORS } from '../services/api';

// Types
interface JournalStats {
  total_trades: number;
  wins: number;
  losses: number;
  break_evens: number;
  win_rate: number;
  win_rate_excl_be: number;
  current_balance: number;
  initial_capital: number;
  peak_balance: number;
  current_drawdown_pct: number;
  max_drawdown_pct: number;
  max_drawdown_dollars: number;
  current_winning_streak: number;
  max_winning_streak: number;
  max_streak_pct: number;
  avg_win_pct: number;
  avg_loss_pct: number;
  profit_factor: number;
  accumulator: number;
  pnl_accumulated_pct: number;
  monthly_returns: Record<string, number>;
  dd_by_year: Record<string, number>;
}

interface JournalTrade {
  trade_number: number;
  trade_id: string;
  date: string;
  instrument: string;
  direction: string;
  strategy: string;
  pnl_dollars: number;
  pnl_pct: number;
  result: 'TP' | 'SL' | 'BE';
  balance_after: number;
  drawdown_pct: number;
  winning_streak: number;
  emotional_notes_pre: string;
  emotional_notes_during: string;
  emotional_notes_post: string;
  is_discretionary?: boolean;
  discretionary_notes?: string;
  _screenshots?: string[];
}

interface MonthlyReport {
  month: string;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
  by_strategy?: Record<string, { trades: number; pnl: number; win_rate: number }>;
  recommendations?: string[];
  best_strategy?: string;
  worst_strategy?: string;
}

const MONTH_LABELS: Record<string, string> = {
  '01': 'ENE', '02': 'FEB', '03': 'MAR', '04': 'ABR',
  '05': 'MAY', '06': 'JUN', '07': 'JUL', '08': 'AGO',
  '09': 'SEP', '10': 'OCT', '11': 'NOV', '12': 'DIC',
};

const getResultColor = (result: string): string => {
  switch (result) {
    case 'TP': return theme.colors.profit;
    case 'SL': return theme.colors.loss;
    case 'BE': return theme.colors.neonYellow;
    default: return theme.colors.textMuted;
  }
};

const formatMonthKey = (key: string): string => {
  // Expected format: "2026-01" or "01-2026" etc.
  const parts = key.split('-');
  if (parts.length === 2) {
    const [yearOrMonth, monthOrYear] = parts;
    if (yearOrMonth.length === 4) {
      // "2026-01" format
      return `${MONTH_LABELS[monthOrYear] || monthOrYear} ${yearOrMonth}`;
    }
    // "01-2026" format
    return `${MONTH_LABELS[yearOrMonth] || yearOrMonth} ${monthOrYear}`;
  }
  return key;
};

export default function JournalScreen() {
  const [stats, setStats] = useState<JournalStats | null>(null);
  const [trades, setTrades] = useState<JournalTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedTrade, setExpandedTrade] = useState<string | null>(null);
  const [editingNotes, setEditingNotes] = useState<Record<string, { pre: string; during: string; post: string }>>({});
  const [savingNotes, setSavingNotes] = useState<string | null>(null);
  const [monthlyReport, setMonthlyReport] = useState<MonthlyReport | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const now = new Date();
  const currentMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [statsRes, tradesRes] = await Promise.all([
        authFetch(`${API_URL}/api/v1/journal/stats`),
        authFetch(`${API_URL}/api/v1/journal/trades?limit=30`),
      ]);

      if (!statsRes.ok || !tradesRes.ok) {
        throw new Error('Error al cargar datos del journal');
      }

      const statsData: JournalStats = await statsRes.json();
      const tradesData: JournalTrade[] = await tradesRes.json();

      setStats(statsData);
      setTrades(tradesData);
    } catch (err) {
      console.error('Failed to fetch journal:', err);
      setError('No se pudo conectar al servidor');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  const toggleExpand = (tradeId: string, trade: JournalTrade) => {
    if (expandedTrade === tradeId) {
      setExpandedTrade(null);
    } else {
      setExpandedTrade(tradeId);
      if (!editingNotes[tradeId]) {
        setEditingNotes((prev) => ({
          ...prev,
          [tradeId]: {
            pre: trade.emotional_notes_pre || '',
            during: trade.emotional_notes_during || '',
            post: trade.emotional_notes_post || '',
          },
        }));
      }
    }
  };

  const saveEmotionalNotes = async (tradeId: string) => {
    const notes = editingNotes[tradeId];
    if (!notes) return;

    try {
      setSavingNotes(tradeId);
      const res = await authFetch(`${API_URL}/api/v1/journal/trades/${tradeId}/emotional-notes`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          emotional_notes_pre: notes.pre,
          emotional_notes_during: notes.during,
          emotional_notes_post: notes.post,
        }),
      });

      if (res.ok) {
        setTrades((prev) =>
          prev.map((t) =>
            t.trade_id === tradeId
              ? {
                  ...t,
                  emotional_notes_pre: notes.pre,
                  emotional_notes_during: notes.during,
                  emotional_notes_post: notes.post,
                }
              : t,
          ),
        );
      }
    } catch (err) {
      console.error('Failed to save emotional notes:', err);
    } finally {
      setSavingNotes(null);
    }
  };

  const generateMonthlyReview = async () => {
    try {
      setLoadingReport(true);
      const report: MonthlyReport = await api.generateMonthlyReview(currentMonth);
      setMonthlyReport(report);
    } catch (err) {
      console.error('Failed to generate monthly review:', err);
      Alert.alert('Error', 'No se pudo generar el review mensual');
    } finally {
      setLoadingReport(false);
    }
  };

  const loadMonthlyReview = async () => {
    try {
      const report: MonthlyReport = await api.getMonthlyReview(currentMonth);
      setMonthlyReport(report);
    } catch {
      // No report yet for this month — that's fine
    }
  };

  useEffect(() => {
    loadMonthlyReview();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleDiscretionary = async (tradeId: string) => {
    const trade = trades.find((t) => t.trade_id === tradeId);
    if (!trade) return;

    const newValue = !trade.is_discretionary;
    try {
      await api.markTradeDiscretionary(tradeId, trade.discretionary_notes || '');
      setTrades((prev) =>
        prev.map((t) =>
          t.trade_id === tradeId ? { ...t, is_discretionary: newValue } : t,
        ),
      );
    } catch (err) {
      console.error('Failed to toggle discretionary:', err);
    }
  };

  const openScreenshots = async (tradeId: string) => {
    try {
      const data = await api.getTradeScreenshots(tradeId);
      const files: string[] = data.files || data.screenshots || [];
      if (files.length === 0) {
        Alert.alert('Screenshots', 'No hay screenshots disponibles');
        return;
      }
      // Open the first screenshot URL
      const url = api.getScreenshotUrl(tradeId, files[0]);
      await Linking.openURL(url);
    } catch (err) {
      console.error('Failed to open screenshots:', err);
    }
  };

  // Compute discretionary ratio
  const discretionaryCount = trades.filter((t) => t.is_discretionary).length;
  const discretionaryRatio = trades.length > 0
    ? ((discretionaryCount / trades.length) * 100).toFixed(1)
    : '0.0';

  const formatDate = (dateStr: string) => {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('es-CO', {
        day: '2-digit',
        month: '2-digit',
        year: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return dateStr;
    }
  };

  const formatCurrency = (value: number): string => {
    return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatPct = (value: number): string => {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
  };

  // ── Stats Overview Card ─────────────────────────────────────────
  const renderStatsCard = () => {
    if (!stats) return null;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ESTADISTICAS GENERALES</Text>

        {/* Row 1: TRADES, WIN RATE, WIN RATE (Ex BE) */}
        <View style={styles.statsGrid}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>TRADES</Text>
            <Text style={styles.statValue}>{stats.total_trades}</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>WIN RATE</Text>
            <Text style={[
              styles.statValue,
              stats.win_rate >= 50 ? styles.profit : styles.loss,
            ]}>
              {stats.win_rate.toFixed(1)}%
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>WR (EX BE)</Text>
            <Text style={[
              styles.statValue,
              stats.win_rate_excl_be >= 50 ? styles.profit : styles.loss,
            ]}>
              {stats.win_rate_excl_be.toFixed(1)}%
            </Text>
          </View>
        </View>

        {/* Row 2: BALANCE, P&L ACC., PROFIT FACTOR */}
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>BALANCE</Text>
            <Text style={[styles.statValueSm, { color: theme.colors.neonCyan }]}>
              {formatCurrency(stats.current_balance)}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>P&L ACC.</Text>
            <Text style={[
              styles.statValueSm,
              stats.pnl_accumulated_pct >= 0 ? styles.profit : styles.loss,
            ]}>
              {formatPct(stats.pnl_accumulated_pct)}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>PROFIT F.</Text>
            <Text style={[
              styles.statValueSm,
              stats.profit_factor >= 1 ? styles.profit : styles.loss,
            ]}>
              {stats.profit_factor.toFixed(2)}
            </Text>
          </View>
        </View>

        {/* Row 3: DD ACTUAL, DD MAX, PEAK */}
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>DD ACTUAL</Text>
            <Text style={[styles.statValueSm, styles.loss]}>
              {stats.current_drawdown_pct.toFixed(2)}%
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>DD MAX</Text>
            <Text style={[styles.statValueSm, styles.loss]}>
              {stats.max_drawdown_pct.toFixed(2)}%
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>PEAK</Text>
            <Text style={[styles.statValueSm, { color: theme.colors.neonCyan }]}>
              {formatCurrency(stats.peak_balance)}
            </Text>
          </View>
        </View>

        {/* Row 4: RACHA ACTUAL, RACHA MAX, ACUMULADOR */}
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>RACHA ACT.</Text>
            <Text style={[
              styles.statValueSm,
              stats.current_winning_streak > 0 ? styles.profit : { color: theme.colors.neonCyan },
            ]}>
              {stats.current_winning_streak}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>RACHA MAX</Text>
            <Text style={[styles.statValueSm, styles.profit]}>
              {stats.max_winning_streak}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>ACUMULADOR</Text>
            <Text style={[
              styles.statValueSm,
              stats.accumulator >= 0 ? styles.profit : styles.loss,
            ]}>
              {stats.accumulator.toFixed(2)}
            </Text>
          </View>
        </View>

        {/* Row 5: DISCRETIONARY RATIO */}
        <View style={styles.statsRow}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>DISCRECIONAL</Text>
            <Text style={[styles.statValueSm, { color: '#ffb800' }]}>
              {discretionaryRatio}%
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>DISC. TRADES</Text>
            <Text style={[styles.statValueSm, { color: '#ffb800' }]}>
              {discretionaryCount}/{trades.length}
            </Text>
          </View>
          <View style={styles.stat} />
        </View>
      </View>
    );
  };

  // ── Monthly Returns Card ────────────────────────────────────────
  const renderMonthlyReturns = () => {
    if (!stats || !stats.monthly_returns) return null;
    const entries = Object.entries(stats.monthly_returns);
    if (entries.length === 0) return null;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>RETORNOS MENSUALES</Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.monthlyScroll}
        >
          {entries.map(([key, value]) => (
            <View key={key} style={styles.monthlyCard}>
              <Text style={styles.monthlyLabel}>{formatMonthKey(key)}</Text>
              <Text style={[
                styles.monthlyValue,
                value >= 0 ? styles.profit : styles.loss,
              ]}>
                {formatPct(value)}
              </Text>
            </View>
          ))}
        </ScrollView>
      </View>
    );
  };

  // ── DD Historico Card ───────────────────────────────────────────
  const renderDDHistorico = () => {
    if (!stats || !stats.dd_by_year) return null;
    const entries = Object.entries(stats.dd_by_year);
    if (entries.length === 0) return null;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>DD HISTORICO</Text>
        {entries.map(([year, value]) => (
          <View key={year} style={styles.configRow}>
            <Text style={styles.configLabel}>{year}</Text>
            <Text style={[styles.configValue, styles.loss]}>
              {value.toFixed(2)}%
            </Text>
          </View>
        ))}
      </View>
    );
  };

  // ── TP/SL/BE Counter Bar ────────────────────────────────────────
  const renderCounterBar = () => {
    if (!stats) return null;

    const total = stats.wins + stats.losses + stats.break_evens;
    const tpWidth = total > 0 ? (stats.wins / total) * 100 : 0;
    const slWidth = total > 0 ? (stats.losses / total) * 100 : 0;
    const beWidth = total > 0 ? (stats.break_evens / total) * 100 : 0;

    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>DISTRIBUCION TP / SL / BE</Text>

        {/* Colored bar */}
        <View style={styles.counterBarContainer}>
          {tpWidth > 0 && (
            <View style={[styles.counterBarSegment, { width: `${tpWidth}%`, backgroundColor: theme.colors.profit }]} />
          )}
          {slWidth > 0 && (
            <View style={[styles.counterBarSegment, { width: `${slWidth}%`, backgroundColor: theme.colors.loss }]} />
          )}
          {beWidth > 0 && (
            <View style={[styles.counterBarSegment, { width: `${beWidth}%`, backgroundColor: theme.colors.neonYellow }]} />
          )}
        </View>

        {/* Labels */}
        <View style={styles.counterLabels}>
          <View style={styles.counterLabelItem}>
            <View style={[styles.counterDot, { backgroundColor: theme.colors.profit }]} />
            <Text style={[styles.counterLabelText, styles.profit]}>
              TP: {stats.wins}
            </Text>
          </View>
          <View style={styles.counterLabelItem}>
            <View style={[styles.counterDot, { backgroundColor: theme.colors.loss }]} />
            <Text style={[styles.counterLabelText, styles.loss]}>
              SL: {stats.losses}
            </Text>
          </View>
          <View style={styles.counterLabelItem}>
            <View style={[styles.counterDot, { backgroundColor: theme.colors.neonYellow }]} />
            <Text style={[styles.counterLabelText, { color: theme.colors.neonYellow }]}>
              BE: {stats.break_evens}
            </Text>
          </View>
        </View>
      </View>
    );
  };

  // ── Trade Item ──────────────────────────────────────────────────
  const renderTradeItem = ({ item }: { item: JournalTrade }) => {
    const isExpanded = expandedTrade === item.trade_id;
    const notes = editingNotes[item.trade_id];

    return (
      <TouchableOpacity
        style={styles.tradeItem}
        onPress={() => toggleExpand(item.trade_id, item)}
        activeOpacity={0.8}
      >
        {/* Trade header row */}
        <View style={styles.tradeHeader}>
          <View style={styles.tradeLeft}>
            <View style={styles.tradeInstrumentRow}>
              <Text style={styles.tradeNumber}>#{item.trade_number}</Text>
              <View style={[styles.resultBadge, { borderColor: getResultColor(item.result) }]}>
                <Text style={[styles.resultBadgeText, { color: getResultColor(item.result) }]}>
                  {item.result}
                </Text>
              </View>
              <Text style={styles.tradeInstrument}>
                {item.instrument.replace('_', '/')}
              </Text>
            </View>
            <View style={styles.tradeTagsRow}>
              <Text style={[
                styles.tradeDirection,
                item.direction === 'BUY' ? styles.profit : styles.loss,
              ]}>
                {item.direction}
              </Text>
              <Text style={styles.tradeStrategy}>{item.strategy}</Text>
              <Text style={styles.tradeDate}>{formatDate(item.date)}</Text>
            </View>
          </View>
          <View style={styles.tradeRight}>
            <Text style={[
              styles.tradePnl,
              item.pnl_dollars >= 0 ? styles.profit : styles.loss,
            ]}>
              {item.pnl_dollars >= 0 ? '+' : ''}${item.pnl_dollars.toFixed(2)}
            </Text>
            <Text style={[
              styles.tradePnlPct,
              item.pnl_pct >= 0 ? styles.profit : styles.loss,
            ]}>
              {formatPct(item.pnl_pct)}
            </Text>
          </View>
        </View>

        {/* Balance / DD / Streak row */}
        <View style={styles.tradeMetaRow}>
          <Text style={styles.tradeMetaText}>
            Bal: {formatCurrency(item.balance_after)}
          </Text>
          <Text style={[styles.tradeMetaText, styles.loss]}>
            DD: {item.drawdown_pct.toFixed(2)}%
          </Text>
          {item.winning_streak > 0 && (
            <Text style={[styles.tradeMetaText, styles.profit]}>
              Racha: {item.winning_streak}
            </Text>
          )}
        </View>

        {/* Expandable emotional notes */}
        {isExpanded && notes && (
          <View style={styles.notesContainer}>
            <View style={styles.notesDivider} />

            {/* Discretionary flag */}
            <TouchableOpacity
              style={[
                styles.discretionaryBtn,
                item.is_discretionary && styles.discretionaryBtnActive,
              ]}
              onPress={() => toggleDiscretionary(item.trade_id)}
            >
              <Text style={styles.discretionaryBtnText}>
                {item.is_discretionary ? '◆ DISCRECIONAL' : '○ SISTEMÁTICO'}
              </Text>
            </TouchableOpacity>

            {/* Screenshots */}
            {item._screenshots && item._screenshots.length > 0 && (
              <TouchableOpacity onPress={() => openScreenshots(item.trade_id)}>
                <Text style={[styles.statLabel, { color: '#5df4fe', marginBottom: 8 }]}>
                  📸 {item._screenshots.length} screenshot(s)
                </Text>
              </TouchableOpacity>
            )}

            <Text style={styles.notesTitle}>NOTAS EMOCIONALES</Text>

            <Text style={styles.noteLabel}>PRE-TRADE</Text>
            <TextInput
              style={styles.noteInput}
              value={notes.pre}
              onChangeText={(text) =>
                setEditingNotes((prev) => ({
                  ...prev,
                  [item.trade_id]: { ...prev[item.trade_id], pre: text },
                }))
              }
              placeholder="Como te sentias antes de entrar?"
              placeholderTextColor={theme.colors.textMuted}
              multiline
              numberOfLines={2}
            />

            <Text style={styles.noteLabel}>DURANTE</Text>
            <TextInput
              style={styles.noteInput}
              value={notes.during}
              onChangeText={(text) =>
                setEditingNotes((prev) => ({
                  ...prev,
                  [item.trade_id]: { ...prev[item.trade_id], during: text },
                }))
              }
              placeholder="Que sentiste mientras el trade estaba abierto?"
              placeholderTextColor={theme.colors.textMuted}
              multiline
              numberOfLines={2}
            />

            <Text style={styles.noteLabel}>POST-TRADE</Text>
            <TextInput
              style={styles.noteInput}
              value={notes.post}
              onChangeText={(text) =>
                setEditingNotes((prev) => ({
                  ...prev,
                  [item.trade_id]: { ...prev[item.trade_id], post: text },
                }))
              }
              placeholder="Que aprendiste? Como te sientes ahora?"
              placeholderTextColor={theme.colors.textMuted}
              multiline
              numberOfLines={2}
            />

            <TouchableOpacity
              style={styles.saveNotesBtn}
              onPress={() => saveEmotionalNotes(item.trade_id)}
              disabled={savingNotes === item.trade_id}
            >
              {savingNotes === item.trade_id ? (
                <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
              ) : (
                <Text style={styles.saveNotesBtnText}>GUARDAR NOTAS</Text>
              )}
            </TouchableOpacity>
          </View>
        )}

        {/* Expand indicator */}
        <Text style={styles.expandIndicator}>
          {isExpanded ? '▲ Ocultar notas' : '▼ Notas emocionales'}
        </Text>
      </TouchableOpacity>
    );
  };

  // ── Loading State ───────────────────────────────────────────────
  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.cp2077Yellow} />
        <Text style={styles.loadingText}>Cargando journal...</Text>
      </View>
    );
  }

  // ── Error State ─────────────────────────────────────────────────
  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorIcon}>⚠</Text>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={fetchData}>
          <Text style={styles.retryBtnText}>REINTENTAR</Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── Monthly Review Card ──────────────────────────────────────────
  const renderMonthlyReview = () => {
    return (
      <View style={styles.card}>
        <Text style={styles.cardTitle}>MONTHLY REVIEW</Text>

        {/* Generate button */}
        <TouchableOpacity
          style={styles.actionButton}
          onPress={generateMonthlyReview}
          disabled={loadingReport}
        >
          {loadingReport ? (
            <ActivityIndicator size="small" color="#5df4fe" />
          ) : (
            <Text style={styles.actionButtonText}>GENERATE {currentMonth}</Text>
          )}
        </TouchableOpacity>

        {/* Show report data if loaded */}
        {monthlyReport && (
          <View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Win Rate</Text>
              <Text style={styles.statValue}>
                {(monthlyReport.win_rate * 100).toFixed(1)}%
              </Text>
            </View>
            <View style={styles.statRow}>
              <Text style={styles.statLabel}>Profit Factor</Text>
              <Text style={styles.statValue}>
                {monthlyReport.profit_factor.toFixed(2)}
              </Text>
            </View>
            {monthlyReport.best_strategy && (
              <View style={styles.statRow}>
                <Text style={styles.statLabel}>Best Strategy</Text>
                <Text style={[styles.statValue, { color: '#00ff88' }]}>
                  {monthlyReport.best_strategy}
                </Text>
              </View>
            )}
            {monthlyReport.worst_strategy && (
              <View style={styles.statRow}>
                <Text style={styles.statLabel}>Worst Strategy</Text>
                <Text style={[styles.statValue, { color: '#da4453' }]}>
                  {monthlyReport.worst_strategy}
                </Text>
              </View>
            )}

            {/* Strategy breakdown */}
            {Object.entries(monthlyReport.by_strategy || {}).map(([name, data]: [string, any]) => (
              <View key={name} style={styles.reviewStrategy}>
                <Text style={[styles.statLabel, { color: STRATEGY_COLORS[name] || '#8892a0' }]}>
                  {name}
                </Text>
                <Text style={styles.statValue}>
                  {data.trades} trades | ${data.pnl?.toFixed(2)}
                </Text>
              </View>
            ))}

            {/* Recommendations */}
            {monthlyReport.recommendations?.map((rec: string, i: number) => (
              <Text key={i} style={styles.recommendationText}>
                → {rec}
              </Text>
            ))}
          </View>
        )}
      </View>
    );
  };

  // ── Main Render ─────────────────────────────────────────────────
  const ListHeader = () => (
    <View>
      {renderStatsCard()}
      {renderMonthlyReturns()}
      {renderDDHistorico()}
      {renderMonthlyReview()}
      {renderCounterBar()}
      <Text style={styles.sectionTitle}>ULTIMOS TRADES</Text>
    </View>
  );

  const ListEmpty = () => (
    <View style={styles.emptyContainer}>
      <Text style={styles.emptyIcon}>▤</Text>
      <Text style={styles.emptyText}>No hay trades registrados</Text>
      <Text style={styles.emptySubtext}>
        Los trades apareceran aqui cuando se cierren posiciones
      </Text>
    </View>
  );

  const ListFooter = () => (
    <View style={{ height: theme.spacing.xl }} />
  );

  return (
    <View style={styles.container}>
      <Text style={styles.header}>JOURNAL</Text>
      <Text style={styles.subheader}>Registro de Trades — TradingLab</Text>

      <FlatList
        data={trades}
        keyExtractor={(item) => item.trade_id}
        renderItem={renderTradeItem}
        ListHeaderComponent={ListHeader}
        ListEmptyComponent={ListEmpty}
        ListFooterComponent={ListFooter}
        style={styles.list}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.md,
  },
  centered: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.md,
  },
  header: {
    fontFamily: theme.fonts.heading,
    fontSize: 20,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 4,
    marginTop: theme.spacing.lg,
  },
  subheader: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: theme.spacing.md,
  },
  list: {
    flex: 1,
  },
  sectionTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 3,
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  // Cards
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.cp2077Yellow,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
  },
  cardTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 3,
    marginBottom: theme.spacing.sm,
  },
  // Stats grid
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: theme.spacing.sm,
  },
  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.sm,
    marginTop: theme.spacing.xs,
  },
  stat: {
    alignItems: 'center',
    flex: 1,
  },
  statLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  statValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.textSecondary,
    marginTop: 4,
  },
  statValueSm: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    marginTop: 4,
  },
  profit: {
    color: theme.colors.profit,
  },
  loss: {
    color: theme.colors.loss,
  },
  // Config rows (reused pattern from Settings)
  configRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: theme.spacing.xs + 2,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  configLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  configValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  // Monthly returns
  monthlyScroll: {
    paddingVertical: theme.spacing.xs,
    gap: theme.spacing.sm,
  },
  monthlyCard: {
    backgroundColor: theme.colors.backgroundLight,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
    alignItems: 'center',
    minWidth: 100,
  },
  monthlyLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    marginBottom: 4,
  },
  monthlyValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    letterSpacing: 1,
  },
  // Counter bar
  counterBarContainer: {
    flexDirection: 'row',
    height: 8,
    borderRadius: theme.borderRadius.round,
    overflow: 'hidden',
    marginBottom: theme.spacing.sm,
  },
  counterBarSegment: {
    height: '100%',
  },
  counterLabels: {
    flexDirection: 'row',
    justifyContent: 'space-around',
  },
  counterLabelItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  counterDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  counterLabelText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1,
  },
  // Trade list items
  tradeItem: {
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  tradeHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  tradeLeft: {
    flex: 1,
  },
  tradeInstrumentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  tradeNumber: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  resultBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    borderWidth: 1,
  },
  resultBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 1,
    fontWeight: 'bold',
  },
  tradeInstrument: {
    fontFamily: theme.fonts.mono,
    fontSize: 15,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  tradeTagsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  tradeDirection: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    letterSpacing: 1,
  },
  tradeStrategy: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    borderWidth: 1,
    borderColor: theme.colors.textMuted,
  },
  tradeDate: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  tradeRight: {
    alignItems: 'flex-end',
  },
  tradePnl: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    fontWeight: 'bold',
  },
  tradePnlPct: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    marginTop: 2,
  },
  tradeMetaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.xs,
  },
  tradeMetaText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },
  // Emotional notes
  notesContainer: {
    marginTop: theme.spacing.sm,
  },
  notesDivider: {
    height: 1,
    backgroundColor: theme.colors.cp2077YellowDim,
    marginBottom: theme.spacing.sm,
    opacity: 0.5,
  },
  notesTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 10,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 3,
    marginBottom: theme.spacing.sm,
  },
  noteLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: theme.spacing.xs,
    marginTop: theme.spacing.xs,
  },
  noteInput: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
    backgroundColor: theme.colors.backgroundLight,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    minHeight: 44,
    textAlignVertical: 'top',
  },
  saveNotesBtn: {
    marginTop: theme.spacing.sm,
    alignSelf: 'flex-end',
    backgroundColor: theme.colors.cp2077Yellow,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs + 2,
    borderRadius: theme.borderRadius.sm,
  },
  saveNotesBtnText: {
    fontFamily: theme.fonts.heading,
    fontSize: 10,
    color: theme.colors.backgroundDark,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  expandIndicator: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    letterSpacing: 1,
    opacity: 0.7,
  },
  // Discretionary toggle
  discretionaryBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: '#2a2445',
    marginBottom: 8,
    alignSelf: 'flex-start',
  },
  discretionaryBtnActive: {
    borderColor: '#ffb800',
    backgroundColor: 'rgba(255, 184, 0, 0.15)',
  },
  discretionaryBtnText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: '#8892a0',
  },
  // Monthly review action button
  actionButton: {
    backgroundColor: 'rgba(0, 240, 255, 0.15)',
    borderWidth: 1,
    borderColor: '#5df4fe',
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    marginVertical: 8,
  },
  actionButtonText: {
    fontFamily: theme.fonts.heading,
    fontSize: 14,
    color: '#5df4fe',
    fontWeight: 'bold',
  },
  // Strategy row in monthly review
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  reviewStrategy: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  recommendationText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: '#ffb800',
    marginTop: 4,
  },
  // Empty state
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: theme.spacing.xxl,
  },
  emptyIcon: {
    fontSize: 48,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.md,
  },
  emptyText: {
    fontFamily: theme.fonts.primary,
    fontSize: 14,
    color: theme.colors.textMuted,
    textAlign: 'center',
  },
  emptySubtext: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    opacity: 0.6,
  },
  // Loading / Error
  loadingText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textMuted,
    marginTop: theme.spacing.md,
    letterSpacing: 2,
  },
  errorIcon: {
    fontSize: 40,
    color: theme.colors.neonRed,
    marginBottom: theme.spacing.md,
  },
  errorText: {
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    color: theme.colors.neonRed,
    textAlign: 'center',
  },
  retryBtn: {
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.cp2077Yellow,
    borderRadius: theme.borderRadius.md,
  },
  retryBtnText: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 2,
  },
});
