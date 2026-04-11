/**
 * NeonTrade AI - Journal Screen
 * Comprehensive trade journal with stats, trade list, and emotional notes.
 * CyberPunk 2077 HUD redesign with sub-navigation pills.
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
const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);
import {
  HUDCard,
  HUDSectionTitle,
  HUDStatRow,
  HUDBadge,
  HUDDivider,
  SubNavPills,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
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
  const parts = key.split('-');
  if (parts.length === 2) {
    const [yearOrMonth, monthOrYear] = parts;
    if (yearOrMonth.length === 4) {
      return `${MONTH_LABELS[monthOrYear] || monthOrYear} ${yearOrMonth}`;
    }
    return `${MONTH_LABELS[yearOrMonth] || yearOrMonth} ${monthOrYear}`;
  }
  return key;
};

const SUB_NAV_OPTIONS = [
  { key: 'history', label: 'HISTORY' },
  { key: 'journal', label: 'JOURNAL' },
];

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
        authFetch(`${API_URL}/api/v1/journal/trades?limit=200`),
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
      // No report yet for this month
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
      await api.markTradeDiscretionary(tradeId, newValue, trade.discretionary_notes || '');
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

  // ── Stats Dashboard Card ───────────────────────────────────────
  const renderStatsDashboard = () => {
    if (!stats) return null;

    return (
      <HUDCard accentColor={theme.colors.neonCyan}>
        <HUDSectionTitle title="ESTADISTICAS GENERALES" color={theme.colors.neonCyan} />

        <View style={styles.statsGrid}>
          {/* Row 1 */}
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>WIN RATE</Text>
            <Text style={[styles.statCellValue, stats.win_rate >= 50 ? styles.profit : styles.loss]}>
              {safe(stats.win_rate, 1)}%
            </Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>WR (EX BE)</Text>
            <Text style={[styles.statCellValue, stats.win_rate_excl_be >= 50 ? styles.profit : styles.loss]}>
              {safe(stats.win_rate_excl_be, 1)}%
            </Text>
          </View>

          {/* Row 2 */}
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>BALANCE</Text>
            <Text style={[styles.statCellValue, { color: theme.colors.neonCyan }]}>
              {formatCurrency(stats.current_balance)}
            </Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>P&L ACC.</Text>
            <Text style={[styles.statCellValue, stats.pnl_accumulated_pct >= 0 ? styles.profit : styles.loss]}>
              {formatPct(stats.pnl_accumulated_pct)}
            </Text>
          </View>

          {/* Row 3 */}
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>PROFIT FACTOR</Text>
            <Text style={[styles.statCellValue, stats.profit_factor >= 1 ? styles.profit : styles.loss]}>
              {safe(stats.profit_factor)}
            </Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>ACUMULADOR</Text>
            <Text style={[styles.statCellValue, stats.accumulator >= 0 ? styles.profit : styles.loss]}>
              {safe(stats.accumulator)}
            </Text>
          </View>

          {/* Row 4 */}
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>DD ACTUAL</Text>
            <Text style={[styles.statCellValue, styles.loss]}>
              {safe(stats.current_drawdown_pct)}%
            </Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>DD MAX</Text>
            <Text style={[styles.statCellValue, styles.loss]}>
              {safe(stats.max_drawdown_pct)}%
            </Text>
          </View>

          {/* Row 5 */}
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>RACHA ACT.</Text>
            <Text style={[styles.statCellValue, stats.current_winning_streak > 0 ? styles.profit : { color: theme.colors.textMuted }]}>
              {stats.current_winning_streak}
            </Text>
          </View>
          <View style={styles.statCell}>
            <Text style={styles.statCellLabel}>RACHA MAX</Text>
            <Text style={[styles.statCellValue, styles.profit]}>
              {stats.max_winning_streak}
            </Text>
          </View>
        </View>
      </HUDCard>
    );
  };

  // ── Monthly Returns Card ────────────────────────────────────────
  const renderMonthlyReturns = () => {
    if (!stats || !stats.monthly_returns) return null;
    const entries = Object.entries(stats.monthly_returns);
    if (entries.length === 0) return null;

    return (
      <HUDCard>
        <HUDSectionTitle title="RETORNOS MENSUALES" />
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.monthlyScroll}
        >
          {entries.map(([key, value]) => (
            <View key={key} style={styles.monthlyItem}>
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
      </HUDCard>
    );
  };

  // ── Monthly Review Card ──────────────────────────────────────────
  const renderMonthlyReview = () => {
    return (
      <HUDCard>
        <HUDSectionTitle title="MONTHLY REVIEW" />

        {/* Generate button - CP2077 yellow */}
        <TouchableOpacity
          style={styles.generateButton}
          onPress={generateMonthlyReview}
          disabled={loadingReport}
        >
          {loadingReport ? (
            <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
          ) : (
            <Text style={styles.generateButtonText}>GENERAR REVIEW {currentMonth}</Text>
          )}
        </TouchableOpacity>

        {/* Report data */}
        {monthlyReport && (
          <View style={styles.reviewContent}>
            <HUDDivider />
            <HUDStatRow
              label="WIN RATE"
              value={`${(monthlyReport.win_rate * 100).toFixed(1)}%`}
              valueColor={theme.colors.textWhite}
            />
            <HUDStatRow
              label="PROFIT FACTOR"
              value={safe(monthlyReport?.profit_factor)}
              valueColor={theme.colors.textWhite}
            />
            <HUDStatRow
              label="TRADES"
              value={monthlyReport.total_trades}
              valueColor={theme.colors.textWhite}
            />

            {monthlyReport.best_strategy && (
              <HUDStatRow
                label="MEJOR ESTRATEGIA"
                value={monthlyReport.best_strategy}
                valueColor={theme.colors.neonGreen}
              />
            )}
            {monthlyReport.worst_strategy && (
              <HUDStatRow
                label="PEOR ESTRATEGIA"
                value={monthlyReport.worst_strategy}
                valueColor={theme.colors.neonRed}
              />
            )}

            {/* Strategy breakdown */}
            {Object.entries(monthlyReport.by_strategy || {}).length > 0 && (
              <View style={styles.strategyBreakdown}>
                <HUDDivider />
                <Text style={styles.breakdownTitle}>POR ESTRATEGIA</Text>
                {Object.entries(monthlyReport.by_strategy || {}).map(([name, data]: [string, any]) => (
                  <View key={name} style={styles.breakdownRow}>
                    <View style={[styles.breakdownDot, { backgroundColor: STRATEGY_COLORS[name] || theme.colors.textMuted }]} />
                    <Text style={[styles.breakdownName, { color: STRATEGY_COLORS[name] || theme.colors.textMuted }]}>
                      {name}
                    </Text>
                    <Text style={styles.breakdownDetail}>
                      {data.trades}T | ${data.pnl?.toFixed(2)}
                    </Text>
                  </View>
                ))}
              </View>
            )}

            {/* Recommendations */}
            {monthlyReport.recommendations && monthlyReport.recommendations.length > 0 && (
              <View style={styles.recommendationsSection}>
                <HUDDivider />
                <Text style={styles.breakdownTitle}>RECOMENDACIONES</Text>
                {monthlyReport.recommendations.map((rec: string, i: number) => (
                  <Text key={i} style={styles.recommendationText}>
                    → {rec}
                  </Text>
                ))}
              </View>
            )}
          </View>
        )}
      </HUDCard>
    );
  };

  // ── Trade Item ──────────────────────────────────────────────────
  const renderTradeItem = ({ item }: { item: JournalTrade }) => {
    const isExpanded = expandedTrade === item.trade_id;
    const notes = editingNotes[item.trade_id];
    const stratColor = STRATEGY_COLORS[item.strategy?.toUpperCase()] || theme.colors.textMuted;

    return (
      <TouchableOpacity
        activeOpacity={0.85}
        onPress={() => toggleExpand(item.trade_id, item)}
      >
        <HUDCard accentColor={stratColor}>
          {/* Trade header row */}
          <View style={styles.tradeHeader}>
            <View style={styles.tradeLeft}>
              <View style={styles.tradeInstrumentRow}>
                <Text style={styles.tradeNumber}>#{item.trade_number}</Text>
                <HUDBadge
                  label={item.result}
                  color={getResultColor(item.result)}
                  small
                />
                <Text style={styles.tradeInstrument}>
                  {item.instrument.replace('_', '/')}
                </Text>
              </View>
              <View style={styles.tradeTagsRow}>
                <HUDBadge
                  label={item.direction}
                  color={item.direction === 'BUY' ? theme.colors.profit : theme.colors.loss}
                  small
                />
                <HUDBadge
                  label={item.strategy}
                  color={stratColor}
                  small
                />
                <Text style={styles.tradeDate}>{formatDate(item.date)}</Text>
              </View>
            </View>
            <View style={styles.tradeRight}>
              <Text style={[
                styles.tradePnl,
                item.pnl_dollars >= 0 ? styles.profit : styles.loss,
              ]}>
                {item.pnl_dollars >= 0 ? '+' : ''}${safe(item.pnl_dollars)}
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
              DD: {safe(item.drawdown_pct)}%
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
              <HUDDivider color={theme.colors.cp2077YellowDim} />

              {/* Discretionary flag */}
              <TouchableOpacity
                style={[
                  styles.discretionaryBtn,
                  item.is_discretionary && styles.discretionaryBtnActive,
                ]}
                onPress={() => toggleDiscretionary(item.trade_id)}
              >
                <Text style={[
                  styles.discretionaryBtnText,
                  item.is_discretionary && { color: theme.colors.neonYellow },
                ]}>
                  {item.is_discretionary ? '◆ DISCRECIONAL' : '○ SISTEMATICO'}
                </Text>
              </TouchableOpacity>

              {/* Screenshots */}
              {item._screenshots && item._screenshots.length > 0 && (
                <TouchableOpacity onPress={() => openScreenshots(item.trade_id)}>
                  <Text style={styles.screenshotLink}>
                    SCREENSHOTS ({item._screenshots.length})
                  </Text>
                </TouchableOpacity>
              )}

              {/* ASR Checklist display */}
              <View style={styles.asrSection}>
                <Text style={styles.asrTitle}>ASR CHECKLIST</Text>
                <Text style={styles.asrItem}>
                  {item.result === 'TP' ? '[x]' : '[ ]'} Take Profit alcanzado
                </Text>
                <Text style={styles.asrItem}>
                  {item.result === 'SL' ? '[x]' : '[ ]'} Stop Loss ejecutado
                </Text>
                <Text style={styles.asrItem}>
                  {item.result === 'BE' ? '[x]' : '[ ]'} Break Even activado
                </Text>
              </View>

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
        </HUDCard>
      </TouchableOpacity>
    );
  };

  // ── Loading State ───────────────────────────────────────────────
  if (loading) {
    return (
      <View style={styles.centeredContainer}>
        <LoadingState message="Cargando journal..." />
      </View>
    );
  }

  // ── Error State ─────────────────────────────────────────────────
  if (error && trades.length === 0) {
    return (
      <View style={styles.centeredContainer}>
        <SubNavPills options={SUB_NAV_OPTIONS} activeKey="journal" onSelect={() => {}} />
        <ErrorState message={error} onRetry={fetchData} />
      </View>
    );
  }

  // ── List Header ─────────────────────────────────────────────────
  const ListHeader = () => (
    <View>
      {renderStatsDashboard()}
      {renderMonthlyReturns()}
      {renderMonthlyReview()}
      <HUDSectionTitle title="ULTIMOS TRADES" icon="▤" />
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

  return (
    <View style={styles.container}>
      {/* Sub-navigation pills */}
      <SubNavPills options={SUB_NAV_OPTIONS} activeKey="journal" onSelect={() => {}} />

      <FlatList
        data={trades}
        keyExtractor={(item) => item.trade_id}
        renderItem={renderTradeItem}
        ListHeaderComponent={ListHeader}
        ListEmptyComponent={ListEmpty}
        ListFooterComponent={() => <View style={{ height: theme.spacing.xl }} />}
        style={styles.list}
        showsVerticalScrollIndicator={false}
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
    paddingTop: theme.spacing.lg,
  },
  centeredContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
    justifyContent: 'center',
    alignItems: 'center',
    padding: theme.spacing.md,
  },
  list: {
    flex: 1,
  },

  // Stats grid (2 columns)
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: theme.spacing.sm,
  },
  statCell: {
    flex: 1,
    minWidth: '45%',
    backgroundColor: theme.colors.backgroundLight,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    alignItems: 'center',
  },
  statCellLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginBottom: 2,
  },
  statCellValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    color: theme.colors.textWhite,
  },
  profit: {
    color: theme.colors.profit,
  },
  loss: {
    color: theme.colors.loss,
  },

  // Monthly returns
  monthlyScroll: {
    paddingVertical: theme.spacing.xs,
    gap: theme.spacing.sm,
  },
  monthlyItem: {
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

  // Generate Review Button (CP2077 Yellow)
  generateButton: {
    backgroundColor: theme.colors.cp2077Yellow,
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: theme.borderRadius.sm,
    alignItems: 'center',
    marginVertical: theme.spacing.sm,
  },
  generateButtonText: {
    fontFamily: theme.fonts.heading,
    fontSize: 13,
    color: theme.colors.backgroundDark,
    letterSpacing: 3,
    fontWeight: 'bold',
  },

  // Review content
  reviewContent: {
    marginTop: theme.spacing.xs,
  },
  strategyBreakdown: {
    marginTop: theme.spacing.xs,
  },
  breakdownTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 10,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 2,
    marginBottom: 4,
  },
  breakdownRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 3,
  },
  breakdownDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  breakdownName: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    letterSpacing: 1,
    flex: 1,
  },
  breakdownDetail: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
  },
  recommendationsSection: {
    marginTop: theme.spacing.xs,
  },
  recommendationText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.neonYellow,
    marginTop: 4,
    letterSpacing: 1,
  },

  // Trade items
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
  tradeInstrument: {
    fontFamily: theme.fonts.heading,
    fontSize: 15,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  tradeTagsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 6,
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
    fontSize: 18,
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
  notesTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 10,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 3,
    marginBottom: theme.spacing.sm,
    marginTop: theme.spacing.sm,
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
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    marginBottom: 8,
    alignSelf: 'flex-start',
  },
  discretionaryBtnActive: {
    borderColor: theme.colors.neonYellow,
    backgroundColor: 'rgba(255, 184, 0, 0.15)',
  },
  discretionaryBtnText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 1,
  },

  // Screenshot link
  screenshotLink: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    color: theme.colors.neonCyan,
    letterSpacing: 2,
    marginBottom: 8,
  },

  // ASR checklist
  asrSection: {
    marginBottom: theme.spacing.sm,
    paddingVertical: theme.spacing.xs,
  },
  asrTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 10,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 2,
    marginBottom: 4,
  },
  asrItem: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 1,
    paddingVertical: 1,
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
});
