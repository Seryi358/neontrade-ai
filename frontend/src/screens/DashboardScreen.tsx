/**
 * Atlas - Dashboard Screen
 * Account overview, engine status, risk monitoring,
 * active positions, and daily activity.
 * Design: Apple Liquid Glass Light
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { theme } from '../theme/apple-glass';

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
    if (level === 'critical') return theme.colors.loss;
    if (level === 'high') return theme.colors.warning;
    if (level === 'moderate') return '#FFCC00';
    return theme.colors.textMuted;
  };

  const riskColor = (pct: number) => {
    if (pct >= 4) return theme.colors.loss;
    if (pct >= 3) return theme.colors.warning;
    if (pct >= 2) return '#FFCC00';
    return theme.colors.profit;
  };

  if (loading && !account && !status) {
    return (
      <View style={styles.container}>
        <LoadingState message="Connecting..." />
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
          tintColor="#007AFF"
        />
      }
    >
      {/* ── HUD Header ─────────────────────────────────── */}
      <HUDHeader title="Dashboard" subtitle={
        `${new Date().toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`
      } />

      {/* Error banner */}
      {error && (
        <ErrorState message={error} onRetry={fetchData} />
      )}

      {/* ── Account Overview ───────────────────────────── */}
      <HUDCard>
        <HUDSectionTitle title="Account" icon="\u25C8" />

        {/* Balance */}
        <Text style={styles.balanceAmount}>
          {account ? formatCurrency(account.balance) : '---'}
        </Text>

        <HUDDivider />

        <HUDStatRow
          label="Equity"
          value={account ? formatCurrency(account.equity) : '---'}
          valueColor={theme.colors.textSecondary}
        />
        <HUDStatRow
          label="Unrealized P&L"
          value={
            account
              ? `${pnlArrow(account.unrealized_pnl)} ${formatCurrency(Math.abs(account.unrealized_pnl))}`
              : '---'
          }
          valueColor={account ? pnlColor(account.unrealized_pnl) : theme.colors.textMuted}
        />
        <HUDStatRow
          label="Available margin"
          value={account ? formatCurrency(account.margin_available ?? account.equity) : '---'}
          valueColor="#007AFF"
        />
      </HUDCard>

      {/* ── Engine Status Row ──────────────────────────── */}
      <HUDCard>
        <HUDSectionTitle title="Engine status" icon="\u25C6" />
        <View style={styles.engineRow}>
          <HUDBadge
            label={status?.mode ?? 'Auto'}
            color={status?.mode === 'MANUAL' ? '#007AFF' : theme.colors.profit}
          />
          <View style={styles.statusDot}>
            <View
              style={[
                styles.dot,
                { backgroundColor: status?.running ? theme.colors.profit : theme.colors.loss },
              ]}
            />
            <Text style={[
              styles.statusLabel,
              { color: status?.running ? theme.colors.profit : theme.colors.loss },
            ]}>
              {status?.running ? 'Connected' : 'Offline'}
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
            ? theme.colors.loss
            : undefined
        }
        style={
          riskStatus?.dd_alert_level === 'critical'
            ? styles.pulseBorder
            : undefined
        }
      >
        <HUDSectionTitle
          title="Risk monitor"
          icon="!"
          color={riskColor(totalRiskPct)}
        />

        <HUDProgressBar
          label="Current risk"
          value={maxRiskPct > 0 ? (totalRiskPct / maxRiskPct) * 100 : 0}
          maxLabel={`${safe(maxRiskPct, 1)}% MAX`}
          color={riskColor(totalRiskPct)}
          showValue
        />
        <Text style={styles.riskActual}>
          {totalRiskPct.toFixed(1)}% deployed
        </Text>

        <HUDDivider />

        {riskStatus && (
          <>
            <HUDStatRow
              label="Drawdown"
              value={`-${safe(riskStatus.current_drawdown)}%`}
              valueColor={ddSeverityColor(riskStatus.dd_alert_level)}
            />
            {riskStatus.dd_alert_level && (
              <HUDBadge
                label={
                  riskStatus.dd_alert_level === 'critical'
                    ? 'DD Critical'
                    : riskStatus.dd_alert_level === 'high'
                      ? 'DD High'
                      : 'DD Alert'
                }
                color={ddSeverityColor(riskStatus.dd_alert_level)}
                small
              />
            )}
            <HUDStatRow
              label="Max risk / day"
              value={maxTotalRisk != null ? `${safe(maxRiskPct, 1)}%` : '---'}
              valueColor={theme.colors.textMuted}
            />
          </>
        )}
      </HUDCard>

      {/* ── Active Positions ───────────────────────────── */}
      <HUDCard>
        <HUDSectionTitle
          title={`Active positions (${positions.length})`}
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
                <Text style={styles.positionPhase}>{(pos.phase || 'initial').toUpperCase()}</Text>
              </View>
            </View>
          ))
        ) : (
          <Text style={styles.emptyText}>No active positions</Text>
        )}
      </HUDCard>

      {/* ── Daily Activity Grid ────────────────────────── */}
      {activity && (
        <HUDCard>
          <HUDSectionTitle title="Daily activity" icon="\u25C7" />
          <View style={styles.activityGrid}>
            <View style={styles.activityCell}>
              <Text style={styles.activityValue}>{activity.scans_completed}</Text>
              <Text style={styles.activityLabel}>Scans</Text>
            </View>
            <View style={styles.activityCell}>
              <Text style={styles.activityValue}>{activity.setups_found}</Text>
              <Text style={styles.activityLabel}>Setups</Text>
            </View>
            <View style={styles.activityCell}>
              <Text style={[styles.activityValue, { color: theme.colors.profit }]}>
                {activity.setups_executed}
              </Text>
              <Text style={styles.activityLabel}>Executed</Text>
            </View>
            <View style={styles.activityCell}>
              <Text style={[styles.activityValue, { color: theme.colors.textSecondary }]}>
                {activity.setups_skipped_ai}
              </Text>
              <Text style={styles.activityLabel}>AI notes</Text>
            </View>
          </View>
          {activity.scans_completed > 0 && (
            <Text style={styles.engineActive}>Engine active</Text>
          )}
        </HUDCard>
      )}

      {/* ── Drawdown Recovery Table ────────────────────── */}
      {riskStatus && riskStatus.current_drawdown > 0 && (
        <HUDCard accentColor="#FFCC00">
          <HUDSectionTitle title="Recovery math" icon="!" color={theme.colors.warning} />

          <View style={styles.recoveryHeader}>
            <HUDStatRow
              label="Current DD"
              value={`-${safe(riskStatus.current_drawdown)}%`}
              valueColor={theme.colors.loss}
            />
            <HUDStatRow
              label="To recover"
              value={`+${safe(riskStatus.recovery_pct_needed)}%`}
              valueColor={theme.colors.warning}
            />
            <HUDStatRow
              label="Lost"
              value={`-$${safe(riskStatus.loss_dollars, 0)}`}
              valueColor={theme.colors.loss}
            />
          </View>

          <HUDDivider />

          <View style={styles.tableHeader}>
            <Text style={styles.tableHeaderText}>Loss</Text>
            <Text style={styles.tableHeaderText}>To recover</Text>
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
                        recovery >= 50 ? theme.colors.loss : theme.colors.warning,
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
          Broker: {status?.broker ?? 'Capital'}
        </Text>
        <Text style={styles.footerText}>
          Watchlist: {status?.watchlist_count ?? 0} pairs
        </Text>
        <Text style={styles.footerText}>
          Engine v2.2 -- Atlas
        </Text>
      </View>
    </ScrollView>
  );
}

