/**
 * NeonTrade AI - Dashboard Screen (HQ)
 * Command Center HUD with account overview, engine status,
 * risk monitoring, active positions, and daily activity.
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

/** Safe toFixed — handles null/undefined/NaN without crashing */
const safe = (v: any, decimals = 2): string => {
  if (v == null || isNaN(v)) return '---';
  return Number(v).toFixed(decimals);
};
import { API_URL, authFetch, wsManager } from '../services/api';
import {
  HUDCard,
  HUDHeader,
  HUDStatRow,
  HUDDivider,
  HUDBadge,
  HUDProgressBar,
  HUDSectionTitle,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';

// ── Types ───────────────────────────────────────────────

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
  unrealized_pnl?: number;
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
  startup_error?: string;
}

// ── Dashboard Screen ────────────────────────────────────

export default function DashboardScreen() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [maxTotalRisk, setMaxTotalRisk] = useState<number | null>(null);
  const [riskStatus, setRiskStatus] = useState<RiskStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();

    wsManager.connect();
    const unsubStatus = wsManager.on('engine_status', (data: any) => {
      if (data) {
        setStatus(prev => prev ? { ...prev, ...data } : data);
      }
    });
    const unsubTrade = wsManager.on('trade_executed', () => fetchData());
    const unsubClose = wsManager.on('trade_closed', () => fetchData());

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

  // Helpers
  const formatCurrency = (val: number) =>
    `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const pnlColor = (val: number) =>
    val > 0 ? theme.colors.profit : val < 0 ? theme.colors.loss : theme.colors.textSecondary;

  const pnlArrow = (val: number) =>
    val > 0 ? '\u25B2' : val < 0 ? '\u25BC' : '\u25CF';

  const ddSeverityColor = (level: string | null) => {
    if (level === 'critical') return theme.colors.neonRed;
    if (level === 'high') return theme.colors.neonOrange;
    if (level === 'moderate') return theme.colors.neonYellow;
    return theme.colors.textMuted;
  };

  const riskColor = (pct: number) => {
    if (pct >= 4) return theme.colors.neonRed;
    if (pct >= 3) return theme.colors.neonOrange;
    if (pct >= 2) return theme.colors.neonYellow;
    return theme.colors.neonGreen;
  };

  if (loading && !account && !status) {
    return (
      <View style={styles.container}>
        <LoadingState message="CONNECTING TO HQ..." />
      </View>
    );
  }

  const totalRiskPct = status ? status.total_risk * 100 : 0;
  const maxRiskPct = maxTotalRisk != null ? maxTotalRisk * 100 : 6;
  const positions = status?.positions ? Object.entries(status.positions) : [];
  const activity = status?.daily_activity;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor={theme.colors.cp2077Yellow}
        />
      }
    >
      {/* ── HUD Header ─────────────────────────────────── */}
      <HUDHeader title="COMMAND CENTER // HQ" subtitle={
        `${new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`
      } />

      {/* Error banner */}
      {error && (
        <ErrorState message={error} onRetry={fetchData} />
      )}

      {/* ── Account Overview ───────────────────────────── */}
      <HUDCard>
        <HUDSectionTitle title="ACCOUNT" icon="\u25C8" />

        {/* Balance - large cyan */}
        <Text style={styles.balanceAmount}>
          {account ? formatCurrency(account.balance) : '---'}
        </Text>

        <HUDDivider />

        <HUDStatRow
          label="EQUITY"
          value={account ? formatCurrency(account.equity) : '---'}
          valueColor={theme.colors.textSecondary}
        />
        <HUDStatRow
          label="UNREALIZED P&L"
          value={
            account
              ? `${pnlArrow(account.unrealized_pnl)} ${formatCurrency(Math.abs(account.unrealized_pnl))}`
              : '---'
          }
          valueColor={account ? pnlColor(account.unrealized_pnl) : theme.colors.textMuted}
        />
        <HUDStatRow
          label="AVAILABLE MARGIN"
          value={account ? formatCurrency(account.equity - (account.balance - account.equity)) : '---'}
          valueColor={theme.colors.neonCyan}
        />
      </HUDCard>

      {/* ── Engine Status Row ──────────────────────────── */}
      <HUDCard>
        <HUDSectionTitle title="ENGINE STATUS" icon="\u25C6" />
        <View style={styles.engineRow}>
          <HUDBadge
            label={status?.mode ?? 'AUTO'}
            color={status?.mode === 'MANUAL' ? theme.colors.neonCyan : theme.colors.neonGreen}
          />
          <View style={styles.statusDot}>
            <View
              style={[
                styles.dot,
                { backgroundColor: status?.running ? theme.colors.neonGreen : theme.colors.neonRed },
              ]}
            />
            <Text style={[
              styles.statusLabel,
              { color: status?.running ? theme.colors.neonGreen : theme.colors.neonRed },
            ]}>
              {status?.running ? 'CONNECTED' : 'OFFLINE'}
            </Text>
          </View>
          <View style={styles.connectionQuality}>
            <Text style={styles.connectionBars}>
              {status?.running ? '\u2581\u2582\u2583\u2584' : '\u2581\u2581\u2581\u2581'}
            </Text>
          </View>
        </View>
      </HUDCard>

      {/* ── Risk Monitor ───────────────────────────────── */}
      <HUDCard
        accentColor={riskColor(totalRiskPct)}
        borderColor={
          riskStatus?.dd_alert_level === 'critical'
            ? theme.colors.neonRed
            : undefined
        }
        style={
          riskStatus?.dd_alert_level === 'critical'
            ? styles.pulseBorder
            : undefined
        }
      >
        <HUDSectionTitle
          title="RISK MONITOR"
          icon="!"
          color={riskColor(totalRiskPct)}
        />

        <HUDProgressBar
          label="CURRENT RISK"
          value={(totalRiskPct / maxRiskPct) * 100}
          maxLabel={`${maxRiskPct.toFixed(1)}% MAX`}
          color={riskColor(totalRiskPct)}
          showValue
        />
        <Text style={styles.riskActual}>
          {totalRiskPct.toFixed(1)}% DEPLOYED
        </Text>

        <HUDDivider />

        {riskStatus && (
          <>
            <HUDStatRow
              label="DRAWDOWN"
              value={`-${safe(riskStatus.current_drawdown)}%`}
              valueColor={ddSeverityColor(riskStatus.dd_alert_level)}
            />
            {riskStatus.dd_alert_level && (
              <HUDBadge
                label={
                  riskStatus.dd_alert_level === 'critical'
                    ? 'DD CRITICO'
                    : riskStatus.dd_alert_level === 'high'
                      ? 'DD ALTO'
                      : 'DD ALERTA'
                }
                color={ddSeverityColor(riskStatus.dd_alert_level)}
                small
              />
            )}
            <HUDStatRow
              label="MAX RISK / DIA"
              value={maxTotalRisk != null ? `${safe(maxRiskPct, 1)}%` : '---'}
              valueColor={theme.colors.textMuted}
            />
          </>
        )}
      </HUDCard>

      {/* ── Active Positions ───────────────────────────── */}
      <HUDCard>
        <HUDSectionTitle
          title={`ACTIVE POSITIONS (${positions.length})`}
          icon="\u25A3"
        />

        {positions.length > 0 ? (
          positions.map(([id, pos]) => (
            <View key={id} style={styles.positionRow}>
              <View style={styles.positionLeft}>
                <Text style={styles.positionPair}>{pos.instrument}</Text>
                <HUDBadge
                  label={pos.direction}
                  color={pos.direction === 'BUY' ? theme.colors.profit : theme.colors.loss}
                  small
                />
              </View>
              <View style={styles.positionRight}>
                <Text style={[
                  styles.positionPnl,
                  {
                    color: pos.unrealized_pnl != null
                      ? pnlColor(pos.unrealized_pnl)
                      : theme.colors.textMuted,
                  },
                ]}>
                  {pos.unrealized_pnl != null
                    ? `${pos.unrealized_pnl >= 0 ? '+' : ''}${safe(pos.unrealized_pnl)}`
                    : `@ ${safe(pos.entry, 5)}`}
                </Text>
                <Text style={styles.positionPhase}>{pos.phase.toUpperCase()}</Text>
              </View>
            </View>
          ))
        ) : (
          <Text style={styles.emptyText}>NO ACTIVE POSITIONS</Text>
        )}
      </HUDCard>

      {/* ── Daily Activity Grid ────────────────────────── */}
      {activity && (
        <HUDCard>
          <HUDSectionTitle title="DAILY ACTIVITY" icon="\u25C7" />
          <View style={styles.activityGrid}>
            <View style={styles.activityCell}>
              <Text style={styles.activityValue}>{activity.scans_completed}</Text>
              <Text style={styles.activityLabel}>SCANS</Text>
            </View>
            <View style={styles.activityCell}>
              <Text style={styles.activityValue}>{activity.setups_found}</Text>
              <Text style={styles.activityLabel}>SETUPS</Text>
            </View>
            <View style={styles.activityCell}>
              <Text style={[styles.activityValue, { color: theme.colors.neonGreen }]}>
                {activity.setups_executed}
              </Text>
              <Text style={styles.activityLabel}>EXECUTED</Text>
            </View>
            <View style={styles.activityCell}>
              <Text style={[styles.activityValue, { color: theme.colors.neonRed }]}>
                {activity.setups_skipped_ai}
              </Text>
              <Text style={styles.activityLabel}>AI REJECTS</Text>
            </View>
          </View>
          {activity.scans_completed > 0 && (
            <Text style={styles.engineActive}>ENGINE ACTIVE // SCANNING</Text>
          )}
        </HUDCard>
      )}

      {/* ── Drawdown Recovery Table ────────────────────── */}
      {riskStatus && riskStatus.current_drawdown > 0 && (
        <HUDCard accentColor={theme.colors.neonYellow}>
          <HUDSectionTitle title="RECOVERY MATH" icon="!" color={theme.colors.neonYellow} />

          <View style={styles.recoveryHeader}>
            <HUDStatRow
              label="DD ACTUAL"
              value={`-${safe(riskStatus.current_drawdown)}%`}
              valueColor={theme.colors.loss}
            />
            <HUDStatRow
              label="PARA RECUPERAR"
              value={`+${safe(riskStatus.recovery_pct_needed)}%`}
              valueColor={theme.colors.neonYellow}
            />
            <HUDStatRow
              label="PERDIDO"
              value={`-$${safe(riskStatus.loss_dollars, 0)}`}
              valueColor={theme.colors.loss}
            />
          </View>

          <HUDDivider />

          {/* HUD Data Table */}
          <View style={styles.tableHeader}>
            <Text style={styles.tableHeaderText}>PERDIDA</Text>
            <Text style={styles.tableHeaderText}>PARA RECUPERAR</Text>
          </View>
          {(riskStatus.recovery_table || []).map(([loss, recovery]) => {
            const isActiveRow =
              riskStatus.current_drawdown >= loss &&
              riskStatus.current_drawdown < loss + 5;
            return (
              <View
                key={loss}
                style={[
                  styles.tableRow,
                  isActiveRow && styles.tableRowActive,
                ]}
              >
                <Text style={[styles.tableCell, { color: theme.colors.loss }]}>
                  -{loss}%
                </Text>
                <Text
                  style={[
                    styles.tableCell,
                    {
                      color:
                        recovery >= 50 ? theme.colors.neonRed : theme.colors.neonYellow,
                    },
                  ]}
                >
                  +{safe(recovery, 1)}%
                </Text>
              </View>
            );
          })}

          <Text style={styles.quoteText}>
            "La conservacion del capital es lo primero" -- Alex Ruiz
          </Text>
        </HUDCard>
      )}

      {/* ── System Info Footer ─────────────────────────── */}
      <View style={styles.footer}>
        <Text style={styles.footerText}>
          BROKER: {(status?.broker ?? 'CAPITAL').toUpperCase()}
        </Text>
        <Text style={styles.footerText}>
          WATCHLIST: {status?.watchlist_count ?? 0} PAIRS
        </Text>
        <Text style={styles.footerText}>
          ENGINE v2.2 // NEONTRADE AI
        </Text>
      </View>
    </ScrollView>
  );
}

// ── Styles ──────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: theme.colors.background,
  },
  content: {
    padding: theme.spacing.md,
    paddingBottom: theme.spacing.xxl,
  },

  // Balance
  balanceAmount: {
    fontFamily: theme.fonts.mono,
    fontSize: 32,
    color: theme.colors.cp2077Yellow,
    textShadowColor: theme.colors.cp2077YellowGlow,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 12,
    marginVertical: theme.spacing.sm,
  },

  // Engine Status
  engineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: theme.spacing.xs,
  },
  statusDot: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  dot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusLabel: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    letterSpacing: 2,
  },
  connectionQuality: {
    alignItems: 'center',
  },
  connectionBars: {
    fontFamily: theme.fonts.mono,
    fontSize: 14,
    color: theme.colors.neonGreen,
    letterSpacing: 1,
  },

  // Risk
  riskActual: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    marginTop: 2,
  },
  pulseBorder: {
    borderColor: theme.colors.neonRed,
    shadowColor: theme.colors.neonRed,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 12,
    elevation: 8,
  },

  // Positions
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
    letterSpacing: 1,
  },
  positionRight: {
    alignItems: 'flex-end',
  },
  positionPnl: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
  },
  positionPhase: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 2,
    marginTop: 2,
  },
  emptyText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textMuted,
    textAlign: 'center',
    paddingVertical: theme.spacing.lg,
    letterSpacing: 3,
  },

  // Daily Activity Grid (2x2)
  activityGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  activityCell: {
    width: '50%',
    alignItems: 'center',
    paddingVertical: theme.spacing.md,
    borderWidth: 0.5,
    borderColor: theme.colors.border,
  },
  activityValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 22,
    color: theme.colors.textWhite,
  },
  activityLabel: {
    fontFamily: theme.fonts.heading,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 3,
    marginTop: 4,
    textTransform: 'uppercase',
  },
  engineActive: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.neonGreen,
    textAlign: 'center',
    letterSpacing: 3,
    marginTop: theme.spacing.sm,
  },

  // Recovery Table
  recoveryHeader: {
    marginBottom: theme.spacing.xs,
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
    borderRadius: 2,
    borderLeftWidth: 2,
    borderLeftColor: theme.colors.neonYellow,
  },
  tableCell: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  quoteText: {
    fontFamily: theme.fonts.light,
    fontSize: 10,
    color: theme.colors.textMuted,
    textAlign: 'center',
    fontStyle: 'italic',
    letterSpacing: 1,
    marginTop: theme.spacing.md,
  },

  // Footer
  footer: {
    alignItems: 'center',
    paddingVertical: theme.spacing.lg,
    marginTop: theme.spacing.md,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
    gap: 4,
  },
  footerText: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    letterSpacing: 3,
  },
});
