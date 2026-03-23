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
import { API_URL, authFetch } from '../services/api';

// Types
interface AccountData {
  balance: number;
  equity: number;
  unrealized_pnl: number;
  open_trade_count: number;
  currency: string;
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

interface EngineStatus {
  running: boolean;
  mode: string;
  broker: string;
  open_positions: number;
  pending_setups: number;
  total_risk: number;
  watchlist_count: number;
  positions: Record<string, Position>;
}

export default function DashboardScreen() {
  const [account, setAccount] = useState<AccountData | null>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setError(null);
      const [accountRes, statusRes] = await Promise.all([
        authFetch(`${API_URL}/api/v1/account`),
        authFetch(`${API_URL}/api/v1/status`),
      ]);
      if (!accountRes.ok || !statusRes.ok) throw new Error('Error del servidor');
      setAccount(await accountRes.json());
      setStatus(await statusRes.json());
    } catch (err) {
      console.error('Failed to fetch data:', err);
      setError('Error al cargar datos');
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
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
            <Text style={styles.statValue}>7.0%</Text>
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

      {/* Broker Info */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>BROKER</Text>
        <Text style={[styles.statValue, { textAlign: 'center' }]}>
          {(status?.broker ?? 'oanda').toUpperCase()}
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
    fontFamily: theme.fonts.primary,
    fontSize: 32,
    color: theme.colors.neonPink,
    letterSpacing: 6,
    textShadowColor: theme.colors.neonPinkGlow,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 15,
  },
  subtitle: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textMuted,
    letterSpacing: 4,
    marginTop: 4,
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
    backgroundColor: 'rgba(255, 7, 58, 0.1)',
  },
  statusText: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
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
    color: theme.colors.neonPink,
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
