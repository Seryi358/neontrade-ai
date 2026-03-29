/**
 * NeonTrade AI - Dashboard Screen
 * Main dashboard showing account status, active trades, and market overview.
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { API_URL, authFetch, wsManager } from '../services/api';

// Types
interface AccountData {
  balance: number;
  equity: number;
  unrealized_pnl: number;
  open_trade_count: number;
  currency: string;
}

interface RiskStatus {
  current_drawdown: number;
  peak_balance: number;
  current_balance: number;
  recovery_pct_needed: number;
  loss_dollars: number;
  dd_alert_level: string | null;
  recovery_table: [number, number][];
  max_total_risk: number;
  adjusted_risk_day: number;
}

interface Position {
  instrument: string;
  direction: string;
  entry: number;
  current_sl: number;
  tp1: number;
  phase: string;
  strategy?: string;
}

interface DailyActivity {
  scans_completed: number;
  setups_found: number;
  setups_executed: number;
  setups_skipped_ai: number;
  errors: number;
}

interface EngineStatus {
  running: boolean;
  mode: string;
  broker: string;
  open_positions: number;
  pending_setups: number;
  total_risk: number;
  watchlist_count: number;
  positions: Record<string, Position>;
  daily_activity?: DailyActivity;
}

export default function DashboardScreen() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [maxTotalRisk, setMaxTotalRisk] = useState<number | null>(null);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setError(null);
      const [accountRes, statusRes, riskRes, riskStatusRes] = await Promise.all([
        authFetch(`${API_URL}/api/v1/account`).catch(() => null),
        authFetch(`${API_URL}/api/v1/status`).catch(() => null),
        authFetch(`${API_URL}/api/v1/risk-config`).catch(() => null),
        authFetch(`${API_URL}/api/v1/risk-status`).catch(() => null),
      ]);
      if (statusRes?.ok) {
        const statusData = await statusRes.json();
        setStatus(statusData);
        // Show broker connection error if engine isn't running
        if (!statusData.running && statusData.startup_error) {
          setError(`Broker: ${statusData.startup_error.slice(0, 80)}`);
        }
      }
      if (accountRes?.ok) {
        setAccount(await accountRes.json());
      } else if (!accountRes) {
        setError('No se pudo conectar al servidor');
      }
      if (riskRes?.ok) {
        const riskData = await riskRes.json();
        if (riskData?.max_total_risk != null) {
          setMaxTotalRisk(riskData.max_total_risk);
        }
      }
      if (riskStatusRes?.ok) {
        const rsData = await riskStatusRes.json();
        if (rsData && !rsData.error) {
          setRiskStatus(rsData);
        }
      }
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Error al cargar datos');
    }
  };

  useEffect(() => {
    // Initial fetch
    fetchData();

    // Real-time updates via WebSocket
    wsManager.connect();
    const unsubStatus = wsManager.on('engine_status', (data: any) => {
      if (data) {
        setStatus(prev => ({ ...prev, ...data }));
      }
    });
    const unsubTrade = wsManager.on('trade_executed', () => fetchData());
    const unsubClose = wsManager.on('trade_closed', () => fetchData());

    // Fallback polling every 15s (less aggressive than 5s)
    const interval = setInterval(fetchData, 15000);

    return () => {
      clearInterval(interval);
      unsubStatus();
      unsubTrade();
      unsubClose();
    };
  }, []);

  const onRefresh = async () => {
    setRefreshing(true);
    await fetchData();
    setRefreshing(false);
  };

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>NEONTRADE</Text>
        <Text style={styles.subtitle}>AI TRADING SYSTEM</Text>
        <View style={[styles.statusBadge, status?.running ? styles.online : styles.offline]}>
          <Text style={styles.statusText}>
            {status?.running ? '● ONLINE' : '○ OFFLINE'}
          </Text>
        </View>
      </View>

      {error && <Text style={{color: theme.colors.neonRed, fontFamily: theme.fonts.mono, fontSize: 11, textAlign: 'center', padding: 8, letterSpacing: 2}}>{error}</Text>}

      {/* Account Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ACCOUNT</Text>
        <Text style={styles.balanceAmount}>
          {account ? `$${account.balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}` : '---'}
        </Text>
        <View style={styles.row}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>P&L</Text>
            <Text style={[
              styles.statValue,
              (account?.unrealized_pnl ?? 0) >= 0 ? styles.profit : styles.loss,
            ]}>
              {account ? `$${account.unrealized_pnl.toFixed(2)}` : '---'}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>TRADES</Text>
            <Text style={styles.statValue}>
              {account?.open_trade_count ?? 0}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>RISK</Text>
            <Text style={styles.statValue}>
              {status ? `${(status.total_risk * 100).toFixed(1)}%` : '0%'}
            </Text>
          </View>
        </View>
      </View>

      {/* Drawdown Alert Banner */}
      {riskStatus?.dd_alert_level && (
        <View style={[
          styles.card,
          {
            borderColor: riskStatus.dd_alert_level === 'critical'
              ? theme.colors.neonRed
              : riskStatus.dd_alert_level === 'high'
                ? theme.colors.neonOrange
                : theme.colors.neonYellow,
            backgroundColor: riskStatus.dd_alert_level === 'critical'
              ? 'rgba(218, 68, 83, 0.1)'
              : riskStatus.dd_alert_level === 'high'
                ? 'rgba(255, 107, 53, 0.1)'
                : 'rgba(255, 184, 0, 0.08)',
          },
        ]}>
          <Text style={[
            styles.cardTitle,
            {
              color: riskStatus.dd_alert_level === 'critical'
                ? theme.colors.neonRed
                : riskStatus.dd_alert_level === 'high'
                  ? theme.colors.neonOrange
                  : theme.colors.neonYellow,
            },
          ]}>
            {riskStatus.dd_alert_level === 'critical' ? 'DRAWDOWN CRITICO' :
             riskStatus.dd_alert_level === 'high' ? 'DRAWDOWN ALTO' : 'DRAWDOWN ALERTA'}
          </Text>
          <Text style={[styles.statValue, { textAlign: 'center', fontSize: 14 }]}>
            DD actual: {riskStatus.current_drawdown.toFixed(2)}% | Recuperar: {riskStatus.recovery_pct_needed.toFixed(2)}%
          </Text>
          <Text style={[styles.emptyText, { marginTop: 2 }]}>
            {riskStatus.dd_alert_level === 'critical'
              ? 'Reducir riesgo inmediatamente. Considerar pausa.'
              : riskStatus.dd_alert_level === 'high'
                ? 'Riesgo elevado. Revisa tu gestión monetaria.'
                : 'Monitorea el drawdown de cerca.'}
          </Text>
        </View>
      )}

      {/* Recovery Math Card — only show when there's drawdown */}
      {riskStatus && riskStatus.current_drawdown > 0 && (
        <View style={[styles.card, { borderColor: theme.colors.neonYellow }]}>
          <Text style={[styles.cardTitle, { color: theme.colors.neonYellow }]}>
            RECOVERY MATH
          </Text>
          <View style={styles.row}>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>DD ACTUAL</Text>
              <Text style={[styles.statValue, styles.loss]}>
                -{riskStatus.current_drawdown.toFixed(2)}%
              </Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>RECUPERAR</Text>
              <Text style={[styles.statValue, { color: theme.colors.neonYellow }]}>
                +{riskStatus.recovery_pct_needed.toFixed(2)}%
              </Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>PERDIDO</Text>
              <Text style={[styles.statValue, styles.loss]}>
                -${riskStatus.loss_dollars.toFixed(0)}
              </Text>
            </View>
          </View>

          {/* Recovery reference table */}
          <View style={recoveryStyles.tableContainer}>
            <View style={recoveryStyles.tableHeader}>
              <Text style={recoveryStyles.tableHeaderText}>PERDIDA</Text>
              <Text style={recoveryStyles.tableHeaderText}>PARA RECUPERAR</Text>
            </View>
            {(riskStatus.recovery_table || []).map(([loss, recovery]) => (
              <View
                key={loss}
                style={[
                  recoveryStyles.tableRow,
                  riskStatus.current_drawdown >= loss && riskStatus.current_drawdown < (loss + 5)
                    ? recoveryStyles.tableRowActive
                    : null,
                ]}
              >
                <Text style={[
                  recoveryStyles.tableCell,
                  styles.loss,
                ]}>
                  -{loss}%
                </Text>
                <Text style={[
                  recoveryStyles.tableCell,
                  { color: recovery >= 50 ? theme.colors.neonRed : theme.colors.neonYellow },
                ]}>
                  +{recovery.toFixed(1)}%
                </Text>
              </View>
            ))}
          </View>

          <Text style={[styles.emptyText, { marginTop: 4, fontSize: 10 }]}>
            Alex: "La conservación del capital es lo primero"
          </Text>
        </View>
      )}

      {/* Active Positions */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ACTIVE POSITIONS</Text>
        {status?.positions && Object.entries(status.positions).length > 0 ? (
          Object.entries(status.positions).map(([id, pos]) => (
            <View key={id} style={styles.positionRow}>
              <View style={styles.positionLeft}>
                <Text style={styles.positionPair}>{pos.instrument}</Text>
                <Text style={[
                  styles.positionDirection,
                  pos.direction === 'BUY' ? styles.profit : styles.loss,
                ]}>
                  {pos.direction}
                </Text>
              </View>
              <View style={styles.positionRight}>
                <Text style={styles.positionEntry}>@ {pos.entry.toFixed(5)}</Text>
                <Text style={styles.positionPhase}>{pos.phase.toUpperCase()}</Text>
              </View>
            </View>
          ))
        ) : (
          <Text style={styles.emptyText}>No active positions</Text>
        )}
      </View>

      {/* Engine Info */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>MOTOR</Text>
        <View style={styles.row}>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>WATCHLIST</Text>
            <Text style={styles.statValue}>{status?.watchlist_count ?? 0}</Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>RIESGO MAX</Text>
            <Text style={styles.statValue}>
              {maxTotalRisk != null ? `${(maxTotalRisk * 100).toFixed(1)}%` : '---'}
            </Text>
          </View>
          <View style={styles.stat}>
            <Text style={styles.statLabel}>MODO</Text>
            <Text style={[
              styles.statValue,
              { color: (status?.mode === 'MANUAL') ? theme.colors.neonCyan : theme.colors.neonGreen }
            ]}>
              {status?.mode ?? 'AUTO'}
            </Text>
          </View>
        </View>
      </View>

      {/* Pending Setups (Manual Mode) */}
      {(status?.pending_setups ?? 0) > 0 && (
        <View style={[styles.card, { borderColor: theme.colors.neonCyan }]}>
          <Text style={[styles.cardTitle, { color: theme.colors.neonCyan }]}>
            OPERACIONES PENDIENTES
          </Text>
          <Text style={[styles.balanceAmount, { color: theme.colors.neonCyan, fontSize: 22 }]}>
            {status?.pending_setups} configuraciones esperando aprobación
          </Text>
          <Text style={styles.emptyText}>
            Ve a la pestaña MANUAL para aprobar o rechazar
          </Text>
        </View>
      )}

      {/* Daily Activity (Proof of Life) */}
      {status?.daily_activity && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>ACTIVIDAD HOY</Text>
          <View style={styles.row}>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>SCANS</Text>
              <Text style={styles.statValue}>{status.daily_activity.scans_completed}</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>SETUPS</Text>
              <Text style={styles.statValue}>{status.daily_activity.setups_found}</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>EJECUTADOS</Text>
              <Text style={[styles.statValue, { color: theme.colors.neonGreen }]}>
                {status.daily_activity.setups_executed}
              </Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>AI REJECT</Text>
              <Text style={styles.statValue}>{status.daily_activity.setups_skipped_ai}</Text>
            </View>
          </View>
          {status.daily_activity.scans_completed > 0 && (
            <Text style={[styles.emptyText, { color: theme.colors.neonGreen, marginTop: 4 }]}>
              Motor activo y escaneando
            </Text>
          )}
        </View>
      )}

      {/* Broker Info */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>BROKER</Text>
        <Text style={[styles.statValue, { textAlign: 'center' }]}>
          {(status?.broker ?? 'capital').toUpperCase()}
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
    padding: theme.spacing.md,
  },
  header: {
    alignItems: 'center',
    paddingVertical: theme.spacing.xl,
  },
  title: {
    fontFamily: theme.fonts.heading,
    fontSize: 32,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 8,
    textTransform: 'uppercase',
    textShadowColor: theme.colors.cp2077YellowGlow,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 15,
  },
  subtitle: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.neonCyan,
    letterSpacing: 6,
    textTransform: 'uppercase',
    marginTop: 2,
  },
  statusBadge: {
    marginTop: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.xs,
    borderRadius: theme.borderRadius.round,
    borderWidth: 1,
  },
  online: {
    borderColor: theme.colors.neonGreen,
    backgroundColor: 'rgba(57, 255, 20, 0.1)',
  },
  offline: {
    borderColor: theme.colors.neonRed,
    backgroundColor: 'rgba(218, 68, 83, 0.1)',
  },
  statusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
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
    fontSize: 12,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 4,
    textTransform: 'uppercase',
    marginBottom: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
    paddingBottom: 4,
  },
  balanceAmount: {
    fontFamily: theme.fonts.mono,
    fontSize: 28,
    color: theme.colors.textWhite,
    marginBottom: theme.spacing.md,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  stat: {
    alignItems: 'center',
    flex: 1,
  },
  statLabel: {
    fontFamily: theme.fonts.mono,
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
  profit: {
    color: theme.colors.profit,
  },
  loss: {
    color: theme.colors.loss,
  },
  positionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: theme.spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  positionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  positionPair: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.textWhite,
  },
  positionDirection: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    letterSpacing: 1,
  },
  positionRight: {
    alignItems: 'flex-end',
  },
  positionEntry: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  positionPhase: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 1,
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.textMuted,
    textAlign: 'center',
    paddingVertical: theme.spacing.lg,
  },
});

const recoveryStyles = StyleSheet.create({
  tableContainer: {
    marginTop: theme.spacing.md,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    paddingTop: theme.spacing.sm,
  },
  tableHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.md,
    marginBottom: 4,
  },
  tableHeaderText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 2,
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 3,
  },
  tableRowActive: {
    backgroundColor: 'rgba(255, 184, 0, 0.12)',
    borderRadius: 4,
  },
  tableCell: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
});
