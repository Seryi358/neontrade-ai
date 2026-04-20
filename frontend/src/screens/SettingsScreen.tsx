/**
 * Atlas - Settings Screen
 * Apple Liquid Glass system configuration.
 * Decomposed into 12 HUDCard sections with collapsible panels.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Alert,
  TextInput,
  Animated,
  Platform,
} from 'react-native';
import { theme } from '../theme/apple-glass';
import {
  HUDCard,
  HUDHeader,
  HUDSectionTitle,
  HUDStatRow,
  HUDDivider,
  HUDBadge,
  HUDProgressBar,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
import { api, API_URL, authFetch, setBackendUrl, resetBackendUrl, setApiKey, clearApiKey } from '../services/api';
import { useAlertSounds } from '../hooks/useAlertSounds';

// ── Types ──────────────────────────────────────────────

interface ModeData {
  mode: 'AUTO' | 'MANUAL';
}

interface BrokerData {
  broker: string;
  connected: boolean;
}

interface StrategyConfig {
  [key: string]: boolean;
}

// ── Constants ──────────────────────────────────────────

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
    color: '#3daee9',
    variants: [
      { key: 'BLUE_A', label: 'Tipo A', description: 'Doble suelo/techo' },
      { key: 'BLUE_B', label: 'Tipo B', description: 'Estandar' },
      { key: 'BLUE_C', label: 'Tipo C', description: 'Rechazo EMA 4H' },
    ],
  },
  { key: 'RED', label: 'RED', description: 'Cambio de tendencia 4H', color: '#fb3048', variants: [] },
  { key: 'PINK', label: 'PINK', description: 'Patron correctivo (Onda 4->5)', color: '#ee00ff', variants: [] },
  { key: 'WHITE', label: 'WHITE', description: 'Continuacion post-Pink', color: '#fcfcfc', variants: [] },
  { key: 'BLACK', label: 'BLACK', description: 'Contratendencia (min 2:1 R:R)', color: '#a1a9b1', variants: [] },
  { key: 'GREEN', label: 'GREEN', description: 'Semanal + Diario + 15M (hasta 10:1)', color: '#28c775', variants: [] },
];

const RISK_FIELDS = [
  { key: 'risk_day_trading', label: 'Day Trading', fmt: (v: number) => `${(v * 100).toFixed(1)}%`, isPercent: true },
  { key: 'risk_scalping', label: 'Scalping', fmt: (v: number) => `${(v * 100).toFixed(1)}%`, isPercent: true },
  { key: 'risk_swing', label: 'Swing', fmt: (v: number) => `${(v * 100).toFixed(1)}%`, isPercent: true },
  { key: 'max_total_risk', label: 'Max Total Risk', fmt: (v: number) => `${(v * 100).toFixed(1)}%`, isPercent: true },
  { key: 'correlated_risk_pct', label: 'Riesgo Correlacion', fmt: (v: number) => `${(v * 100).toFixed(2)}%`, isPercent: true },
  { key: 'min_rr_ratio', label: 'Min R:R', fmt: (v: number) => `1:${v.toFixed(2)}`, isPercent: false },
  { key: 'move_sl_to_be_pct_to_tp1', label: 'BE a % de TP1', fmt: (v: number) => `${(v * 100).toFixed(0)}%`, isPercent: true },
];

const WATCHLIST_CATEGORIES = [
  { key: 'forex', label: 'FOREX' },
  { key: 'forex_exotic', label: 'EXOTIC' },
  { key: 'commodities', label: 'COMMODITIES' },
  { key: 'indices', label: 'INDICES' },
  { key: 'equities', label: 'EQUITIES' },
  { key: 'crypto', label: 'CRYPTO' },
];

const _formatHours = (config: Record<string, number>) => [
  { label: 'London + NY', value: `${String(config.trading_start_hour ?? 7).padStart(2, '0')}:00 - ${String(config.trading_end_hour ?? 21).padStart(2, '0')}:00 UTC` },
  { label: 'Cierre Viernes', value: `${String(config.close_before_friday_hour ?? 20).padStart(2, '0')}:00 UTC` },
  { label: 'Sin Nuevas (Vie)', value: `${String(config.no_new_trades_friday_hour ?? 18).padStart(2, '0')}:00 UTC` },
  { label: 'Evitar Noticias', value: `${config.avoid_news_minutes_before ?? 30} min antes / ${config.avoid_news_minutes_after ?? 15} min después` },
];

// ── Safe localStorage helper (fixes crash on native) ───

function safeGetLocalStorage(key: string): string | null {
  if (Platform.OS === 'web') {
    try {
      return window.localStorage?.getItem(key) ?? null;
    } catch {
      return null;
    }
  }
  return null;
}

// ── Collapsible Section Component ──────────────────────

interface CollapsibleProps {
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  accentColor?: string;
}

function CollapsibleSection({ title, children, defaultOpen = false, accentColor = theme.colors.cp2077Yellow }: CollapsibleProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const animHeight = useRef(new Animated.Value(defaultOpen ? 1 : 0)).current;

  const toggle = () => {
    Animated.timing(animHeight, {
      toValue: isOpen ? 0 : 1,
      duration: 200,
      useNativeDriver: false,
    }).start();
    setIsOpen(!isOpen);
  };

  return (
    <HUDCard accentColor={accentColor}>
      <TouchableOpacity onPress={toggle} style={styles.collapsibleHeader} activeOpacity={0.7}>
        <HUDSectionTitle title={title} color={accentColor} />
        <Text style={[styles.collapseArrow, { color: accentColor }]}>
          {isOpen ? '\u25B2' : '\u25BC'}
        </Text>
      </TouchableOpacity>
      {isOpen && <View style={styles.collapsibleContent}>{children}</View>}
    </HUDCard>
  );
}

// ── iOS Toggle Switch (custom, works identically on web/iOS/Android) ──

interface IOSSwitchProps {
  value: boolean;
  onValueChange: (val: boolean) => void;
  disabled?: boolean;
  activeColor?: string;
}

function IOSSwitch({ value, onValueChange, disabled = false, activeColor = '#4CD964' }: IOSSwitchProps) {
  const animValue = React.useRef(new Animated.Value(value ? 1 : 0)).current;

  React.useEffect(() => {
    Animated.spring(animValue, {
      toValue: value ? 1 : 0,
      useNativeDriver: false,
      bounciness: 2,
      speed: 15,
    }).start();
  }, [value]);

  const trackBg = animValue.interpolate({
    inputRange: [0, 1],
    outputRange: ['#E5E5EA', activeColor],
  });

  const thumbX = animValue.interpolate({
    inputRange: [0, 1],
    outputRange: [2, 21],
  });

  return (
    <TouchableOpacity
      activeOpacity={0.8}
      onPress={() => !disabled && onValueChange(!value)}
      disabled={disabled}
      style={{ opacity: disabled ? 0.4 : 1 }}
    >
      <Animated.View
        style={{
          width: 51,
          height: 31,
          borderRadius: 15.5,
          backgroundColor: trackBg,
          justifyContent: 'center',
          padding: 0,
        }}
      >
        <Animated.View
          style={{
            width: 27,
            height: 27,
            borderRadius: 13.5,
            backgroundColor: '#FFFFFF',
            transform: [{ translateX: thumbX }],
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 2 },
            shadowOpacity: 0.2,
            shadowRadius: 2.5,
            elevation: 4,
          }}
        />
      </Animated.View>
    </TouchableOpacity>
  );
}

// ── Emergency Button with Pulsing Glow ─────────────────

function EmergencyButton({ onPress, loading }: { onPress: () => void; loading: boolean }) {
  const pulseAnim = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: false }),
        Animated.timing(pulseAnim, { toValue: 0.4, duration: 800, useNativeDriver: false }),
      ])
    );
    pulse.start();
    return () => pulse.stop();
  }, [pulseAnim]);

  return (
    <Animated.View style={[styles.emergencyGlowWrap, { shadowOpacity: pulseAnim }]}>
      <TouchableOpacity
        style={styles.emergencyBtn}
        onPress={onPress}
        disabled={loading}
        activeOpacity={0.7}
      >
        {loading ? (
          <ActivityIndicator size="small" color={theme.colors.textWhite} />
        ) : (
          <Text style={styles.emergencyBtnText}>EMERGENCY // CLOSE ALL POSITIONS</Text>
        )}
      </TouchableOpacity>
    </Animated.View>
  );
}

// ── Main Component ─────────────────────────────────────

export default function SettingsScreen() {
  // ── State ──────────────────────────────────────────
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
  const { soundEnabled, hapticEnabled, setSoundEnabled, setHapticEnabled } = useAlertSounds();
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
    const stored = safeGetLocalStorage('atlas_api_key');
    if (stored) return stored;
    if (Platform.OS === 'web') {
      try {
        const injected = (window as any).__ATLAS_API_KEY__;
        if (injected) return injected;
      } catch {}
    }
    return '';
  });
  const [editingApiKey, setEditingApiKey] = useState(false);
  const [apiKeyDraft, setApiKeyDraft] = useState('');
  const [securityStatus, setSecurityStatus] = useState<any>(null);
  const [watchlistCategories, setWatchlistCategories] = useState<string[]>(['forex']);
  const [watchlistInfo, setWatchlistInfo] = useState<any>(null);

  // ── Data Fetching ──────────────────────────────────

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

  // ── Actions ────────────────────────────────────────

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
      `Se aplicara el perfil "${profileName}". Esto cambiara multiples ajustes (riesgo, estilo, watchlists, gestion de posicion). Continuar?`,
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

    if (!value) {
      const strat = STRATEGIES.find((s) => s.key === key);
      if (strat?.variants?.length) {
        for (const v of strat.variants) {
          newConfig[v.key] = false;
        }
      }
    }

    if (value) {
      const strat = STRATEGIES.find((s) => s.key === key);
      if (strat?.variants?.length) {
        for (const v of strat.variants) {
          newConfig[v.key] = true;
        }
      }
    }

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
      if (updated.length === 0) return;
      await api.updateWatchlistCategories(updated);
      setWatchlistCategories(updated);
    } catch (_e: any) {
      // handle error silently
    }
  };

  const runDiagnostic = async () => {
    setActionLoading('diagnostic');
    try {
      const res = await authFetch(`${API_URL}/api/v1/diagnostic`);
      if (res.ok) {
        const data = await res.json();
        const stepLines = (data.steps || []).map((s: any) =>
          `${s.ok ? '\u2713' : '\u2717'} ${s.step}: ${s.detail}${s.sample ? '\n  ' + JSON.stringify(s.sample).slice(0, 200) : ''}`
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
  };

  // ── Loading / Error States ─────────────────────────

  if (loading) {
    return (
      <View style={styles.centered}>
        <LoadingState message="CARGANDO CONFIGURACION..." />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.centered}>
        <ErrorState message={error} onRetry={fetchData} />
      </View>
    );
  }

  // ── Render ─────────────────────────────────────────

  return (
    <ScrollView
      style={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={onRefresh}
          tintColor={theme.colors.cp2077Yellow}
        />
      }
    >
      {/* ═══ 1. HUD Header ═══════════════════════════════ */}
      <HUDHeader
        title="SYSTEM CONFIGURATION"
        subtitle="// SYS"
      />

      {/* ═══ 2. Mode Control Card ════════════════════════ */}
      <HUDCard accentColor={theme.colors.cp2077Yellow}>
        <HUDSectionTitle title="MODE CONTROL" color={theme.colors.cp2077Yellow} />

        <View style={styles.modeRow}>
          <View style={styles.modeInfo}>
            <View style={[
              styles.modeIndicator,
              { backgroundColor: mode === 'AUTO' ? theme.colors.cp2077Yellow : theme.colors.textMuted },
            ]} />
            <Text style={[
              styles.modeLabel,
              { color: mode === 'AUTO' ? theme.colors.cp2077Yellow : theme.colors.textMuted },
            ]}>
              {mode}
            </Text>
          </View>
          <IOSSwitch
            value={mode === 'AUTO'}
            onValueChange={toggleMode}
            disabled={actionLoading === 'mode'}
            activeColor={theme.colors.cp2077Yellow}
          />
        </View>
        <Text style={styles.modeDescription}>
          {mode === 'AUTO'
            ? 'Atlas opera automaticamente basado en las estrategias detectadas'
            : 'Atlas te sugiere operaciones y tu decides si ejecutar o no'
          }
        </Text>

        <HUDDivider />

        {/* Trading Profile Selector */}
        <Text style={styles.hintText}>
          Presets de configuracion con valores recomendados por TradingLab
        </Text>

        <TouchableOpacity
          style={[styles.profileBtn, { borderColor: theme.colors.neonCyan }]}
          onPress={() => applyProfile('tradinglab_recommended', 'TradingLab Recommended')}
          disabled={actionLoading === 'profile'}
          activeOpacity={0.7}
        >
          {actionLoading === 'profile' ? (
            <ActivityIndicator size="small" color={theme.colors.neonCyan} />
          ) : (
            <>
              <Text style={[styles.profileBtnTitle, { color: theme.colors.neonCyan }]}>
                TRADINGLAB RECOMMENDED
              </Text>
              <Text style={styles.profileBtnDesc}>
                Day Trading - 1% riesgo - R:R 1.5:1 - Salida rapida - Sin parciales - BE al 1%
              </Text>
            </>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.profileBtn, styles.profileBtnSpacing, { borderColor: theme.colors.neonGreen }]}
          onPress={() => applyProfile('conservative', 'Conservative')}
          disabled={actionLoading === 'profile'}
          activeOpacity={0.7}
        >
          {actionLoading === 'profile' ? (
            <ActivityIndicator size="small" color={theme.colors.neonGreen} />
          ) : (
            <>
              <Text style={[styles.profileBtnTitle, { color: theme.colors.neonGreen }]}>
                CONSERVATIVE
              </Text>
              <Text style={styles.profileBtnDesc}>
                Swing Trading - 1% riesgo - R:R 2.0:1 - Trailing amplio (LP)
              </Text>
            </>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.applyBtn}
          onPress={onRefresh}
          activeOpacity={0.7}
        >
          <Text style={styles.applyBtnText}>REFRESH CONFIG</Text>
        </TouchableOpacity>
      </HUDCard>

      {/* ═══ 3. Strategy Module Card ═════════════════════ */}
      <HUDCard accentColor={theme.colors.neonCyan}>
        <HUDSectionTitle title="STRATEGY MODULE" color={theme.colors.neonCyan} />
        <Text style={styles.hintText}>
          TradingLab recommends starting with BLUE + RED only
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
              <IOSSwitch
                value={strategyConfig[strat.key] ?? true}
                onValueChange={(val) => toggleStrategy(strat.key, val)}
                activeColor={strat.color}
              />
            </View>
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
                    <IOSSwitch
                      value={strategyConfig[variant.key] ?? true}
                      onValueChange={(val) => toggleStrategy(variant.key, val)}
                      activeColor={strat.color}
                    />
                  </View>
                ))}
              </View>
            )}
          </View>
        ))}

        <HUDDivider />
        <View style={styles.strategyCountRow}>
          <Text style={styles.strategyCountLabel}>Estrategias activas:</Text>
          <Text style={styles.strategyCountValue}>
            {STRATEGIES.filter((s) => strategyConfig[s.key]).length} / {STRATEGIES.length}
          </Text>
        </View>
      </HUDCard>

      {/* ═══ 4. Risk Parameters Card ═════════════════════ */}
      <HUDCard accentColor={theme.colors.neonOrange}>
        <HUDSectionTitle title="RISK PARAMETERS" color={theme.colors.neonOrange} />
        <Text style={styles.hintText}>Toca un valor para editarlo</Text>

        {RISK_FIELDS.map((item) => (
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
                setEditValue(item.isPercent ? (val * 100).toFixed(1) : val?.toFixed(2) || '0');
                setEditingRisk(item.key);
              }}>
                <Text style={[styles.configValue, { color: theme.colors.neonCyan }]}>
                  {riskConfig[item.key] !== undefined ? item.fmt(riskConfig[item.key]) : '---'}
                </Text>
              </TouchableOpacity>
            )}
          </View>
        ))}
      </HUDCard>

      {/* ═══ 5. Trading Hours Card ═══════════════════════ */}
      <HUDCard>
        <HUDSectionTitle title="TRADING HOURS" />
        {_formatHours(riskConfig).map((item, index) => (
          <HUDStatRow
            key={index}
            label={item.label}
            value={item.value}
            valueColor={theme.colors.textWhite}
          />
        ))}
      </HUDCard>

      {/* ═══ 6. Scalping Module Card (collapsible) ═══════ */}
      <CollapsibleSection title="SCALPING MODULE" accentColor={theme.colors.neonYellow}>
        <View style={styles.modeRow}>
          <View style={styles.modeInfo}>
            <View style={[
              styles.modeIndicator,
              { backgroundColor: scalpingEnabled ? theme.colors.neonYellow : theme.colors.textMuted },
            ]} />
            <Text style={[styles.subModeLabel, { color: scalpingEnabled ? theme.colors.neonYellow : theme.colors.textMuted }]}>
              {scalpingEnabled ? 'ACTIVO' : 'INACTIVO'}
            </Text>
          </View>
          <IOSSwitch
            value={scalpingEnabled}
            onValueChange={toggleScalping}
            disabled={actionLoading === 'scalping'}
            activeColor={theme.colors.neonYellow}
          />
        </View>

        <Text style={styles.hintText}>
          {'Workshop de Scalping -- Temporalidades comprimidas H1->M15->M5->M1'}
        </Text>

        {scalpingEnabled && scalpingStatus && (
          <View style={styles.collapsibleDetails}>
            <HUDStatRow label="Riesgo/Trade" value="0.5%" valueColor={theme.colors.textWhite} />
            <HUDStatRow label="DD Diario Max" value="5%" valueColor={theme.colors.neonYellow} />
            <HUDStatRow label="DD Total Max" value="10%" valueColor={theme.colors.neonYellow} />
            <HUDStatRow label="Intervalo Scan" value="30s" valueColor={theme.colors.textWhite} />
            <HUDDivider />
            <Text style={styles.mappingText}>
              {'MAPEO: D->H1 | H4->M15 | H1->M5 | M5->M1'}
            </Text>
          </View>
        )}
      </CollapsibleSection>

      {/* ═══ 7. Funded Account Card (collapsible) ════════ */}
      <CollapsibleSection title="FUNDED ACCOUNT" accentColor={theme.colors.neonOrange}>
        <View style={styles.modeRow}>
          <View style={styles.modeInfo}>
            <View style={[
              styles.modeIndicator,
              { backgroundColor: fundedEnabled ? theme.colors.neonOrange : theme.colors.textMuted },
            ]} />
            <Text style={[styles.subModeLabel, { color: fundedEnabled ? theme.colors.neonOrange : theme.colors.textMuted }]}>
              {fundedEnabled ? 'ACTIVO' : 'INACTIVO'}
            </Text>
          </View>
          <IOSSwitch
            value={fundedEnabled}
            onValueChange={toggleFunded}
            disabled={actionLoading === 'funded'}
            activeColor={theme.colors.neonOrange}
          />
        </View>

        <Text style={styles.hintText}>
          Workshop Cuentas Fondeadas -- Limites estrictos de drawdown
        </Text>

        {fundedEnabled && fundedStatus && (
          <View style={styles.collapsibleDetails}>
            <HUDStatRow
              label="Tipo Cuenta"
              value={(fundedStatus.account_type || 'swing').toUpperCase()}
              valueColor={theme.colors.neonCyan}
            />
            <HUDStatRow
              label="Evaluacion"
              value={`${(fundedStatus.evaluation_type || '2phase').toUpperCase()} -- Fase ${fundedStatus.current_phase || 1}`}
              valueColor={theme.colors.neonCyan}
            />
            <HUDStatRow
              label="DD Diario Max"
              value={`${(fundedStatus.daily_dd_limit || 5).toFixed(0)}%`}
              valueColor={theme.colors.neonOrange}
            />
            <HUDStatRow
              label="DD Diario Usado"
              value={`${(fundedStatus.daily_dd_used_pct || 0).toFixed(1)}%`}
              valueColor={(fundedStatus.daily_dd_used_pct || 0) > 60 ? theme.colors.loss : theme.colors.profit}
            />
            <HUDStatRow
              label="DD Total Max"
              value={`${(fundedStatus.total_dd_limit || 10).toFixed(0)}%`}
              valueColor={theme.colors.neonOrange}
            />
            <HUDStatRow
              label="DD Total Actual"
              value={`${(fundedStatus.total_dd_pct || 0).toFixed(2)}%`}
              valueColor={(fundedStatus.total_dd_pct || 0) > 5 ? theme.colors.loss : theme.colors.profit}
            />
            {(fundedStatus.profit_target_pct || 0) > 0 && (
              <HUDProgressBar
                label="Objetivo Profit"
                value={(fundedStatus.profit_progress_pct || 0)}
                maxLabel={`${(fundedStatus.profit_target_pct || 0).toFixed(0)}%`}
                color={theme.colors.neonGreen}
              />
            )}
            <HUDDivider />
            <HUDStatRow label="No Overnight" value={fundedStatus.no_overnight ? 'Si' : 'No'} />
            <HUDStatRow label="No News Trading" value={fundedStatus.no_news_trading ? 'Si' : 'No'} />
            <HUDStatRow label="No Weekend" value={fundedStatus.no_weekend ? 'Si' : 'No'} />
          </View>
        )}
      </CollapsibleSection>

      {/* ═══ 8. Broker Selection Card ════════════════════ */}
      <HUDCard accentColor={theme.colors.neonGreen}>
        <HUDSectionTitle title="BROKER SELECTION" color={theme.colors.neonGreen} />

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
                <HUDBadge
                  label={b.badge}
                  color={b.active ? theme.colors.neonGreen : theme.colors.textMuted}
                  small
                />
              </View>
              <Text style={styles.brokerDesc}>{b.description}</Text>
            </View>
            {broker?.broker === b.id && broker?.connected && (
              <Text style={styles.connectedText}>CONECTADO</Text>
            )}
          </View>
        ))}

        <HUDDivider />
        <TouchableOpacity
          style={styles.diagnosticBtn}
          onPress={runDiagnostic}
          disabled={actionLoading === 'diagnostic'}
          activeOpacity={0.7}
        >
          {actionLoading === 'diagnostic' ? (
            <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
          ) : (
            <Text style={styles.diagnosticBtnText}>EJECUTAR DIAGNOSTICO</Text>
          )}
        </TouchableOpacity>
      </HUDCard>

      {/* ═══ 9. Watchlist Categories Card ════════════════ */}
      <HUDCard>
        <HUDSectionTitle title="WATCHLIST CATEGORIES" />
        <Text style={styles.hintText}>Categorias de instrumentos del curso TradingLab</Text>

        <View style={styles.chipContainer}>
          {WATCHLIST_CATEGORIES.map((cat) => {
            const isActive = watchlistCategories.includes(cat.key);
            const info = watchlistInfo?.[cat.key];
            return (
              <TouchableOpacity
                key={cat.key}
                style={[
                  styles.chip,
                  isActive && styles.chipActive,
                ]}
                onPress={() => toggleWatchlistCategory(cat.key)}
                activeOpacity={0.7}
              >
                <Text style={[
                  styles.chipText,
                  isActive && styles.chipTextActive,
                ]}>
                  {cat.label}
                </Text>
                <Text style={[
                  styles.chipCount,
                  isActive && styles.chipCountActive,
                ]}>
                  {info?.count || 0}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <HUDDivider />
        <HUDStatRow
          label="Total activo"
          value={`${watchlistCategories.reduce((sum: number, cat: string) =>
            sum + (watchlistInfo?.[cat]?.count || 0), 0)} instrumentos`}
          valueColor={theme.colors.neonCyan}
        />
      </HUDCard>

      {/* ═══ 10. Notifications Card (collapsible) ════════ */}
      <CollapsibleSection title="NOTIFICATIONS" accentColor={theme.colors.neonMagenta}>
        <Text style={styles.hintText}>
          Se activan automaticamente cuando las credenciales estan en las variables de entorno
        </Text>

        {[
          { key: 'telegram_enabled', label: 'Telegram' },
          { key: 'discord_enabled', label: 'Discord' },
          { key: 'email_enabled', label: 'Email SMTP' },
          { key: 'gmail_enabled', label: 'Gmail OAuth2' },
        ].map((ch) => (
          <View key={ch.key} style={styles.configRow}>
            <Text style={styles.configLabel}>{ch.label}</Text>
            <Text style={[
              styles.configValue,
              { color: alertConfig[ch.key] ? theme.colors.profit : theme.colors.loss },
            ]}>
              {alertConfig[ch.key] ? 'ACTIVO' : 'INACTIVO'}
            </Text>
          </View>
        ))}

        {(alertConfig.telegram_enabled || alertConfig.discord_enabled || alertConfig.email_enabled || alertConfig.gmail_enabled) && (
          <>
            <HUDDivider />
            <HUDStatRow
              label="Trades ejecutados"
              value={alertConfig.notify_trade_executed ? 'Si' : 'No'}
              valueColor={theme.colors.textSecondary}
            />
            <HUDStatRow
              label="Setups pendientes"
              value={alertConfig.notify_setup_pending ? 'Si' : 'No'}
              valueColor={theme.colors.textSecondary}
            />
            <HUDStatRow
              label="Trades cerrados"
              value={alertConfig.notify_trade_closed ? 'Si' : 'No'}
              valueColor={theme.colors.textSecondary}
            />
          </>
        )}

        <HUDDivider />
        <HUDSectionTitle title="ALERTAS LOCALES (SETUP)" color={theme.colors.neonMagenta} />

        <View style={styles.localAlertRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.localAlertLabel}>Sonido en setup</Text>
            <Text style={styles.localAlertHint}>Chime corto al llegar un setup nuevo</Text>
          </View>
          <IOSSwitch value={soundEnabled} onValueChange={setSoundEnabled} />
        </View>
        <View style={styles.localAlertRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.localAlertLabel}>Vibración en setup</Text>
            <Text style={styles.localAlertHint}>Háptica doble al detectar setup</Text>
          </View>
          <IOSSwitch value={hapticEnabled} onValueChange={setHapticEnabled} />
        </View>
      </CollapsibleSection>

      {/* ═══ 11. Engine Control Card ═════════════════════ */}
      <HUDCard accentColor={engineRunning ? theme.colors.neonGreen : theme.colors.neonRed} borderColor={engineRunning ? theme.colors.neonGreen : theme.colors.neonRed}>
        <HUDSectionTitle title="ENGINE CONTROL" color={theme.colors.neonCyan} />

        <View style={styles.engineStatusRow}>
          <Text style={styles.engineStatusLabel}>Estado:</Text>
          <HUDBadge
            label={engineRunning ? 'ACTIVO' : 'DETENIDO'}
            color={engineRunning ? theme.colors.neonGreen : theme.colors.neonRed}
          />
        </View>

        {/* Connection status inline */}
        <View style={styles.connectionBlock}>
          <HUDStatRow
            label="Motor"
            value={engineRunning ? 'Ejecutando' : 'Detenido'}
            valueColor={engineRunning ? theme.colors.profit : theme.colors.loss}
          />
          <HUDStatRow
            label="Broker"
            value={broker?.connected ? 'Conectado' : 'Desconectado'}
            valueColor={broker?.connected ? theme.colors.profit : theme.colors.loss}
          />
          {engineStatus?.scanned_instruments != null && (
            <HUDStatRow
              label="Escaneados"
              value={`${engineStatus.scanned_instruments}/${engineStatus.watchlist_count || 0}`}
              valueColor={theme.colors.textWhite}
            />
          )}
          <HUDStatRow label="API" value="Activa" valueColor={theme.colors.profit} />
        </View>

        {engineStatus?.startup_error && (
          <View style={styles.errorBlock}>
            <Text style={styles.errorBlockTitle}>ERROR DE CONEXION</Text>
            <Text style={styles.errorBlockMsg} numberOfLines={3}>
              {engineStatus.startup_error}
            </Text>
            <TouchableOpacity onPress={startEngine} activeOpacity={0.7}>
              <Text style={styles.errorRetryLink}>REINTENTAR CONEXION</Text>
            </TouchableOpacity>
          </View>
        )}

        <HUDDivider />

        <View style={styles.engineButtons}>
          <TouchableOpacity
            style={[styles.engineBtn, styles.startBtn, engineRunning && styles.btnDisabled]}
            onPress={startEngine}
            disabled={engineRunning || actionLoading === 'start'}
            activeOpacity={0.7}
          >
            {actionLoading === 'start' ? (
              <ActivityIndicator size="small" color={theme.colors.backgroundDark} />
            ) : (
              <Text style={styles.startBtnText}>INICIAR ENGINE</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.engineBtn, styles.stopBtn, !engineRunning && styles.btnDisabled]}
            onPress={stopEngine}
            disabled={!engineRunning || actionLoading === 'stop'}
            activeOpacity={0.7}
          >
            {actionLoading === 'stop' ? (
              <ActivityIndicator size="small" color={theme.colors.textWhite} />
            ) : (
              <Text style={styles.stopBtnText}>DETENER ENGINE</Text>
            )}
          </TouchableOpacity>
        </View>

        <EmergencyButton
          onPress={emergencyCloseAll}
          loading={actionLoading === 'emergency'}
        />
      </HUDCard>

      {/* ═══ 12. System Info Card ════════════════════════ */}
      <HUDCard accentColor={theme.colors.textMuted}>
        <HUDSectionTitle title="SYSTEM INFO" color={theme.colors.textMuted} />

        {/* Backend URL */}
        <View style={styles.configRow}>
          <Text style={styles.configLabel}>Backend URL</Text>
          {editingBackendUrl ? (
            <View style={styles.inlineEditRow}>
              <TextInput
                style={styles.inlineEditInput}
                value={backendUrlDraft}
                onChangeText={setBackendUrlDraft}
                autoCapitalize="none"
                autoCorrect={false}
                placeholder="https://atlas.tu-vps.com"
                placeholderTextColor={theme.colors.textMuted}
              />
              <TouchableOpacity
                style={styles.inlineEditOk}
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
                <Text style={styles.inlineEditOkText}>OK</Text>
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
            style={styles.resetLink}
            onPress={() => {
              resetBackendUrl();
              setBackendUrlState('http://localhost:8000');
              setEditingBackendUrl(false);
              Alert.alert('Backend', 'Restaurado a localhost. Reinicia la app.');
            }}
          >
            <Text style={styles.resetLinkText}>Restaurar a localhost</Text>
          </TouchableOpacity>
        )}

        <HUDDivider />

        {/* API Key */}
        <Text style={styles.sysInfoLabel}>API KEY</Text>
        <Text style={styles.sysInfoHint}>
          {securityStatus && !securityStatus.auth_enabled
            ? 'Autenticacion deshabilitada en el servidor'
            : securityStatus && securityStatus.api_keys_count === 0
              ? 'Acceso abierto (sin keys configuradas) -- primera ejecucion'
              : 'Requerida para conectar al servidor remoto'}
        </Text>

        {securityStatus && (
          <View style={styles.authStatusRow}>
            <View style={[
              styles.authDot,
              {
                backgroundColor: !securityStatus.auth_enabled || securityStatus.api_keys_count === 0
                  ? theme.colors.neonGreen : apiKeyValue ? theme.colors.neonGreen : theme.colors.cp2077Yellow,
              },
            ]} />
            <Text style={styles.authStatusText}>
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
            <View style={styles.inlineEditRow}>
              <TextInput
                style={[styles.inlineEditInput, styles.inlineEditInputSmall]}
                value={apiKeyDraft}
                onChangeText={setApiKeyDraft}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry={false}
                placeholder="nt_..."
                placeholderTextColor={theme.colors.textMuted}
              />
              <TouchableOpacity
                style={styles.inlineEditOk}
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
                <Text style={styles.inlineEditOkText}>OK</Text>
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
            style={styles.resetLink}
            onPress={() => {
              clearApiKey();
              setApiKeyValue('');
              setEditingApiKey(false);
              Alert.alert('API Key', 'Key eliminada.');
            }}
          >
            <Text style={styles.resetLinkText}>Eliminar Key</Text>
          </TouchableOpacity>
        ) : null}

        <HUDDivider />

        {/* Version */}
        <HUDStatRow label="Version" value="Atlas v3.0" valueColor={theme.colors.textMuted} />
      </HUDCard>

      <View style={styles.bottomSpacer} />
    </ScrollView>
  );
}

// ── Styles ──────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
    padding: 16,
  },
  centered: {
    flex: 1,
    backgroundColor: '#f2f2f7',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  bottomSpacer: {
    height: 32,
  },

  // ── Local alert rows (sound + haptic) ─────────────
  localAlertRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    gap: 12,
  },
  localAlertLabel: {
    fontFamily: theme.fonts.semibold,
    fontSize: 14,
    fontWeight: '600',
    color: theme.colors.textPrimary,
  },
  localAlertHint: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textSecondary,
    marginTop: 2,
  },

  // ── Collapsible ────────────────────────────────────
  collapsibleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  collapseArrow: {
    fontSize: 12,
    marginTop: -8,
  },
  collapsibleContent: {
    marginTop: 8,
  },
  collapsibleDetails: {
    marginTop: 8,
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.04)',
    paddingTop: 8,
  },

  // ── Mode Control ───────────────────────────────────
  modeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
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
    fontSize: 22,
    fontWeight: '700',
    letterSpacing: -0.3,
  },
  subModeLabel: {
    fontSize: 16,
    fontWeight: '600',
  },
  modeDescription: {
    fontSize: 13,
    color: '#aeaeb2',
    lineHeight: 20,
  },
  hintText: {
    fontSize: 12,
    color: '#aeaeb2',
    marginBottom: 8,
  },

  // ── Profile Buttons ────────────────────────────────
  profileBtn: {
    borderWidth: 1,
    borderRadius: 14,
    padding: 16,
    backgroundColor: '#f9f9f9',
    borderColor: 'rgba(0,0,0,0.04)',
  },
  profileBtnSpacing: {
    marginTop: 8,
  },
  profileBtnTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  profileBtnDesc: {
    fontSize: 12,
    color: '#aeaeb2',
    marginTop: 2,
  },
  applyBtn: {
    backgroundColor: '#007AFF',
    borderRadius: 12,
    paddingVertical: 10,
    alignItems: 'center',
    marginTop: 16,
  },
  applyBtnText: {
    fontSize: 14,
    color: '#ffffff',
    fontWeight: '600',
  },

  // ── Strategy ───────────────────────────────────────
  strategyRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
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
    fontSize: 15,
    fontWeight: '500',
    color: '#1d1d1f',
  },
  strategyLabelDisabled: {
    color: '#aeaeb2',
  },
  strategyDesc: {
    fontSize: 12,
    color: '#aeaeb2',
    marginTop: 1,
  },
  variantContainer: {
    marginLeft: 38,
    borderLeftWidth: 1,
    borderLeftColor: 'rgba(0,0,0,0.04)',
    paddingLeft: 8,
    marginBottom: 4,
  },
  variantRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  variantInfo: {
    flex: 1,
  },
  variantLabel: {
    fontSize: 14,
    color: '#86868b',
  },
  variantDesc: {
    fontSize: 11,
    color: '#aeaeb2',
  },
  strategyCountRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  strategyCountLabel: {
    fontSize: 13,
    color: '#aeaeb2',
  },
  strategyCountValue: {
    fontSize: 14,
    fontWeight: '600',
    color: '#007AFF',
  },

  // ── Config Rows (risk, etc.) ───────────────────────
  configRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.04)',
  },
  configLabel: {
    fontSize: 14,
    color: '#86868b',
  },
  configValue: {
    fontSize: 14,
    fontWeight: '500',
    color: '#1d1d1f',
  },
  riskInput: {
    fontSize: 14,
    color: '#007AFF',
    borderBottomWidth: 1,
    borderBottomColor: '#007AFF',
    paddingVertical: 2,
    paddingHorizontal: 6,
    minWidth: 60,
    textAlign: 'right',
  },

  // ── Mapping text ───────────────────────────────────
  mappingText: {
    fontSize: 11,
    color: '#aeaeb2',
  },

  // ── Broker ─────────────────────────────────────────
  brokerItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderRadius: 14,
    padding: 12,
    marginBottom: 4,
    backgroundColor: '#f9f9f9',
  },
  brokerItemActive: {
    backgroundColor: 'rgba(52,199,89,0.06)',
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
    fontSize: 15,
    fontWeight: '500',
    color: '#1d1d1f',
  },
  brokerNameDisabled: {
    color: '#aeaeb2',
  },
  brokerDesc: {
    fontSize: 12,
    color: '#aeaeb2',
    lineHeight: 18,
  },
  connectedText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#34C759',
    marginLeft: 8,
  },
  diagnosticBtn: {
    backgroundColor: '#007AFF',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 8,
    alignSelf: 'flex-start',
  },
  diagnosticBtnText: {
    fontSize: 13,
    color: '#ffffff',
    fontWeight: '600',
  },

  // ── Watchlist Chips ────────────────────────────────
  chipContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginVertical: 8,
  },
  chip: {
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: '#f9f9f9',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  chipActive: {
    backgroundColor: 'rgba(0,122,255,0.08)',
  },
  chipText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#aeaeb2',
  },
  chipTextActive: {
    color: '#007AFF',
  },
  chipCount: {
    fontSize: 11,
    color: '#aeaeb2',
  },
  chipCountActive: {
    color: '#007AFF',
  },

  // ── Engine ─────────────────────────────────────────
  engineStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 16,
  },
  engineStatusLabel: {
    fontSize: 14,
    color: '#86868b',
  },
  connectionBlock: {
    marginBottom: 8,
  },
  errorBlock: {
    marginTop: 8,
    padding: 12,
    backgroundColor: 'rgba(255,59,48,0.06)',
    borderRadius: 14,
  },
  errorBlockTitle: {
    fontSize: 12,
    fontWeight: '600',
    color: '#FF3B30',
    marginBottom: 4,
  },
  errorBlockMsg: {
    fontSize: 12,
    color: '#86868b',
  },
  errorRetryLink: {
    fontSize: 13,
    fontWeight: '600',
    color: '#007AFF',
    marginTop: 6,
  },
  engineButtons: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 16,
  },
  engineBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  startBtn: {
    backgroundColor: '#34C759',
  },
  startBtnText: {
    fontSize: 14,
    color: '#ffffff',
    fontWeight: '600',
  },
  stopBtn: {
    backgroundColor: '#f9f9f9',
    borderWidth: 1,
    borderColor: 'rgba(0,0,0,0.06)',
  },
  stopBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1d1d1f',
  },
  btnDisabled: {
    opacity: 0.4,
  },

  // ── Emergency Button ───────────────────────────────
  emergencyGlowWrap: {
    shadowColor: '#FF3B30',
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
    shadowOpacity: 0.15,
    elevation: 6,
    borderRadius: 12,
  },
  emergencyBtn: {
    backgroundColor: 'rgba(255,59,48,0.08)',
    borderWidth: 1,
    borderColor: '#FF3B30',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emergencyBtnText: {
    fontSize: 14,
    color: '#FF3B30',
    fontWeight: '600',
  },

  // ── System Info ────────────────────────────────────
  inlineEditRow: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    justifyContent: 'flex-end',
  },
  inlineEditInput: {
    fontSize: 13,
    color: '#007AFF',
    borderBottomWidth: 1,
    borderBottomColor: '#007AFF',
    minWidth: 180,
    textAlign: 'right',
    paddingVertical: 2,
    paddingHorizontal: 4,
  },
  inlineEditInputSmall: {
    minWidth: 200,
    fontSize: 12,
  },
  inlineEditOk: {
    marginLeft: 8,
    backgroundColor: '#007AFF',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  inlineEditOkText: {
    fontSize: 13,
    color: '#ffffff',
    fontWeight: '600',
  },
  resetLink: {
    marginTop: 8,
    alignSelf: 'flex-end',
  },
  resetLinkText: {
    fontSize: 13,
    color: '#007AFF',
  },
  sysInfoLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: '#86868b',
    marginBottom: 4,
  },
  sysInfoHint: {
    fontSize: 13,
    color: '#aeaeb2',
    marginBottom: 8,
  },
  authStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  authDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    marginRight: 6,
  },
  authStatusText: {
    fontSize: 12,
    fontWeight: '500',
    color: '#86868b',
  },
});
