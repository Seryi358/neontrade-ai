/**
 * Atlas - Manual Mode Screen
 * Shows pending trade setups awaiting user approval.
 * Apple Liquid Glass Light design.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { theme } from '../theme/apple-glass';
const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);
import {
  HUDCard,
  HUDHeader,
  HUDSectionTitle,
  HUDBadge,
  HUDDivider,
  LoadingState,
  ErrorState,
  EmptyState,
} from '../components/HUDComponents';
import { API_URL, authFetch, STRATEGY_COLORS } from '../services/api';

// ─── Types ──────────────────────────────────────────────────────────────────

interface PendingSetup {
  id: string;
  timestamp: string;
  instrument: string;
  strategy: string;
  direction: 'BUY' | 'SELL';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  units: number;
  confidence: number;
  risk_reward_ratio: number;
  reasoning: string;
  checklist?: string[];
  status: string;
  expires_at: string;
}

// ─── Helpers ────────────────────────────────────────────────────────────────

const getStrategyDotColor = (color: string): string => {
  return STRATEGY_COLORS[color?.toUpperCase()] || theme.colors.textMuted;
};

const getConfidenceLabel = (confidence: number): string => {
  if (confidence >= 75) return 'ALTA';
  if (confidence >= 50) return 'MEDIA';
  return 'BAJA';
};

const getConfidenceColor = (confidence: number): string => {
  if (confidence >= 75) return theme.colors.neonGreen;
  if (confidence >= 50) return theme.colors.neonYellow;
  return theme.colors.neonOrange;
};

// ─── Component ──────────────────────────────────────────────────────────────

export default function ManualModeScreen() {
  const [setups, setSetups] = useState<PendingSetup[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const fetchSetups = useCallback(async () => {
    try {
      setError(null);
      const res = await authFetch(`${API_URL}/api/v1/pending-setups`);
      if (!res.ok) throw new Error('Error al cargar');
      const data = await res.json();
      setSetups(data);
    } catch (err) {
      console.error('Failed to fetch pending setups:', err);
      setError('No se pudo conectar al servidor');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSetups();
    const interval = setInterval(fetchSetups, 10000);
    return () => clearInterval(interval);
  }, [fetchSetups]);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchSetups();
    setRefreshing(false);
  };

  const approveSetup = async (id: string) => {
    try {
      setActionLoading(`approve-${id}`);
      const res = await authFetch(`${API_URL}/api/v1/pending-setups/${id}/approve`, {
        method: 'POST',
      });
      if (res.ok) {
        setSetups((prev) => prev.filter((s) => s.id !== id));
      } else {
        const errData = await res.json().catch(() => ({ detail: res.statusText }));
        Alert.alert('Error', errData.detail || `Error al aprobar (${res.status})`);
      }
    } catch (err) {
      console.error('Failed to approve setup:', err);
      Alert.alert('Error', 'No se pudo conectar al servidor');
    } finally {
      setActionLoading(null);
    }
  };

  const rejectSetup = async (id: string) => {
    try {
      setActionLoading(`reject-${id}`);
      const res = await authFetch(`${API_URL}/api/v1/pending-setups/${id}/reject`, {
        method: 'POST',
      });
      if (res.ok) {
        setSetups((prev) => prev.filter((s) => s.id !== id));
      } else {
        const errData = await res.json().catch(() => ({ detail: res.statusText }));
        Alert.alert('Error', errData.detail || `Error al rechazar (${res.status})`);
      }
    } catch (err) {
      console.error('Failed to reject setup:', err);
      Alert.alert('Error', 'No se pudo conectar al servidor');
    } finally {
      setActionLoading(null);
    }
  };

  const approveAll = () => {
    Alert.alert(
      'APROBAR TODAS',
      `Aprobar ${setups.length} operaciones pendientes?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'SI, APROBAR TODAS',
          onPress: async () => {
            try {
              setActionLoading('approve-all');
              const res = await authFetch(`${API_URL}/api/v1/pending-setups/approve-all`, {
                method: 'POST',
              });
              if (res.ok) {
                setSetups([]);
              } else {
                const detail = await res.text();
                Alert.alert('Error', `No se pudieron aprobar: HTTP ${res.status} ${detail.slice(0, 100)}`);
              }
            } catch (err) {
              console.error('Failed to approve all:', err);
              Alert.alert('Error', 'Fallo de conexión al aprobar todas');
            } finally {
              setActionLoading(null);
            }
          },
        },
      ]
    );
  };

  const rejectAll = () => {
    Alert.alert(
      'RECHAZAR TODAS',
      `Rechazar ${setups.length} operaciones pendientes?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'SI, RECHAZAR TODAS',
          style: 'destructive',
          onPress: async () => {
            try {
              setActionLoading('reject-all');
              const res = await authFetch(`${API_URL}/api/v1/pending-setups/reject-all`, {
                method: 'POST',
              });
              if (res.ok) {
                setSetups([]);
              } else {
                const detail = await res.text();
                Alert.alert('Error', `No se pudieron rechazar: HTTP ${res.status} ${detail.slice(0, 100)}`);
              }
            } catch (err) {
              console.error('Failed to reject all:', err);
              Alert.alert('Error', 'Fallo de conexión al rechazar todas');
            } finally {
              setActionLoading(null);
            }
          },
        },
      ]
    );
  };

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const getPipMultiplier = (instrument: string | null): number => {
    if (!instrument) return 10000;
    return instrument.toUpperCase().includes('JPY') ? 100 : 10000;
  };

  // ── Setup Card ──────────────────────────────────────────────────────────

  const renderSetupCard = ({ item }: { item: PendingSetup }) => {
    const isExpanded = expandedId === item.id;
    const isApproving = actionLoading === `approve-${item.id}`;
    const isRejecting = actionLoading === `reject-${item.id}`;
    const pipMultiplier = getPipMultiplier(item.instrument);
    const stratColor = getStrategyDotColor(item.strategy);
    const confColor = getConfidenceColor(item.confidence);
    const confLabel = getConfidenceLabel(item.confidence);
    const isBuy = item.direction === 'BUY';

    const slPips = (Math.abs(item.entry_price - item.stop_loss) * pipMultiplier).toFixed(1);
    const tpPips = (Math.abs(item.take_profit - item.entry_price) * pipMultiplier).toFixed(1);

    return (
      <HUDCard accentColor={stratColor}>
        {/* Header: Strategy badge + Direction + Confidence */}
        <View style={styles.setupHeader}>
          <View style={styles.setupHeaderLeft}>
            {/* Strategy badge */}
            <View style={styles.strategyBadge}>
              <View style={[styles.strategyDot, { backgroundColor: stratColor, shadowColor: stratColor }]} />
              <Text style={[styles.strategyName, { color: stratColor }]}>
                {item.strategy}
              </Text>
            </View>
            {/* Direction badge */}
            <HUDBadge
              label={isBuy ? '\u25B2 COMPRAR' : '\u25BC VENDER'}
              color={isBuy ? theme.colors.profit : theme.colors.loss}
              small
            />
          </View>
          {/* Confidence badge */}
          <HUDBadge label={`${confLabel} (${item.confidence}%)`} color={confColor} small />
        </View>

        {/* Instrument name */}
        <Text style={styles.setupInstrument}>
          {item.instrument.replace('_', '/')}
        </Text>

        {/* R:R ratio prominent */}
        <View style={styles.rrContainer}>
          <Text style={styles.rrLabel}>R:R</Text>
          <Text style={styles.rrValue}>{(item.risk_reward_ratio || 0).toFixed(1)}</Text>
        </View>

        <HUDDivider />

        {/* Entry/SL/TP grid (3 columns, mono font, with pip distances) */}
        <View style={styles.pricesGrid}>
          <View style={styles.priceCol}>
            <Text style={styles.priceColLabel}>ENTRADA</Text>
            <Text style={styles.priceColValue}>{(item.entry_price || 0).toFixed(5)}</Text>
          </View>
          <View style={styles.priceCol}>
            <Text style={[styles.priceColLabel, { color: theme.colors.neonRed }]}>STOP LOSS</Text>
            <Text style={[styles.priceColValue, { color: theme.colors.neonRed }]}>
              {(item.stop_loss || 0).toFixed(5)}
            </Text>
            <Text style={styles.priceColPips}>{slPips} pips</Text>
          </View>
          <View style={styles.priceCol}>
            <Text style={[styles.priceColLabel, { color: theme.colors.neonGreen }]}>TAKE PROFIT</Text>
            <Text style={[styles.priceColValue, { color: theme.colors.neonGreen }]}>
              {(item.take_profit || 0).toFixed(5)}
            </Text>
            <Text style={styles.priceColPips}>{tpPips} pips</Text>
          </View>
        </View>

        {/* Expandable reasoning */}
        <TouchableOpacity
          style={styles.expandToggle}
          onPress={() => toggleExpand(item.id)}
          activeOpacity={0.7}
        >
          <Text style={styles.expandToggleText}>
            {isExpanded ? '\u25BE Ocultar analisis' : '\u25B8 Ver analisis de la estrategia'}
          </Text>
        </TouchableOpacity>

        {isExpanded && (
          <View style={styles.expandedContent}>
            <HUDSectionTitle title="RAZONAMIENTO" color={theme.colors.cp2077Yellow} />
            <Text style={styles.reasoningText}>{item.reasoning}</Text>

            {item.checklist && item.checklist.length > 0 && (
              <>
                <HUDDivider />
                <HUDSectionTitle title="CHECKLIST" color={theme.colors.cp2077Yellow} />
                {item.checklist.map((step, index) => (
                  <View key={index} style={styles.checklistItem}>
                    <Text style={styles.checklistCheck}>{'\u2713'}</Text>
                    <Text style={styles.checklistText}>{step}</Text>
                  </View>
                ))}
              </>
            )}
          </View>
        )}

        {/* Action buttons: GREEN glow APPROVE + RED outline REJECT */}
        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.rejectBtn]}
            onPress={() => rejectSetup(item.id)}
            disabled={isRejecting || isApproving}
            activeOpacity={0.7}
          >
            {isRejecting ? (
              <ActivityIndicator size="small" color={theme.colors.neonRed} />
            ) : (
              <Text style={styles.rejectBtnText}>RECHAZAR</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.actionBtn, styles.approveBtn]}
            onPress={() => approveSetup(item.id)}
            disabled={isApproving || isRejecting}
            activeOpacity={0.7}
          >
            {isApproving ? (
              <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
            ) : (
              <Text style={styles.approveBtnText}>APROBAR</Text>
            )}
          </TouchableOpacity>
        </View>
      </HUDCard>
    );
  };

  // ── Loading State ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <View style={styles.fullScreen}>
        <HUDHeader title="PENDING OPS // MANUAL" subtitle="TRADE APPROVAL SYSTEM" />
        <LoadingState message="Cargando setups..." />
      </View>
    );
  }

  // ── Error State ───────────────────────────────────────────────────────────

  if (error) {
    return (
      <View style={styles.fullScreen}>
        <HUDHeader title="PENDING OPS // MANUAL" subtitle="TRADE APPROVAL SYSTEM" />
        <ErrorState message={error} onRetry={fetchSetups} />
      </View>
    );
  }

  // ── Main Render ───────────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      {/* HUD Header */}
      <HUDHeader title="PENDING OPS // MANUAL" subtitle="TRADE APPROVAL SYSTEM" />

      {/* Mode indicator + count */}
      <View style={styles.modeRow}>
        <View style={styles.modeIndicator}>
          <View style={styles.modeIndicatorDot} />
          <Text style={styles.modeIndicatorText}>MANUAL ACTIVO</Text>
        </View>
        {setups.length > 0 && (
          <View style={styles.countBadge}>
            <Text style={styles.countBadgeText}>{setups.length}</Text>
          </View>
        )}
      </View>

      {setups.length > 0 ? (
        <>
          <FlatList
            data={setups}
            keyExtractor={(item) => item.id}
            renderItem={renderSetupCard}
            style={styles.list}
            contentContainerStyle={styles.listContent}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
            }
          />

          {/* Bulk actions footer (sticky bottom bar) */}
          <View style={styles.bulkActions}>
            <View style={styles.bulkActionsInner}>
              <TouchableOpacity
                style={[styles.bulkBtn, styles.bulkRejectBtn]}
                onPress={rejectAll}
                disabled={actionLoading === 'reject-all'}
                activeOpacity={0.7}
              >
                {actionLoading === 'reject-all' ? (
                  <ActivityIndicator size="small" color={theme.colors.neonRed} />
                ) : (
                  <Text style={styles.bulkRejectText}>RECHAZAR TODAS</Text>
                )}
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.bulkBtn, styles.bulkApproveBtn]}
                onPress={approveAll}
                disabled={actionLoading === 'approve-all'}
                activeOpacity={0.7}
              >
                {actionLoading === 'approve-all' ? (
                  <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
                ) : (
                  <Text style={styles.bulkApproveText}>APROBAR TODAS</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </>
      ) : (
        <EmptyState
          title="No hay operaciones pendientes"
          subtitle="Cuando Atlas detecte una oportunidad en modo MANUAL, aparecera aqui para tu aprobacion."
          hint="Cambia al modo MANUAL en Configuracion para aprobar operaciones manualmente."
        />
      )}
    </View>
  );
}

