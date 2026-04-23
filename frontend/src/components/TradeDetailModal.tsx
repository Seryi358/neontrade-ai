/**
 * Trade detail modal — shows everything the mentorship exam needs for a
 * single trade: OPEN/CLOSE screenshots, the reasoning captured at signal
 * detection, and the post-mortem ASR (AI self-review) checklist.
 *
 * Zero branding by design: this view will be shown to the TradingLab
 * mentor and must not reveal the custom dashboard.
 */
import React, { useEffect, useState } from 'react';
import {
  Modal,
  View,
  Text,
  ScrollView,
  StyleSheet,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  Dimensions,
  Platform,
} from 'react-native';
import { theme } from '../theme/apple-glass';
import { API_URL, authFetch, STRATEGY_COLORS } from '../services/api';

const safe = (v: any, d = 2): string =>
  v == null || isNaN(v) ? '---' : Number(v).toFixed(d);

interface Props {
  tradeId: string | null;
  onClose: () => void;
}

interface HistoryRow {
  id: string;
  instrument: string;
  strategy: string;
  strategy_variant?: string;
  direction: 'BUY' | 'SELL';
  entry_price: number;
  exit_price?: number;
  stop_loss?: number;
  take_profit?: number;
  pnl?: number;
  pnl_pips?: number;
  status: string;
  mode?: string;
  confidence?: number;
  risk_reward_ratio?: number;
  reasoning?: string;
  opened_at?: string;
  closed_at?: string;
}

interface JournalRow {
  trade_id: string;
  strategy?: string;
  pnl_dollars?: number;
  pnl_pct?: number;
  result?: string;
  rr_achieved?: number;
  asr_completed?: boolean;
  asr_htf_correct?: boolean;
  asr_ltf_correct?: boolean;
  asr_strategy_correct?: boolean;
  asr_sl_correct?: boolean;
  asr_tp_correct?: boolean;
  asr_management_correct?: boolean;
  asr_would_enter_again?: boolean;
  asr_error_type?: string;
  asr_lessons?: string;
}

export default function TradeDetailModal({ tradeId, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [history, setHistory] = useState<HistoryRow | null>(null);
  const [journal, setJournal] = useState<JournalRow | null>(null);
  const [openImg, setOpenImg] = useState<string | null>(null);
  const [closeImg, setCloseImg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!tradeId) return;
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [histRes, journRes, shotRes] = await Promise.all([
          authFetch(`${API_URL}/api/v1/history?limit=200`),
          authFetch(`${API_URL}/api/v1/journal/trades?limit=200`),
          authFetch(`${API_URL}/api/v1/screenshots/${tradeId}`),
        ]);
        if (cancelled) return;
        const histList: HistoryRow[] = await histRes.json();
        const journList: JournalRow[] = await journRes.json();
        const shotsResp: { screenshots: string[] } = await shotRes.json();
        const h = histList.find((t) => t.id === tradeId) || null;
        const j = journList.find((t) => t.trade_id === tradeId) || null;
        setHistory(h);
        setJournal(j);
        // Newest open + close by filename suffix
        const shots = (shotsResp.screenshots || []).slice().sort();
        const opens = shots.filter((s) => s.includes('_open_'));
        const closes = shots.filter((s) => s.includes('_close_'));
        const openFile = opens.length ? opens[opens.length - 1].split('/').pop()! : null;
        const closeFile = closes.length ? closes[closes.length - 1].split('/').pop()! : null;
        setOpenImg(openFile ? `${API_URL}/api/v1/screenshots/${tradeId}/image/${openFile}` : null);
        setCloseImg(closeFile ? `${API_URL}/api/v1/screenshots/${tradeId}/image/${closeFile}` : null);
      } catch (e: any) {
        if (!cancelled) setError(String(e?.message || e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [tradeId]);

  if (!tradeId) return null;

  const strategy = (history?.strategy_variant || journal?.strategy || history?.strategy || '—').toUpperCase();
  const dotColor = STRATEGY_COLORS[strategy] || theme.colors.textMuted;
  const pnl = history?.pnl ?? journal?.pnl_dollars ?? 0;
  const pnlPositive = pnl >= 0;

  const asrRow = (label: string, val: boolean | null | undefined) => {
    const sym = val === true ? '✓' : val === false ? '✗' : '—';
    const color = val === true ? theme.colors.profit : val === false ? theme.colors.loss : theme.colors.textMuted;
    return (
      <View style={styles.asrRow} key={label}>
        <Text style={styles.asrLabel}>{label}</Text>
        <Text style={[styles.asrValue, { color }]}>{sym}</Text>
      </View>
    );
  };

  return (
    <Modal visible={!!tradeId} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.modal}>
          <View style={styles.header}>
            <View style={styles.headerLeft}>
              <View style={[styles.dot, { backgroundColor: dotColor }]} />
              <Text style={styles.title}>
                {history?.instrument?.replace('_', '/') || journal?.trade_id || tradeId}
                <Text style={styles.strategySuffix}>  ·  {strategy}</Text>
              </Text>
            </View>
            <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
              <Text style={styles.closeBtnText}>✕</Text>
            </TouchableOpacity>
          </View>

          {loading && (
            <View style={styles.loadingWrap}>
              <ActivityIndicator color={theme.colors.accent} />
            </View>
          )}
          {error && <Text style={styles.error}>{error}</Text>}

          {!loading && (
            <ScrollView contentContainerStyle={styles.scroll}>
              {/* ── Metrics row ─────────────────────────── */}
              <View style={styles.metricsRow}>
                <Metric label="Dirección" value={history?.direction || '—'} />
                <Metric label="Entry" value={safe(history?.entry_price, 4)} />
                <Metric label="Exit" value={safe(history?.exit_price, 4)} />
                <Metric
                  label="P&L"
                  value={`${pnlPositive ? '+' : ''}$${safe(pnl)}`}
                  color={pnlPositive ? theme.colors.profit : theme.colors.loss}
                />
              </View>
              <View style={styles.metricsRow}>
                <Metric label="SL" value={safe(history?.stop_loss, 4)} />
                <Metric label="TP" value={safe(history?.take_profit, 4)} />
                <Metric label="R:R" value={safe(history?.risk_reward_ratio, 2)} />
                <Metric label="Status" value={(history?.status || '—').replace('closed_', '')} />
              </View>

              {/* ── Por qué se ejecutó (reasoning) ─────── */}
              {history?.reasoning && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Por qué se ejecutó</Text>
                  <Text style={styles.reasoningText}>{history.reasoning}</Text>
                </View>
              )}

              {/* ── Screenshot OPEN ──────────────────────── */}
              {openImg && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Setup de entrada</Text>
                  <Image
                    source={{ uri: openImg }}
                    style={styles.chartImg}
                    resizeMode="contain"
                  />
                </View>
              )}

              {/* ── Screenshot CLOSE ────────────────────── */}
              {closeImg && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Resultado del trade</Text>
                  <Image
                    source={{ uri: closeImg }}
                    style={styles.chartImg}
                    resizeMode="contain"
                  />
                </View>
              )}

              {/* ── Análisis post-mortem (ASR) ───────────── */}
              {journal?.asr_completed && (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Revisión post-trade</Text>
                  {asrRow('Análisis HTF correcto', journal.asr_htf_correct)}
                  {asrRow('Señal LTF clara', journal.asr_ltf_correct)}
                  {asrRow('Estrategia adecuada', journal.asr_strategy_correct)}
                  {asrRow('SL en lugar correcto', journal.asr_sl_correct)}
                  {asrRow('TP en lugar correcto', journal.asr_tp_correct)}
                  {asrRow('Gestión correcta', journal.asr_management_correct)}
                  {asrRow('¿Volvería a entrar?', journal.asr_would_enter_again)}
                  {journal.asr_error_type && (
                    <View style={styles.asrRow}>
                      <Text style={styles.asrLabel}>Tipo de error</Text>
                      <Text style={[styles.asrValue, { color: theme.colors.textMuted }]}>
                        {journal.asr_error_type}
                      </Text>
                    </View>
                  )}
                  {journal.asr_lessons && (
                    <View style={styles.lessonsBox}>
                      <Text style={styles.lessonsLabel}>Lecciones</Text>
                      <Text style={styles.lessonsText}>{journal.asr_lessons}</Text>
                    </View>
                  )}
                </View>
              )}
            </ScrollView>
          )}
        </View>
      </View>
    </Modal>
  );
}

