/**
 * NeonTrade AI - Manual Mode Screen
 * Shows pending trade setups awaiting user approval.
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
import { theme } from '../theme/cyberpunk';
import { API_URL } from '../services/api';

// Types
interface PendingSetup {
  id: string;
  strategy_color: string;
  strategy_name: string;
  instrument: string;
  direction: 'BUY' | 'SELL';
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  sl_distance_pips: number;
  tp_distance_pips: number;
  rr_ratio: number;
  confidence: 'ALTA' | 'MEDIA' | 'BAJA';
  reasoning: string;
  checklist: string[];
  created_at: string;
}

const getStrategyDotColor = (color: string): string => {
  switch (color?.toUpperCase()) {
    case 'BLUE': return '#4488ff';
    case 'RED': return '#ff2e63';
    case 'PINK': return '#eb4eca';
    case 'WHITE': return '#f0e6ff';
    case 'BLACK': return '#555555';
    case 'GREEN': return '#00ff88';
    default: return theme.colors.textMuted;
  }
};

const getConfidenceColor = (confidence: string) => {
  switch (confidence) {
    case 'ALTA': return theme.colors.neonGreen;
    case 'MEDIA': return theme.colors.neonYellow;
    case 'BAJA': return theme.colors.neonOrange;
    default: return theme.colors.textMuted;
  }
};

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
      const res = await fetch(`${API_URL}/api/v1/pending-setups`);
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
    const interval = setInterval(fetchSetups, 3000);
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
      const res = await fetch(`${API_URL}/api/v1/pending-setups/${id}/approve`, {
        method: 'POST',
      });
      if (res.ok) {
        setSetups((prev) => prev.filter((s) => s.id !== id));
      }
    } catch (err) {
      console.error('Failed to approve setup:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const rejectSetup = async (id: string) => {
    try {
      setActionLoading(`reject-${id}`);
      const res = await fetch(`${API_URL}/api/v1/pending-setups/${id}/reject`, {
        method: 'POST',
      });
      if (res.ok) {
        setSetups((prev) => prev.filter((s) => s.id !== id));
      }
    } catch (err) {
      console.error('Failed to reject setup:', err);
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
              const res = await fetch(`${API_URL}/api/v1/pending-setups/approve-all`, {
                method: 'POST',
              });
              if (res.ok) {
                setSetups([]);
              }
            } catch (err) {
              console.error('Failed to approve all:', err);
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
              // Reject each setup individually
              await Promise.all(
                setups.map((s) =>
                  fetch(`${API_URL}/api/v1/pending-setups/${s.id}/reject`, {
                    method: 'POST',
                  })
                )
              );
              setSetups([]);
            } catch (err) {
              console.error('Failed to reject all:', err);
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

  const renderSetupCard = ({ item }: { item: PendingSetup }) => {
    const isExpanded = expandedId === item.id;
    const isApproving = actionLoading === `approve-${item.id}`;
    const isRejecting = actionLoading === `reject-${item.id}`;

    return (
      <View style={styles.setupCard}>
        {/* Strategy badge + instrument */}
        <View style={styles.setupHeader}>
          <View style={styles.setupHeaderLeft}>
            <View style={styles.strategyBadge}>
              <View style={[styles.strategyDot, { backgroundColor: getStrategyDotColor(item.strategy_color) }]} />
              <Text style={[styles.strategyName, { color: getStrategyDotColor(item.strategy_color) }]}>
                {item.strategy_name}
              </Text>
            </View>
            <Text style={styles.setupInstrument}>
              {item.instrument.replace('_', '/')}
            </Text>
          </View>
          <View style={[
            styles.confidenceBadge,
            { borderColor: getConfidenceColor(item.confidence) },
          ]}>
            <Text style={[
              styles.confidenceText,
              { color: getConfidenceColor(item.confidence) },
            ]}>
              {item.confidence}
            </Text>
          </View>
        </View>

        {/* Direction */}
        <View style={styles.directionRow}>
          <Text style={[
            styles.directionText,
            item.direction === 'BUY' ? styles.profit : styles.loss,
          ]}>
            {item.direction === 'BUY' ? '▲ COMPRAR' : '▼ VENDER'}
          </Text>
          <Text style={styles.rrText}>R:R {item.rr_ratio.toFixed(1)}</Text>
        </View>

        {/* Prices */}
        <View style={styles.pricesContainer}>
          <View style={styles.priceRow}>
            <Text style={styles.priceLabel}>ENTRADA</Text>
            <Text style={styles.priceValue}>{item.entry_price.toFixed(5)}</Text>
          </View>
          <View style={styles.priceRow}>
            <Text style={styles.priceLabel}>STOP LOSS</Text>
            <Text style={[styles.priceValue, styles.loss]}>
              {item.stop_loss.toFixed(5)}
              <Text style={styles.priceDistance}> ({item.sl_distance_pips.toFixed(1)} pips)</Text>
            </Text>
          </View>
          <View style={styles.priceRow}>
            <Text style={styles.priceLabel}>TAKE PROFIT</Text>
            <Text style={[styles.priceValue, styles.profit]}>
              {item.take_profit.toFixed(5)}
              <Text style={styles.priceDistance}> ({item.tp_distance_pips.toFixed(1)} pips)</Text>
            </Text>
          </View>
        </View>

        {/* Expandable reasoning */}
        <TouchableOpacity
          style={styles.expandToggle}
          onPress={() => toggleExpand(item.id)}
        >
          <Text style={styles.expandToggleText}>
            {isExpanded ? '▾ Ocultar analisis' : '▸ Ver analisis de la estrategia'}
          </Text>
        </TouchableOpacity>

        {isExpanded && (
          <View style={styles.expandedContent}>
            <Text style={styles.reasoningTitle}>RAZONAMIENTO</Text>
            <Text style={styles.reasoningText}>{item.reasoning}</Text>

            {item.checklist && item.checklist.length > 0 && (
              <>
                <Text style={styles.checklistTitle}>CHECKLIST</Text>
                {item.checklist.map((step, index) => (
                  <View key={index} style={styles.checklistItem}>
                    <Text style={styles.checklistCheck}>✓</Text>
                    <Text style={styles.checklistText}>{step}</Text>
                  </View>
                ))}
              </>
            )}
          </View>
        )}

        {/* Action buttons */}
        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.actionBtn, styles.rejectBtn]}
            onPress={() => rejectSetup(item.id)}
            disabled={isRejecting || isApproving}
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
          >
            {isApproving ? (
              <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
            ) : (
              <Text style={styles.approveBtnText}>APROBAR</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.neonPink} />
        <Text style={styles.loadingText}>Cargando setups...</Text>
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <Text style={styles.errorIcon}>⚠</Text>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity style={styles.retryBtn} onPress={fetchSetups}>
          <Text style={styles.retryBtnText}>REINTENTAR</Text>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {/* Header */}
      <View style={styles.headerRow}>
        <View>
          <Text style={styles.header}>MODO MANUAL</Text>
          <Text style={styles.subheader}>Setups pendientes de aprobacion</Text>
        </View>
        {setups.length > 0 && (
          <View style={styles.countBadge}>
            <Text style={styles.countBadgeText}>{setups.length}</Text>
          </View>
        )}
      </View>

      {/* Mode indicator */}
      <View style={styles.modeIndicator}>
        <View style={styles.modeIndicatorDot} />
        <Text style={styles.modeIndicatorText}>MANUAL ACTIVO</Text>
      </View>

      {setups.length > 0 ? (
        <>
          <FlatList
            data={setups}
            keyExtractor={(item) => item.id}
            renderItem={renderSetupCard}
            style={styles.list}
            refreshControl={
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
            }
          />

          {/* Bulk actions */}
          <View style={styles.bulkActions}>
            <TouchableOpacity
              style={[styles.bulkBtn, styles.bulkRejectBtn]}
              onPress={rejectAll}
              disabled={actionLoading === 'reject-all'}
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
            >
              {actionLoading === 'approve-all' ? (
                <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
              ) : (
                <Text style={styles.bulkApproveText}>APROBAR TODAS</Text>
              )}
            </TouchableOpacity>
          </View>
        </>
      ) : (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyIcon}>◇</Text>
          <Text style={styles.emptyText}>
            No hay operaciones pendientes
          </Text>
          <Text style={styles.emptySubtext}>
            Cuando NeonTrade detecte una oportunidad en modo MANUAL, aparecera aqui para tu aprobacion.
          </Text>
          <Text style={[styles.emptySubtext, { marginTop: 8, color: theme.colors.neonCyan }]}>
            Cambia al modo MANUAL en Configuracion para aprobar operaciones manualmente.
          </Text>
        </View>
      )}
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
  // Header
  headerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: theme.spacing.lg,
  },
  header: {
    fontFamily: theme.fonts.mono,
    fontSize: 20,
    color: theme.colors.neonCyan,
    letterSpacing: 4,
  },
  subheader: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  countBadge: {
    backgroundColor: theme.colors.neonPink,
    borderRadius: theme.borderRadius.round,
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  countBadgeText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.textWhite,
    fontWeight: 'bold',
  },
  modeIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: theme.spacing.sm,
    marginBottom: theme.spacing.md,
  },
  modeIndicatorDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: theme.colors.neonCyan,
  },
  modeIndicatorText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.neonCyan,
    letterSpacing: 2,
  },
  list: {
    flex: 1,
  },
  // Setup card
  setupCard: {
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
  },
  setupHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: theme.spacing.sm,
  },
  setupHeaderLeft: {
    flex: 1,
  },
  strategyBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 4,
  },
  strategyDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  strategyName: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    letterSpacing: 2,
  },
  setupInstrument: {
    fontFamily: theme.fonts.mono,
    fontSize: 22,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
  confidenceBadge: {
    borderWidth: 1,
    borderRadius: theme.borderRadius.sm,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  confidenceText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  // Direction
  directionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  directionText: {
    fontFamily: theme.fonts.mono,
    fontSize: 16,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  rrText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.neonCyan,
    letterSpacing: 1,
  },
  profit: {
    color: theme.colors.profit,
  },
  loss: {
    color: theme.colors.loss,
  },
  // Prices
  pricesContainer: {
    backgroundColor: theme.colors.backgroundDark,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  priceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  priceLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  priceValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.textWhite,
  },
  priceDistance: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
  },
  // Expand toggle
  expandToggle: {
    paddingVertical: theme.spacing.xs,
    marginBottom: theme.spacing.sm,
  },
  expandToggleText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonPink,
    letterSpacing: 1,
  },
  expandedContent: {
    backgroundColor: theme.colors.backgroundDark,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    marginBottom: theme.spacing.sm,
  },
  reasoningTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.neonPink,
    letterSpacing: 2,
    marginBottom: 6,
  },
  reasoningText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    lineHeight: 18,
    marginBottom: theme.spacing.sm,
  },
  checklistTitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.neonPink,
    letterSpacing: 2,
    marginBottom: 6,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.sm,
  },
  checklistItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    marginBottom: 4,
  },
  checklistCheck: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonGreen,
  },
  checklistText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textSecondary,
    flex: 1,
    lineHeight: 16,
  },
  // Action buttons
  actionRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: theme.spacing.sm + 2,
    borderRadius: theme.borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  approveBtn: {
    backgroundColor: theme.colors.neonGreen,
    shadowColor: theme.colors.neonGreen,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 8,
    elevation: 8,
  },
  approveBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.backgroundDark,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  rejectBtn: {
    backgroundColor: 'rgba(255, 7, 58, 0.15)',
    borderWidth: 1,
    borderColor: theme.colors.neonRed,
  },
  rejectBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.neonRed,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  // Bulk actions
  bulkActions: {
    flexDirection: 'row',
    gap: 10,
    paddingVertical: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  bulkBtn: {
    flex: 1,
    paddingVertical: theme.spacing.sm + 2,
    borderRadius: theme.borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bulkApproveBtn: {
    backgroundColor: theme.colors.neonGreen,
    shadowColor: theme.colors.neonGreen,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 6,
    elevation: 6,
  },
  bulkApproveText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.backgroundDark,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  bulkRejectBtn: {
    backgroundColor: 'rgba(255, 7, 58, 0.15)',
    borderWidth: 1,
    borderColor: theme.colors.neonRed,
  },
  bulkRejectText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonRed,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  // Empty state
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: theme.spacing.xxl,
  },
  emptyIcon: {
    fontSize: 56,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.md,
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.textMuted,
    textAlign: 'center',
  },
  emptySubtext: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    opacity: 0.6,
  },
  emptyPulse: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: theme.spacing.lg,
  },
  emptyPulseText: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.neonPink,
    letterSpacing: 2,
  },
  // Loading / Error
  loadingText: {
    fontFamily: theme.fonts.mono,
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
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.neonRed,
    textAlign: 'center',
  },
  retryBtn: {
    marginTop: theme.spacing.md,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.sm,
    borderWidth: 1,
    borderColor: theme.colors.neonPink,
    borderRadius: theme.borderRadius.md,
  },
  retryBtnText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.neonPink,
    letterSpacing: 2,
  },
});