// ─── Styles ─────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
  },
  fullScreen: {
    flex: 1,
    backgroundColor: '#f2f2f7',
  },

  // ── Mode Row ───────────────────────────────────────
  modeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    marginBottom: 8,
  },
  modeIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  modeIndicatorDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#007AFF',
  },
  modeIndicatorText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#007AFF',
  },
  countBadge: {
    backgroundColor: '#007AFF',
    borderRadius: 999,
    width: 28,
    height: 28,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countBadgeText: {
    fontSize: 13,
    color: '#ffffff',
    fontWeight: '700',
  },

  // ── List ───────────────────────────────────────────
  list: {
    flex: 1,
  },
  listContent: {
    padding: 16,
  },

  // ── Setup Card ─────────────────────────────────────
  setupHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 4,
  },
  setupHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexWrap: 'wrap',
    flex: 1,
  },
  strategyBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  strategyDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  strategyName: {
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.3,
  },
  setupInstrument: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1d1d1f',
    letterSpacing: -0.3,
    marginBottom: 4,
  },

  // ── R:R ────────────────────────────────────────────
  rrContainer: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 6,
    marginBottom: 4,
  },
  rrLabel: {
    fontSize: 11,
    fontWeight: '500',
    color: '#aeaeb2',
  },
  rrValue: {
    fontSize: 22,
    color: '#007AFF',
    fontWeight: '700',
  },

  // ── Prices Grid ────────────────────────────────────
  pricesGrid: {
    flexDirection: 'row',
    backgroundColor: '#f9f9f9',
    borderRadius: 14,
    padding: 10,
    marginBottom: 8,
  },
  priceCol: {
    flex: 1,
    alignItems: 'center',
  },
  priceColLabel: {
    fontSize: 10,
    fontWeight: '500',
    color: '#aeaeb2',
    marginBottom: 3,
  },
  priceColValue: {
    fontSize: 13,
    fontWeight: '600',
    color: '#1d1d1f',
  },
  priceColPips: {
    fontSize: 10,
    color: '#aeaeb2',
    marginTop: 2,
  },

  // ── Expand Toggle ──────────────────────────────────
  expandToggle: {
    paddingVertical: 4,
    marginBottom: 8,
  },
  expandToggleText: {
    fontSize: 13,
    color: '#007AFF',
    fontWeight: '500',
  },
  expandedContent: {
    backgroundColor: '#f9f9f9',
    borderRadius: 14,
    padding: 12,
    marginBottom: 8,
  },
  reasoningText: {
    fontSize: 13,
    color: '#86868b',
    lineHeight: 20,
  },
  checklistItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginBottom: 4,
  },
  checklistCheck: {
    fontSize: 13,
    color: '#34C759',
  },
  checklistText: {
    fontSize: 13,
    color: '#86868b',
    flex: 1,
    lineHeight: 18,
  },

  // ── Action Buttons ─────────────────────────────────
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  approveBtn: {
    backgroundColor: '#34C759',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
  },
  approveBtnText: {
    fontSize: 14,
    color: '#ffffff',
    fontWeight: '600',
  },
  rejectBtn: {
    backgroundColor: 'rgba(255,59,48,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,59,48,0.2)',
  },
  rejectBtnText: {
    fontSize: 14,
    color: '#FF3B30',
    fontWeight: '600',
  },

  // ── Bulk Actions (sticky bottom) ───────────────────
  bulkActions: {
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.04)',
    backgroundColor: '#ffffff',
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  bulkActionsInner: {
    flexDirection: 'row',
    gap: 10,
  },
  bulkBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bulkApproveBtn: {
    backgroundColor: '#34C759',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.08,
    shadowRadius: 12,
    elevation: 4,
  },
  bulkApproveText: {
    fontSize: 13,
    color: '#ffffff',
    fontWeight: '600',
  },
  bulkRejectBtn: {
    backgroundColor: 'rgba(255,59,48,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(255,59,48,0.2)',
  },
  bulkRejectText: {
    fontSize: 13,
    color: '#FF3B30',
    fontWeight: '600',
  },
});