function Metric({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={[styles.metricValue, color ? { color } : null]}>{value}</Text>
    </View>
  );
}

const screenW = Dimensions.get('window').width;
const isWeb = Platform.OS === 'web';
const modalWidth = isWeb ? Math.min(screenW * 0.9, 900) : screenW * 0.94;

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  modal: {
    width: modalWidth,
    maxHeight: '92%',
    backgroundColor: theme.colors.bgSecondary,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: theme.colors.divider,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.divider,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  dot: { width: 10, height: 10, borderRadius: 5, marginRight: 10 },
  title: { color: theme.colors.textWhite, fontSize: 18, fontWeight: '700' },
  strategySuffix: { color: theme.colors.textMuted, fontSize: 14, fontWeight: '500' },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: theme.colors.bgTertiary,
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeBtnText: { color: theme.colors.textWhite, fontSize: 18 },
  loadingWrap: { padding: 40, alignItems: 'center' },
  error: { padding: 20, color: theme.colors.loss },
  scroll: { padding: 16 },
  metricsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
    gap: 8,
  },
  metric: { flex: 1 },
  metricLabel: { color: theme.colors.textMuted, fontSize: 11, marginBottom: 2 },
  metricValue: { color: theme.colors.textWhite, fontSize: 15, fontWeight: '600' },
  section: {
    marginTop: 20,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: theme.colors.divider,
  },
  sectionTitle: {
    color: theme.colors.textMuted,
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 10,
  },
  reasoningText: {
    color: theme.colors.textWhite,
    fontSize: 13,
    lineHeight: 19,
    fontFamily: Platform.select({ web: 'monospace', default: 'Courier' }),
  },
  chartImg: {
    width: '100%',
    aspectRatio: 16 / 9,
    backgroundColor: '#fff',
    borderRadius: 8,
  },
  asrRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
  },
  asrLabel: { color: theme.colors.textWhite, fontSize: 14 },
  asrValue: { fontSize: 16, fontWeight: '700' },
  lessonsBox: {
    marginTop: 14,
    backgroundColor: theme.colors.bgTertiary,
    padding: 12,
    borderRadius: 8,
  },
  lessonsLabel: {
    color: theme.colors.textMuted,
    fontSize: 11,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 6,
  },
  lessonsText: { color: theme.colors.textWhite, fontSize: 14, lineHeight: 20 },
});