// ── Styles (Apple Liquid Glass Light) ───────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
  },
  content: {
    padding: 16,
    paddingBottom: 48,
  },

  // Balance
  balanceAmount: {
    fontFamily: theme.fonts.primary,
    fontSize: 34,
    fontWeight: '700',
    color: '#1d1d1f',
    letterSpacing: -0.5,
    marginVertical: 8,
  },

  // Engine Status
  engineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 4,
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
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    fontWeight: '500',
    letterSpacing: 0,
  },
  connectionQuality: {
    alignItems: 'center',
  },
  connectionBars: {
    fontFamily: theme.fonts.primary,
    fontSize: 14,
    color: '#34C759',
  },

  // Risk
  riskActual: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    fontWeight: '400',
    color: '#aeaeb2',
    marginTop: 2,
  },
  pulseBorder: {
    borderColor: '#FF3B30',
    shadowColor: '#FF3B30',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.18,
    shadowRadius: 12,
    elevation: 6,
  },

  // Positions
  positionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(0,0,0,0.06)',
  },
  positionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  positionPair: {
    fontFamily: theme.fonts.primary,
    fontSize: 15,
    fontWeight: '600',
    color: '#1d1d1f',
  },
  positionRight: {
    alignItems: 'flex-end',
  },
  positionPnl: {
    fontFamily: theme.fonts.primary,
    fontSize: 15,
    fontWeight: '600',
  },
  positionPhase: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    fontWeight: '500',
    color: '#86868b',
    marginTop: 2,
  },
  emptyText: {
    fontFamily: theme.fonts.primary,
    fontSize: 14,
    fontWeight: '400',
    color: '#aeaeb2',
    textAlign: 'center',
    paddingVertical: 24,
  },

  // Daily Activity Grid (2x2)
  activityGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  activityCell: {
    width: '50%',
    alignItems: 'center',
    paddingVertical: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(0,0,0,0.04)',
  },
  activityValue: {
    fontFamily: theme.fonts.primary,
    fontSize: 24,
    fontWeight: '700',
    color: '#1d1d1f',
  },
  activityLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    fontWeight: '500',
    color: '#aeaeb2',
    letterSpacing: 0.3,
    marginTop: 4,
  },
  engineActive: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    fontWeight: '500',
    color: '#34C759',
    textAlign: 'center',
    marginTop: 8,
  },

  // Recovery Table
  recoveryHeader: {
    marginBottom: 4,
  },
  tableHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    marginBottom: 4,
  },
  tableHeaderText: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    fontWeight: '500',
    color: '#aeaeb2',
    letterSpacing: 0.3,
  },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 4,
  },
  tableRowActive: {
    backgroundColor: 'rgba(0, 122, 255, 0.06)',
    borderRadius: 8,
    borderLeftWidth: 2,
    borderLeftColor: '#007AFF',
  },
  tableCell: {
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    fontWeight: '500',
  },
  quoteText: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    fontWeight: '400',
    color: '#aeaeb2',
    textAlign: 'center',
    fontStyle: 'italic',
    marginTop: 16,
  },

  // Footer
  footer: {
    alignItems: 'center',
    paddingVertical: 24,
    marginTop: 16,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: 'rgba(0,0,0,0.06)',
    gap: 4,
  },
  footerText: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    fontWeight: '400',
    color: '#aeaeb2',
  },
});
