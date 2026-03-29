/**
 * NeonTrade AI - Settings Screen
 * Configuration: trading mode, broker, risk, engine control.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  Switch,
  RefreshControl,
  ActivityIndicator,
  Alert,
  TextInput,
} from 'react-native';
import { theme } from '../theme/cyberpunk';
import { api, API_URL, authFetch, setBackendUrl, resetBackendUrl, setApiKey, clearApiKey } from '../services/api';

// Types
interface ModeData {
  mode: 'AUTO' | 'MANUAL';
}

interface BrokerData {
  broker: string;
  connected: boolean;
}

const BROKERS = [
  {
    id: 'capital',
    name: 'Capital.com',
    description: 'Multi-asset: Forex, Acciones, Indices, Materias Primas',
    active: true,
    badge: 'Activo',
  },
  {
    id: 'ibkr',
    name: 'Interactive Brokers',
    description: 'Broker profesional con acceso global a todos los mercados',
    active: false,
    badge: 'Pendiente OAuth',
  },
];

const STRATEGIES = [
  {
    key: 'BLUE',
    label: 'BLUE',
    description: 'Cambio de tendencia 1H',
    color: '#0088ff',
    variants: [
      { key: 'BLUE_A', label: 'Tipo A', description: 'Doble suelo/techo' },
      { key: 'BLUE_B', label: 'Tipo B', description: 'Estandar' },
      { key: 'BLUE_C', label: 'Tipo C', description: 'Rechazo EMA 4H' },
    ],
  },
  { key: 'RED', label: 'RED', description: 'Cambio de tendencia 4H', color: '#da4453', variants: [] },
  { key: 'PINK', label: 'PINK', description: 'Patron correctivo (Onda 4→5)', color: '#ff69b4', variants: [] },
  { key: 'WHITE', label: 'WHITE', description: 'Continuacion post-Pink', color: '#ffffff', variants: [] },
  { key: 'BLACK', label: 'BLACK', description: 'Contratendencia (min 2:1 R:R)', color: '#888888', variants: [] },
  { key: 'GREEN', label: 'GREEN', description: 'Semanal + Diario + 15M (hasta 10:1)', color: '#00ff41', variants: [] },
];

interface StrategyConfig {
  [key: string]: boolean;
}

// Trading hours shown from dynamic config
const _formatHours = (config: Record<string, number>) => [
  { session: 'London + NY', hours: `${String(config.trading_start_hour ?? 7).padStart(2, '0')}:00 - ${String(config.trading_end_hour ?? 21).padStart(2, '0')}:00 UTC` },
  { session: 'Cierre Viernes', hours: `${String(config.close_before_friday_hour ?? 20).padStart(2, '0')}:00 UTC` },
];

export default function SettingsScreen() {
  const [mode, setMode] = useState<'AUTO' | 'MANUAL'>('AUTO');
  const [broker, setBroker] = useState<BrokerData | null>(null);
  const [engineRunning, setEngineRunning] = useState(false);
  const [strategyConfig, setStrategyConfig] = useState<StrategyConfig>({
    BLUE: true, BLUE_A: true, BLUE_B: true, BLUE_C: true,
    RED: true, PINK: true, WHITE: true, BLACK: true, GREEN: true,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [engineStatus, setEngineStatus] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [riskConfig, setRiskConfig] = useState<Record<string, number>>({});
  const [alertConfig, setAlertConfig] = useState<Record<string, any>>({});
  const [editingRisk, setEditingRisk] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [scalpingEnabled, setScalpingEnabled] = useState(false);
  const [scalpingStatus, setScalpingStatus] = useState<any>(null);
  const [fundedEnabled, setFundedEnabled] = useState(false);
  const [fundedStatus, setFundedStatus] = useState<any>(null);
  const [backendUrl, setBackendUrlState] = useState(API_URL);
  const [editingBackendUrl, setEditingBackendUrl] = useState(false);
  const [backendUrlDraft, setBackendUrlDraft] = useState(API_URL);
  const [apiKeyValue, setApiKeyValue] = useState(() => {
    try {
      // Check localStorage first, then injected key from backend (same-origin deploy)
      const stored = window.localStorage.getItem('neontrade_api_key');
      if (stored) return stored;
      const injected = (window as any).__NEONTRADE_API_KEY__;
      if (injected) return injected;
      return '';
    } catch { return ''; }
  });
  const [editingApiKey, setEditingApiKey] = useState(false);
  const [apiKeyDraft, setApiKeyDraft] = useState('');
  const [securityStatus, setSecurityStatus] = useState<any>(null);
  const [watchlistCategories, setWatchlistCategories] = useState<string[]>(['forex']);
  const [watchlistInfo, setWatchlistInfo] = useState<any>(null);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [modeRes, brokerRes, statusRes, stratRes, riskRes, alertRes, scalpingRes, fundedRes] = await Promise.all([
        authFetch(`${API_URL}/api/v1/mode`),
        authFetch(`${API_URL}/api/v1/broker`),
        authFetch(`${API_URL}/api/v1/status`),
        authFetch(`${API_URL}/api/v1/strategies/config`),
        authFetch(`${API_URL}/api/v1/risk-config`).catch(() => null),
        authFetch(`${API_URL}/api/v1/alerts/config`).catch(() => null),
        authFetch(`${API_URL}/api/v1/scalping/status`).catch(() => null),
        authFetch(`${API_URL}/api/v1/funded/status`).catch(() => null),
      ]);

      if (modeRes.ok) {
        const modeData: ModeData = await modeRes.json();
        setMode(modeData.mode);
      }
      if (brokerRes.ok) {
        const brokerData = await brokerRes.json();
        setBroker(brokerData);
      }
      if (statusRes.ok) {
        const statusData = await statusRes.json();
        setEngineRunning(statusData.running);
        setEngineStatus(statusData);
      }
      if (stratRes.ok) {
        const stratData: StrategyConfig = await stratRes.json();
        setStrategyConfig(stratData);
      }
      if (riskRes?.ok) {
        setRiskConfig(await riskRes.json());
      }
      if (alertRes?.ok) {
        setAlertConfig(await alertRes.json());
      }
      if (scalpingRes?.ok) {
        const sd = await scalpingRes.json();
        setScalpingEnabled(sd.enabled);
        setScalpingStatus(sd);
      }
      if (fundedRes?.ok) {
        const fd = await fundedRes.json();
        setFundedEnabled(fd.enabled);
        setFundedStatus(fd);
      }
      try {
        const wlData = await api.getWatchlistCategories();
        setWatchlistCategories(wlData.active_categories || ['forex']);
        setWatchlistInfo(wlData.available || {});
      } catch {}
      try {
        const secData = await api.getSecurityStatus();
        setSecurityStatus(secData);
      } catch {}
    } catch (err) {
      console.error('Failed to fetch settings:', err);
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

  const toggleMode = async () => {
    const newMode = mode === 'AUTO' ? 'MANUAL' : 'AUTO';
    try {
      setActionLoading('mode');
      const res = await authFetch(`${API_URL}/api/v1/mode`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode: newMode }),
      });
      if (res.ok) {
        setMode(newMode);
      }
    } catch (err) {
      console.error('Failed to toggle mode:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const applyProfile = (profileId: string, profileName: string) => {
    Alert.alert(
      'APLICAR PERFIL',
      `Se aplicará el perfil "${profileName}". Esto cambiará múltiples ajustes (riesgo, estilo, watchlists, gestión de posición). ¿Continuar?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'APLICAR',
          onPress: async () => {
            try {
              setActionLoading('profile');
              const res = await authFetch(`${API_URL}/api/v1/profiles/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ profile_id: profileId }),
              });
              if (res.ok) {
                // Refresh all data to reflect the new profile settings
                await fetchData();
                Alert.alert('Perfil Aplicado', `"${profileName}" configurado correctamente`);
              } else {
                const err = await res.json().catch(() => ({}));
                Alert.alert('Error', err.detail || 'No se pudo aplicar el perfil');
              }
            } catch (err) {
              console.error('Failed to apply profile:', err);
              Alert.alert('Error', 'No se pudo conectar con el servidor');
            } finally {
              setActionLoading(null);
            }
          },
        },
      ],
    );
  };

  const toggleScalping = async () => {
    const newVal = !scalpingEnabled;
    try {
      setActionLoading('scalping');
      const res = await authFetch(`${API_URL}/api/v1/scalping/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newVal }),
      });
      if (res.ok) {
        setScalpingEnabled(newVal);
        const sd = await authFetch(`${API_URL}/api/v1/scalping/status`);
        if (sd.ok) setScalpingStatus(await sd.json());
      }
    } catch (err) {
      console.error('Failed to toggle scalping:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const toggleFunded = async () => {
    const newVal = !fundedEnabled;
    try {
      setActionLoading('funded');
      const res = await authFetch(`${API_URL}/api/v1/funded/toggle`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newVal }),
      });
      if (res.ok) {
        setFundedEnabled(newVal);
        const fd = await authFetch(`${API_URL}/api/v1/funded/status`);
        if (fd.ok) setFundedStatus(await fd.json());
      }
    } catch (err) {
      console.error('Failed to toggle funded:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const startEngine = async () => {
    try {
      setActionLoading('start');
      const res = await authFetch(`${API_URL}/api/v1/engine/start`, { method: 'POST' });
      if (res.ok) {
        setEngineRunning(true);
      }
    } catch (err) {
      console.error('Failed to start engine:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const stopEngine = async () => {
    try {
      setActionLoading('stop');
      const res = await authFetch(`${API_URL}/api/v1/engine/stop`, { method: 'POST' });
      if (res.ok) {
        setEngineRunning(false);
      }
    } catch (err) {
      console.error('Failed to stop engine:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const emergencyCloseAll = () => {
    Alert.alert(
      'CERRAR TODAS LAS POSICIONES',
      'Esta accion cerrara TODAS las posiciones abiertas inmediatamente. Esta seguro?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'SI, CERRAR TODO',
          style: 'destructive',
          onPress: async () => {
            try {
              setActionLoading('emergency');
              await authFetch(`${API_URL}/api/v1/emergency/close-all`, { method: 'POST' });
              await fetchData();
            } catch (err) {
              console.error('Emergency close failed:', err);
            } finally {
              setActionLoading(null);
            }
          },
        },
      ]
    );
  };

  const saveRiskField = async (field: string, rawValue: string) => {
    const numValue = parseFloat(rawValue);
    if (isNaN(numValue)) return;
    // Convert display percentage to decimal for percentage fields
    const isPercentField = ['risk_day_trading', 'risk_scalping', 'risk_swing', 'max_total_risk', 'move_sl_to_be_pct_to_tp1', 'correlated_risk_pct'].includes(field);
    const apiValue = isPercentField ? numValue / 100 : numValue;
    try {
      const res = await authFetch(`${API_URL}/api/v1/risk-config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ [field]: apiValue }),
      });
      if (res.ok) {
        setRiskConfig((prev) => ({ ...prev, [field]: apiValue }));
      }
    } catch (err) {
      console.error('Failed to save risk config:', err);
    }
    setEditingRisk(null);
  };

  const toggleStrategy = async (key: string, value: boolean) => {
    const prevConfig = { ...strategyConfig };
    const newConfig = { ...strategyConfig, [key]: value };

    // If toggling a main strategy OFF, also disable its variants
    if (!value) {
      const strat = STRATEGIES.find((s) => s.key === key);
      if (strat?.variants?.length) {
        for (const v of strat.variants) {
          newConfig[v.key] = false;
        }
      }
    }

    // If toggling a main strategy ON, enable all its variants by default
    if (value) {
      const strat = STRATEGIES.find((s) => s.key === key);
      if (strat?.variants?.length) {
        for (const v of strat.variants) {
          newConfig[v.key] = true;
        }
      }
    }

    // If enabling a variant, ensure the parent strategy is also enabled
    if (value) {
      const parent = STRATEGIES.find((s) =>
        s.variants?.some((v) => v.key === key)
      );
      if (parent) {
        newConfig[parent.key] = true;
      }
    }

    setStrategyConfig(newConfig);

    try {
      const res = await authFetch(`${API_URL}/api/v1/strategies/config`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newConfig),
      });
      if (!res.ok) throw new Error('Server error');
    } catch (err) {
      console.error('Failed to update strategy config:', err);
      setStrategyConfig(prevConfig);
    }
  };

  const toggleWatchlistCategory = async (category: string) => {
    try {
      const updated = watchlistCategories.includes(category)
        ? watchlistCategories.filter((c: string) => c !== category)
        : [...watchlistCategories, category];
      // Don't allow empty
      if (updated.length === 0) return;
      await api.updateWatchlistCategories(updated);
      setWatchlistCategories(updated);
    } catch (e: any) {
      // handle error
    }
  };

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={theme.colors.cp2077Yellow} />
        <Text style={styles.loadingText}>Cargando configuracion...</Text>
      </View>
    );
  }

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

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
      }
    >
      <Text style={styles.header}>CONFIGURACION</Text>
      <Text style={styles.subheader}>Ajustes del sistema</Text>

      {/* Trading Mode Card */}
      <View style={[styles.card, styles.modeCard]}>
        <Text style={styles.cardTitle}>MODO DE OPERACION</Text>
        <View style={styles.modeRow}>
          <View style={styles.modeInfo}>
            <View style={[
              styles.modeIndicator,
              { backgroundColor: mode === 'AUTO' ? theme.colors.neonGreen : theme.colors.neonCyan },
            ]} />
            <Text style={styles.modeLabel}>{mode}</Text>
          </View>
          <Switch
            value={mode === 'AUTO'}
            onValueChange={toggleMode}
            trackColor={{ false: theme.colors.backgroundLight, true: 'rgba(57, 255, 20, 0.3)' }}
            thumbColor={mode === 'AUTO' ? theme.colors.neonGreen : theme.colors.neonCyan}
            disabled={actionLoading === 'mode'}
          />
        </View>
        <Text style={styles.modeDescription}>
          {mode === 'AUTO'
            ? 'NeonTrade opera automaticamente basado en las estrategias detectadas'
            : 'NeonTrade te sugiere operaciones y tu decides si ejecutar o no'
          }
        </Text>
      </View>

      {/* Trading Profiles Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>PERFILES DE TRADING</Text>
        <Text style={styles.strategyHint}>
          Presets de configuración con valores recomendados por TradingLab
        </Text>

        <TouchableOpacity
          style={[styles.profileBtn, { borderColor: theme.colors.neonCyan }]}
          onPress={() => applyProfile('tradinglab_recommended', 'TradingLab Recommended')}
          disabled={actionLoading === 'profile'}
        >
          {actionLoading === 'profile' ? (
            <ActivityIndicator size="small" color={theme.colors.neonCyan} />
          ) : (
            <>
              <Text style={[styles.profileBtnTitle, { color: theme.colors.neonCyan }]}>
                TRADINGLAB RECOMMENDED
              </Text>
              <Text style={styles.profileBtnDesc}>
                Day Trading · 1% riesgo · R:R 1.5:1 · Salida rápida · Sin parciales · BE al 1%
              </Text>
              <Text style={styles.profileBtnDesc}>
                Watchlists completas · London + NY · LP por defecto, CP y CPA disponibles
              </Text>
            </>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.profileBtn, { borderColor: theme.colors.neonGreen, marginTop: theme.spacing.sm }]}
          onPress={() => applyProfile('conservative', 'Conservative')}
          disabled={actionLoading === 'profile'}
        >
          {actionLoading === 'profile' ? (
            <ActivityIndicator size="small" color={theme.colors.neonGreen} />
          ) : (
            <>
              <Text style={[styles.profileBtnTitle, { color: theme.colors.neonGreen }]}>
                CONSERVATIVE
              </Text>
              <Text style={styles.profileBtnDesc}>
                Swing Trading · 1% riesgo · R:R 2.0:1 · Trailing amplio (LP)
              </Text>
              <Text style={styles.profileBtnDesc}>
                Solo Forex principales · Ideal para principiantes
              </Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {/* Scalping Module Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>MODULO SCALPING</Text>
        <Text style={styles.strategyHint}>
          Workshop de Scalping — Temporalidades comprimidas H1→M15→M5→M1
        </Text>
        <View style={styles.modeRow}>
          <View style={styles.modeInfo}>
            <View style={[
              styles.modeIndicator,
              { backgroundColor: scalpingEnabled ? theme.colors.neonYellow : theme.colors.textMuted },
            ]} />
            <Text style={[styles.modeLabel, { fontSize: 16 }]}>
              {scalpingEnabled ? 'ACTIVO' : 'INACTIVO'}
            </Text>
          </View>
          <Switch
            value={scalpingEnabled}
            onValueChange={toggleScalping}
            trackColor={{ false: theme.colors.backgroundLight, true: 'rgba(255, 184, 0, 0.3)' }}
            thumbColor={scalpingEnabled ? theme.colors.neonYellow : theme.colors.textMuted}
            disabled={actionLoading === 'scalping'}
          />
        </View>
        {scalpingEnabled && scalpingStatus && (
          <View style={{ marginTop: theme.spacing.sm, borderTopWidth: 1, borderTopColor: theme.colors.border, paddingTop: theme.spacing.sm }}>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Riesgo/Trade</Text>
              <Text style={styles.configValue}>0.5%</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>DD Diario Max</Text>
              <Text style={[styles.configValue, { color: theme.colors.neonYellow }]}>5%</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>DD Total Max</Text>
              <Text style={[styles.configValue, { color: theme.colors.neonYellow }]}>10%</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Intervalo Scan</Text>
              <Text style={styles.configValue}>30s</Text>
            </View>
            <View style={{ marginTop: theme.spacing.sm }}>
              <Text style={{ fontFamily: theme.fonts.primary, fontSize: 9, color: theme.colors.textMuted, letterSpacing: 1 }}>
                MAPEO: D→H1 | H4→M15 | H1→M5 | M5→M1
              </Text>
            </View>
          </View>
        )}
      </View>

      {/* Funded Account Mode Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>CUENTA FONDEADA</Text>
        <Text style={styles.strategyHint}>
          Workshop Cuentas Fondeadas — Limites estrictos de drawdown
        </Text>
        <View style={styles.modeRow}>
          <View style={styles.modeInfo}>
            <View style={[
              styles.modeIndicator,
              { backgroundColor: fundedEnabled ? theme.colors.neonOrange : theme.colors.textMuted },
            ]} />
            <Text style={[styles.modeLabel, { fontSize: 16 }]}>
              {fundedEnabled ? 'ACTIVO' : 'INACTIVO'}
            </Text>
          </View>
          <Switch
            value={fundedEnabled}
            onValueChange={toggleFunded}
            trackColor={{ false: theme.colors.backgroundLight, true: 'rgba(255, 107, 53, 0.3)' }}
            thumbColor={fundedEnabled ? theme.colors.neonOrange : theme.colors.textMuted}
            disabled={actionLoading === 'funded'}
          />
        </View>
        {fundedEnabled && fundedStatus && (
          <View style={{ marginTop: theme.spacing.sm, borderTopWidth: 1, borderTopColor: theme.colors.border, paddingTop: theme.spacing.sm }}>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Tipo Cuenta</Text>
              <Text style={[styles.configValue, { color: theme.colors.neonCyan }]}>
                {(fundedStatus.account_type || 'swing').toUpperCase()}
              </Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Evaluacion</Text>
              <Text style={[styles.configValue, { color: theme.colors.neonCyan }]}>
                {(fundedStatus.evaluation_type || '2phase').toUpperCase()} — Fase {fundedStatus.current_phase || 1}
              </Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>DD Diario Max</Text>
              <Text style={[styles.configValue, { color: theme.colors.neonOrange }]}>
                {(fundedStatus.daily_dd_limit || 5).toFixed(0)}%
              </Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>DD Diario Usado</Text>
              <Text style={[styles.configValue,
                (fundedStatus.daily_dd_used_pct || 0) > 60 ? styles.loss : styles.profit
              ]}>
                {(fundedStatus.daily_dd_used_pct || 0).toFixed(1)}%
              </Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>DD Total Max</Text>
              <Text style={[styles.configValue, { color: theme.colors.neonOrange }]}>
                {(fundedStatus.total_dd_limit || 10).toFixed(0)}%
              </Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>DD Total Actual</Text>
              <Text style={[styles.configValue,
                (fundedStatus.total_dd_pct || 0) > 5 ? styles.loss : styles.profit
              ]}>
                {(fundedStatus.total_dd_pct || 0).toFixed(2)}%
              </Text>
            </View>
            {(fundedStatus.profit_target_pct || 0) > 0 && (
              <View style={styles.configRow}>
                <Text style={styles.configLabel}>Objetivo Profit</Text>
                <Text style={[styles.configValue, { color: theme.colors.neonGreen }]}>
                  {(fundedStatus.profit_progress_pct || 0).toFixed(1)}% / {(fundedStatus.profit_target_pct || 0).toFixed(0)}%
                </Text>
              </View>
            )}
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>No Overnight</Text>
              <Text style={styles.configValue}>{fundedStatus.no_overnight ? 'Si' : 'No'}</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>No News Trading</Text>
              <Text style={styles.configValue}>{fundedStatus.no_news_trading ? 'Si' : 'No'}</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>No Weekend</Text>
              <Text style={styles.configValue}>{fundedStatus.no_weekend ? 'Si' : 'No'}</Text>
            </View>
          </View>
        )}
      </View>

      {/* Strategy Selection Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ESTRATEGIAS ACTIVAS</Text>
        <Text style={styles.strategyHint}>
          Selecciona las estrategias que la IA debe utilizar
        </Text>
        {STRATEGIES.map((strat) => (
          <View key={strat.key}>
            <View style={styles.strategyRow}>
              <View style={styles.strategyInfo}>
                <View style={[styles.strategyDot, { backgroundColor: strat.color }]} />
                <View style={styles.strategyText}>
                  <Text style={[
                    styles.strategyLabel,
                    !strategyConfig[strat.key] && styles.strategyLabelDisabled,
                  ]}>
                    {strat.label}
                  </Text>
                  <Text style={styles.strategyDesc}>{strat.description}</Text>
                </View>
              </View>
              <Switch
                value={strategyConfig[strat.key] ?? true}
                onValueChange={(val) => toggleStrategy(strat.key, val)}
                trackColor={{ false: theme.colors.backgroundLight, true: `${strat.color}40` }}
                thumbColor={strategyConfig[strat.key] ? strat.color : theme.colors.textMuted}
              />
            </View>
            {/* BLUE variants */}
            {strat.variants?.length > 0 && strategyConfig[strat.key] && (
              <View style={styles.variantContainer}>
                {strat.variants.map((variant) => (
                  <View key={variant.key} style={styles.variantRow}>
                    <View style={styles.variantInfo}>
                      <Text style={[
                        styles.variantLabel,
                        !strategyConfig[variant.key] && styles.strategyLabelDisabled,
                      ]}>
                        {variant.label}
                      </Text>
                      <Text style={styles.variantDesc}>{variant.description}</Text>
                    </View>
                    <Switch
                      value={strategyConfig[variant.key] ?? true}
                      onValueChange={(val) => toggleStrategy(variant.key, val)}
                      trackColor={{ false: theme.colors.backgroundLight, true: `${strat.color}40` }}
                      thumbColor={strategyConfig[variant.key] ? strat.color : theme.colors.textMuted}
                    />
                  </View>
                ))}
              </View>
            )}
          </View>
        ))}
        <View style={styles.strategyCountRow}>
          <Text style={styles.strategyCountLabel}>Estrategias activas:</Text>
          <Text style={styles.strategyCountValue}>
            {STRATEGIES.filter((s) => strategyConfig[s.key]).length} / {STRATEGIES.length}
          </Text>
        </View>
      </View>

      {/* Broker Selection Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>BROKER</Text>
        {BROKERS.map((b) => (
          <View
            key={b.id}
            style={[
              styles.brokerItem,
              broker?.broker === b.id && styles.brokerItemActive,
            ]}
          >
            <View style={styles.brokerInfo}>
              <View style={styles.brokerNameRow}>
                <Text style={[
                  styles.brokerName,
                  !b.active && styles.brokerNameDisabled,
                ]}>
                  {b.name}
                </Text>
                <View style={[
                  styles.brokerBadge,
                  b.active ? styles.brokerBadgeActive : styles.brokerBadgeInactive,
                ]}>
                  <Text style={[
                    styles.brokerBadgeText,
                    b.active ? styles.brokerBadgeTextActive : styles.brokerBadgeTextInactive,
                  ]}>
                    {b.badge}
                  </Text>
                </View>
              </View>
              <Text style={styles.brokerDesc}>{b.description}</Text>
            </View>
            {broker?.broker === b.id && broker?.connected && (
              <View style={styles.connectedBadge}>
                <Text style={styles.connectedText}>● CONECTADO</Text>
              </View>
            )}
          </View>
        ))}
      </View>

      {/* ── WATCHLISTS (TradingLab) ───────────────────────── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>WATCHLISTS</Text>
        <Text style={styles.cardSubtitle}>Categorías de instrumentos del curso TradingLab</Text>

        {[
          { key: 'forex', label: 'FOREX (Principales)', icon: '💱' },
          { key: 'forex_exotic', label: 'FOREX (Exóticos)', icon: '🌍' },
          { key: 'commodities', label: 'COMMODITIES', icon: '🛢️' },
          { key: 'indices', label: 'ÍNDICES', icon: '📊' },
          { key: 'crypto', label: 'CRYPTO', icon: '₿' },
        ].map(cat => {
          const info = watchlistInfo?.[cat.key];
          const isActive = watchlistCategories.includes(cat.key);
          return (
            <View key={cat.key} style={styles.watchlistRow}>
              <View style={{ flex: 1 }}>
                <Text style={[styles.strategyLabel, isActive && { color: '#5df4fe' }]}>
                  {cat.icon} {cat.label}
                </Text>
                <Text style={styles.watchlistCount}>
                  {info?.count || 0} instrumentos
                </Text>
              </View>
              <Switch
                value={isActive}
                onValueChange={() => toggleWatchlistCategory(cat.key)}
                trackColor={{ false: '#2a2445', true: 'rgba(0, 240, 255, 0.3)' }}
                thumbColor={isActive ? '#5df4fe' : '#555'}
              />
            </View>
          );
        })}

        <View style={styles.totalInstruments}>
          <Text style={styles.configValue}>
            Total activo: {watchlistCategories.reduce((sum: number, cat: string) =>
              sum + (watchlistInfo?.[cat]?.count || 0), 0)} instrumentos
          </Text>
        </View>
      </View>

      {/* Risk Management Card (Editable) */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>GESTION DE RIESGO</Text>
        <Text style={styles.strategyHint}>Toca un valor para editarlo</Text>
        {[
          { key: 'risk_day_trading', label: 'Day Trading', fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
          { key: 'risk_scalping', label: 'Scalping', fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
          { key: 'risk_swing', label: 'Swing', fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
          { key: 'max_total_risk', label: 'Max Total Risk', fmt: (v: number) => `${(v * 100).toFixed(1)}%` },
          { key: 'correlated_risk_pct', label: 'Riesgo Correlacion', fmt: (v: number) => `${(v * 100).toFixed(2)}%` },
          { key: 'min_rr_ratio', label: 'Min R:R', fmt: (v: number) => `1:${v.toFixed(2)}` },
          { key: 'move_sl_to_be_pct_to_tp1', label: 'BE a % de TP1', fmt: (v: number) => `${(v * 100).toFixed(0)}%` },
        ].map((item) => (
          <View key={item.key} style={styles.configRow}>
            <Text style={styles.configLabel}>{item.label}</Text>
            {editingRisk === item.key ? (
              <TextInput
                style={styles.riskInput}
                value={editValue}
                onChangeText={setEditValue}
                onBlur={() => saveRiskField(item.key, editValue)}
                onSubmitEditing={() => saveRiskField(item.key, editValue)}
                keyboardType="decimal-pad"
                autoFocus
                selectTextOnFocus
              />
            ) : (
              <TouchableOpacity onPress={() => {
                const val = riskConfig[item.key];
                const isPercent = ['risk_day_trading', 'risk_scalping', 'risk_swing', 'max_total_risk', 'move_sl_to_be_pct_to_tp1', 'correlated_risk_pct'].includes(item.key);
                setEditValue(isPercent ? (val * 100).toFixed(1) : val?.toFixed(2) || '0');
                setEditingRisk(item.key);
              }}>
                <Text style={[styles.configValue, { color: theme.colors.neonCyan }]}>
                  {riskConfig[item.key] !== undefined ? item.fmt(riskConfig[item.key]) : '---'}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
      </View>

      {/* Trading Hours Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>HORARIO DE OPERACION</Text>
        {_formatHours(riskConfig).map((item, index) => (
          <View key={index} style={styles.configRow}>
            <Text style={styles.configLabel}>{item.session}</Text>
            <Text style={styles.configValue}>{item.hours}</Text>
          </View>
        ))}
      </View>

      {/* Engine Control Card */}
      <View style={[styles.card, styles.engineCard]}>
        <Text style={styles.cardTitle}>CONTROL DEL ENGINE</Text>

        <View style={styles.engineStatusRow}>
          <Text style={styles.engineStatusLabel}>Estado:</Text>
          <View style={[
            styles.engineStatusBadge,
            engineRunning ? styles.engineOnline : styles.engineOffline,
          ]}>
            <Text style={styles.engineStatusText}>
              {engineRunning ? '● ACTIVO' : '○ DETENIDO'}
            </Text>
          </View>
        </View>

        <View style={styles.engineButtons}>
          <TouchableOpacity
            style={[styles.engineBtn, styles.startBtn]}
            onPress={startEngine}
            disabled={engineRunning || actionLoading === 'start'}
          >
            {actionLoading === 'start' ? (
              <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
            ) : (
              <Text style={styles.startBtnText}>INICIAR ENGINE</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.engineBtn, styles.stopBtn]}
            onPress={stopEngine}
            disabled={!engineRunning || actionLoading === 'stop'}
          >
            {actionLoading === 'stop' ? (
              <ActivityIndicator size="small" color={theme.colors.textWhite} />
            ) : (
              <Text style={styles.stopBtnText}>DETENER ENGINE</Text>
            )}
          </TouchableOpacity>
        </View>

        <TouchableOpacity
          style={styles.emergencyBtn}
          onPress={emergencyCloseAll}
          disabled={actionLoading === 'emergency'}
        >
          {actionLoading === 'emergency' ? (
            <ActivityIndicator size="small" color={theme.colors.textWhite} />
          ) : (
            <Text style={styles.emergencyBtnText}>⚠ CERRAR TODAS LAS POSICIONES</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Alert Channels Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>CANALES DE ALERTAS</Text>
        <Text style={styles.strategyHint}>
          Se activan automaticamente cuando las credenciales estan en las variables de entorno
        </Text>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Gmail OAuth2</Text>
          <Text style={[styles.configValue, alertConfig.gmail_enabled ? styles.profit : styles.loss]}>
            {alertConfig.gmail_enabled ? '● Activo' : '○ Inactivo'}
          </Text>
        </View>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Telegram</Text>
          <Text style={[styles.configValue, alertConfig.telegram_enabled ? styles.profit : styles.loss]}>
            {alertConfig.telegram_enabled ? '● Activo' : '○ Inactivo'}
          </Text>
        </View>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Discord</Text>
          <Text style={[styles.configValue, alertConfig.discord_enabled ? styles.profit : styles.loss]}>
            {alertConfig.discord_enabled ? '● Activo' : '○ Inactivo'}
          </Text>
        </View>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Email SMTP</Text>
          <Text style={[styles.configValue, alertConfig.email_enabled ? styles.profit : styles.loss]}>
            {alertConfig.email_enabled ? '● Activo' : '○ Inactivo'}
          </Text>
        </View>
        {(alertConfig.telegram_enabled || alertConfig.discord_enabled || alertConfig.email_enabled || alertConfig.gmail_enabled) && (
          <>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Trades ejecutados</Text>
              <Text style={styles.configValue}>{alertConfig.notify_trade_executed ? 'Si' : 'No'}</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Setups pendientes</Text>
              <Text style={styles.configValue}>{alertConfig.notify_setup_pending ? 'Si' : 'No'}</Text>
            </View>
            <View style={styles.configRow}>
              <Text style={styles.configLabel}>Trades cerrados</Text>
              <Text style={styles.configValue}>{alertConfig.notify_trade_closed ? 'Si' : 'No'}</Text>
            </View>
          </>
        )}
      </View>

      {/* Backend URL Card (for remote VPS deployment) */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>SERVIDOR BACKEND</Text>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>URL</Text>
          {editingBackendUrl ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1, justifyContent: 'flex-end' }}>
              <TextInput
                style={[styles.configValue, { borderBottomWidth: 1, borderColor: theme.colors.neonCyan, minWidth: 180, textAlign: 'right' }]}
                value={backendUrlDraft}
                onChangeText={setBackendUrlDraft}
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="https://neontrade.tu-vps.com"
                placeholderTextColor={theme.colors.textSecondary}
              />
              <TouchableOpacity
                style={{ marginLeft: 8, backgroundColor: theme.colors.neonCyan, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 }}
                onPress={() => {
                  if (backendUrlDraft && backendUrlDraft.startsWith('http')) {
                    setBackendUrl(backendUrlDraft);
                    setBackendUrlState(backendUrlDraft);
                    setEditingBackendUrl(false);
                    Alert.alert('Backend', 'URL actualizada. Reinicia la app para aplicar.');
                  } else {
                    Alert.alert('Error', 'URL debe empezar con http:// o https://');
                  }
                }}
              >
                <Text style={{ color: theme.colors.background, fontWeight: 'bold', fontSize: 12 }}>OK</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity onPress={() => { setBackendUrlDraft(backendUrl); setEditingBackendUrl(true); }}>
              <Text style={[styles.configValue, { color: theme.colors.neonCyan }]}>
                {backendUrl}
              </Text>
            </TouchableOpacity>
          )}
        </View>
        {backendUrl !== 'http://localhost:8000' && (
          <TouchableOpacity
            style={{ marginTop: 8, alignSelf: 'flex-end' }}
            onPress={() => {
              resetBackendUrl();
              setBackendUrlState('http://localhost:8000');
              setEditingBackendUrl(false);
              Alert.alert('Backend', 'Restaurado a localhost. Reinicia la app.');
            }}
          >
            <Text style={{ color: theme.colors.cp2077Yellow, fontSize: 12 }}>Restaurar a localhost</Text>
          </TouchableOpacity>
        )}
      </View>

      {/* API Key Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>API KEY</Text>
        <Text style={{ color: theme.colors.textSecondary, fontSize: 11, marginBottom: 8 }}>
          {securityStatus && !securityStatus.auth_enabled
            ? 'Autenticacion deshabilitada en el servidor'
            : securityStatus && securityStatus.api_keys_count === 0
              ? 'Acceso abierto (sin keys configuradas) — primera ejecucion'
              : 'Requerida para conectar al servidor remoto'}
        </Text>
        {/* Auth status badge */}
        {securityStatus && (
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
            <View style={{
              width: 8, height: 8, borderRadius: 4, marginRight: 6,
              backgroundColor: !securityStatus.auth_enabled || securityStatus.api_keys_count === 0
                ? theme.colors.neonGreen : apiKeyValue ? theme.colors.neonGreen : theme.colors.cp2077Yellow,
            }} />
            <Text style={{ color: theme.colors.textSecondary, fontSize: 10, fontFamily: theme.fonts.primary }}>
              {!securityStatus.auth_enabled
                ? 'AUTH DESHABILITADA'
                : securityStatus.api_keys_count === 0
                  ? 'ACCESO ABIERTO'
                  : apiKeyValue
                    ? 'AUTENTICADA'
                    : 'KEY REQUERIDA'}
            </Text>
          </View>
        )}
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Key</Text>
          {editingApiKey ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1, justifyContent: 'flex-end' }}>
              <TextInput
                style={[styles.configValue, { borderBottomWidth: 1, borderColor: theme.colors.neonCyan, minWidth: 200, textAlign: 'right', fontSize: 11 }]}
                value={apiKeyDraft}
                onChangeText={setApiKeyDraft}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry={false}
                placeholder="nt_..."
                placeholderTextColor={theme.colors.textSecondary}
              />
              <TouchableOpacity
                style={{ marginLeft: 8, backgroundColor: theme.colors.neonCyan, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 }}
                onPress={() => {
                  if (apiKeyDraft && apiKeyDraft.startsWith('nt_')) {
                    setApiKey(apiKeyDraft);
                    setApiKeyValue(apiKeyDraft);
                    setEditingApiKey(false);
                    Alert.alert('API Key', 'Key guardada. Las peticiones ahora incluyen autenticacion.');
                  } else {
                    Alert.alert('Error', 'API Key debe empezar con nt_');
                  }
                }}
              >
                <Text style={{ color: theme.colors.background, fontWeight: 'bold', fontSize: 12 }}>OK</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <TouchableOpacity onPress={() => { setApiKeyDraft(apiKeyValue); setEditingApiKey(true); }}>
              <Text style={[styles.configValue, {
                color: apiKeyValue
                  ? theme.colors.neonGreen
                  : (securityStatus && (securityStatus.api_keys_count === 0 || !securityStatus.auth_enabled))
                    ? theme.colors.neonCyan
                    : theme.colors.cp2077Yellow,
              }]}>
                {apiKeyValue
                  ? apiKeyValue.slice(0, 8) + '...' + apiKeyValue.slice(-4)
                  : (securityStatus && !securityStatus.auth_enabled)
                    ? 'No requerida'
                    : (securityStatus && securityStatus.api_keys_count === 0)
                      ? 'Acceso abierto'
                      : 'No configurada'}
              </Text>
            </TouchableOpacity>
          )}
        </View>
        {apiKeyValue ? (
          <TouchableOpacity
            style={{ marginTop: 8, alignSelf: 'flex-end' }}
            onPress={() => {
              clearApiKey();
              setApiKeyValue('');
              setEditingApiKey(false);
              Alert.alert('API Key', 'Key eliminada.');
            }}
          >
            <Text style={{ color: theme.colors.cp2077Yellow, fontSize: 12 }}>Eliminar Key</Text>
          </TouchableOpacity>
        ) : null}
      </View>

      {/* Connection Status Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>ESTADO DE CONEXION</Text>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Motor</Text>
          <Text style={[
            styles.configValue,
            engineRunning ? styles.profit : styles.loss,
          ]}>
            {engineRunning ? '● Ejecutando' : '○ Detenido'}
          </Text>
        </View>
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Broker</Text>
          <Text style={[
            styles.configValue,
            broker?.connected ? styles.profit : styles.loss,
          ]}>
            {broker?.connected ? '● Conectado' : '○ Desconectado'}
          </Text>
        </View>
        {engineStatus?.scanned_instruments != null && (
          <View style={styles.configRow}>
            <Text style={styles.configLabel}>Escaneados</Text>
            <Text style={styles.configValue}>
              {engineStatus.scanned_instruments}/{engineStatus.watchlist_count || 0}
            </Text>
          </View>
        )}
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>API</Text>
          <Text style={[styles.configValue, styles.profit]}>
            ● Activa
          </Text>
        </View>
        {engineStatus?.startup_error ? (
          <View style={{ marginTop: 8, padding: 8, backgroundColor: 'rgba(255,46,99,0.1)', borderRadius: 4, borderWidth: 1, borderColor: theme.colors.neonRed }}>
            <Text style={{ color: theme.colors.neonRed, fontFamily: theme.fonts.heading, fontSize: 10, letterSpacing: 1, marginBottom: 4 }}>ERROR DE CONEXION</Text>
            <Text style={{ color: theme.colors.textSecondary, fontFamily: theme.fonts.primary, fontSize: 10 }} numberOfLines={3}>
              {engineStatus.startup_error}
            </Text>
            <TouchableOpacity
              style={{ marginTop: 6, alignSelf: 'flex-start' }}
              onPress={startEngine}
            >
              <Text style={{ color: theme.colors.neonCyan, fontFamily: theme.fonts.heading, fontSize: 11, letterSpacing: 1 }}>REINTENTAR CONEXION</Text>
            </TouchableOpacity>
          </View>
        ) : null}
      </View>

      {/* Diagnostic Card */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>DIAGNOSTICO DEL BROKER</Text>
        <Text style={{ color: theme.colors.textSecondary, fontSize: 10, fontFamily: theme.fonts.primary, marginBottom: 8 }}>
          Prueba paso a paso la conexion con el broker
        </Text>
        <TouchableOpacity
          style={{ backgroundColor: theme.colors.neonCyan, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 4, alignSelf: 'flex-start' }}
          onPress={async () => {
            setActionLoading('diagnostic');
            try {
              const res = await authFetch(`${API_URL}/api/v1/diagnostic`);
              if (res.ok) {
                const data = await res.json();
                const stepLines = (data.steps || []).map((s: any) =>
                  `${s.ok ? '✓' : '✗'} ${s.step}: ${s.detail}${s.sample ? '\n  ' + JSON.stringify(s.sample).slice(0, 200) : ''}`
                ).join('\n');
                Alert.alert('Diagnostico', stepLines || 'Sin resultados');
              } else {
                Alert.alert('Error', `HTTP ${res.status}`);
              }
            } catch (err: any) {
              Alert.alert('Error', err.message || 'Fallo la conexion');
            } finally {
              setActionLoading(null);
            }
          }}
        >
          {actionLoading === 'diagnostic' ? (
            <ActivityIndicator size="small" color={theme.colors.background} />
          ) : (
            <Text style={{ color: theme.colors.background, fontWeight: 'bold', fontFamily: theme.fonts.heading, fontSize: 12 }}>EJECUTAR DIAGNOSTICO</Text>
          )}
        </TouchableOpacity>
      </View>

      <View style={{ height: theme.spacing.xl }} />
    </ScrollView>
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
  // Cards
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.borderRadius.md,
    borderWidth: 1,
    borderColor: theme.colors.border,
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
  // Mode card
  modeCard: {
    borderColor: theme.colors.cp2077Yellow,
  },
  modeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  modeInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  modeIndicator: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  modeLabel: {
    fontFamily: theme.fonts.heading,
    fontSize: 22,
    color: theme.colors.textWhite,
    letterSpacing: 4,
  },
  modeDescription: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    lineHeight: 18,
  },
  // Strategy selection
  strategyHint: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.sm,
    letterSpacing: 1,
  },
  strategyRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: theme.spacing.xs + 2,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.border,
  },
  strategyInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 10,
  },
  strategyDot: {
    width: 14,
    height: 14,
    borderRadius: 7,
  },
  strategyText: {
    flex: 1,
  },
  strategyLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 14,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
  strategyLabelDisabled: {
    color: theme.colors.textMuted,
  },
  strategyDesc: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
    marginTop: 1,
  },
  variantContainer: {
    marginLeft: 38,
    borderLeftWidth: 1,
    borderLeftColor: theme.colors.border,
    paddingLeft: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
  },
  variantRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: theme.spacing.xs,
  },
  variantInfo: {
    flex: 1,
  },
  variantLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
    letterSpacing: 1,
  },
  variantDesc: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.textMuted,
  },
  strategyCountRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: theme.spacing.sm,
    paddingTop: theme.spacing.sm,
    borderTopWidth: 1,
    borderTopColor: theme.colors.border,
  },
  strategyCountLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
  },
  strategyCountValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    color: theme.colors.neonCyan,
    letterSpacing: 1,
  },
  // Broker
  brokerItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.sm,
    padding: theme.spacing.sm,
    marginBottom: theme.spacing.xs,
  },
  brokerItemActive: {
    borderColor: theme.colors.neonGreen,
    backgroundColor: 'rgba(57, 255, 20, 0.05)',
  },
  brokerInfo: {
    flex: 1,
  },
  brokerNameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  brokerName: {
    fontFamily: theme.fonts.primary,
    fontSize: 14,
    color: theme.colors.textWhite,
    letterSpacing: 1,
  },
  brokerNameDisabled: {
    color: theme.colors.textMuted,
  },
  brokerBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 3,
    borderWidth: 1,
  },
  brokerBadgeActive: {
    borderColor: theme.colors.neonGreen,
    backgroundColor: 'rgba(57, 255, 20, 0.1)',
  },
  brokerBadgeInactive: {
    borderColor: theme.colors.textMuted,
  },
  brokerBadgeText: {
    fontFamily: theme.fonts.primary,
    fontSize: 8,
    letterSpacing: 1,
  },
  brokerBadgeTextActive: {
    color: theme.colors.neonGreen,
  },
  brokerBadgeTextInactive: {
    color: theme.colors.textMuted,
  },
  brokerDesc: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    lineHeight: 16,
  },
  connectedBadge: {
    marginLeft: theme.spacing.sm,
  },
  connectedText: {
    fontFamily: theme.fonts.primary,
    fontSize: 9,
    color: theme.colors.neonGreen,
    letterSpacing: 1,
  },
  // Config rows (risk, hours)
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
  riskInput: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    color: theme.colors.neonCyan,
    borderBottomWidth: 1,
    borderBottomColor: theme.colors.neonCyan,
    paddingVertical: 2,
    paddingHorizontal: 6,
    minWidth: 60,
    textAlign: 'right',
  },
  profit: {
    color: theme.colors.profit,
  },
  loss: {
    color: theme.colors.loss,
  },
  // Engine card
  engineCard: {
    borderColor: theme.colors.neonCyan,
  },
  engineStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: theme.spacing.md,
  },
  engineStatusLabel: {
    fontFamily: theme.fonts.primary,
    fontSize: 12,
    color: theme.colors.textSecondary,
  },
  engineStatusBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: theme.borderRadius.round,
    borderWidth: 1,
  },
  engineOnline: {
    borderColor: theme.colors.neonGreen,
    backgroundColor: 'rgba(57, 255, 20, 0.1)',
  },
  engineOffline: {
    borderColor: theme.colors.neonRed,
    backgroundColor: 'rgba(255, 7, 58, 0.1)',
  },
  engineStatusText: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
  engineButtons: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: theme.spacing.md,
  },
  engineBtn: {
    flex: 1,
    paddingVertical: theme.spacing.sm + 4,
    borderRadius: theme.borderRadius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  startBtn: {
    backgroundColor: theme.colors.neonGreen,
  },
  startBtnText: {
    fontFamily: theme.fonts.heading,
    fontSize: 12,
    color: theme.colors.backgroundDark,
    letterSpacing: 2,
    fontWeight: 'bold',
  },
  stopBtn: {
    backgroundColor: theme.colors.backgroundLight,
    borderWidth: 1,
    borderColor: theme.colors.textMuted,
  },
  stopBtnText: {
    fontFamily: theme.fonts.heading,
    fontSize: 12,
    color: theme.colors.textWhite,
    letterSpacing: 2,
  },
  emergencyBtn: {
    backgroundColor: 'rgba(255, 7, 58, 0.15)',
    borderWidth: 1,
    borderColor: theme.colors.neonRed,
    borderRadius: theme.borderRadius.md,
    paddingVertical: theme.spacing.sm + 4,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emergencyBtnText: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.neonRed,
    letterSpacing: 2,
    fontWeight: 'bold',
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
  // Watchlist card
  cardSubtitle: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.sm,
    letterSpacing: 1,
  },
  watchlistRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1530',
  },
  watchlistCount: {
    fontFamily: theme.fonts.mono,
    fontSize: 11,
    color: '#8892a0',
    marginTop: 2,
  },
  totalInstruments: {
    marginTop: 12,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#2a2445',
    alignItems: 'center',
  },
  // Profile buttons
  profileBtn: {
    borderWidth: 1,
    borderRadius: theme.borderRadius.md,
    padding: theme.spacing.md,
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
  },
  profileBtnTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 13,
    letterSpacing: 2,
    marginBottom: 4,
  },
  profileBtnDesc: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 0.5,
    marginTop: 2,
  },
});
