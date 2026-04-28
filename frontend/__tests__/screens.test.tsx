/**
 * NeonTrade AI - Frontend Screen Tests
 * Verifies that all 8 screens render correctly with mocked API data.
 *
 * Strategy: Mock global fetch (used by authFetch) to return realistic data,
 * then render each screen and verify key elements are present.
 */

import React from 'react';
import { render, waitFor } from '@testing-library/react-native';

// ── Mock API module ─────────────────────────────────────────────
jest.mock('../src/services/api', () => {
  const actual = jest.requireActual('../src/services/api');
  return {
    ...actual,
    API_URL: 'http://test-api:8000',
    WS_URL: 'ws://test-api:8000/ws',
    authFetch: jest.fn(),
    wsManager: {
      connect: jest.fn(),
      disconnect: jest.fn(),
      on: jest.fn(() => jest.fn()),
      send: jest.fn(),
      connected: false,
    },
    api: {
      getStatus: jest.fn(),
      getAccount: jest.fn(),
      getWatchlist: jest.fn(),
      getAnalysis: jest.fn(),
      getCandles: jest.fn(),
      getPrice: jest.fn(),
      getPendingSetups: jest.fn(),
      approveSetup: jest.fn(),
      rejectSetup: jest.fn(),
      getHistory: jest.fn(),
      getPerformanceStats: jest.fn(),
      getMode: jest.fn(),
      getBroker: jest.fn(),
      startEngine: jest.fn(),
      stopEngine: jest.fn(),
      getStrategies: jest.fn(),
      getSecurityStatus: jest.fn(),
      getWatchlistCategories: jest.fn(),
      getTradeScreenshots: jest.fn(),
      getMonthlyReview: jest.fn(),
      markTradeDiscretionary: jest.fn(),
    },
  };
});

jest.mock('@react-navigation/native', () => ({
  ...jest.requireActual('@react-navigation/native'),
  useNavigation: () => ({ navigate: jest.fn(), goBack: jest.fn() }),
  useRoute: () => ({ params: {} }),
  useFocusEffect: (cb: () => any) => {
    const React = require('react');
    React.useEffect(() => {
      const cleanup = cb();
      return typeof cleanup === 'function' ? cleanup : undefined;
    }, []);
  },
}));

jest.mock('react-native/Libraries/Alert/Alert', () => ({
  alert: jest.fn(),
}));

jest.mock('react-native/Libraries/Linking/Linking', () => ({
  openURL: jest.fn().mockResolvedValue(true),
  canOpenURL: jest.fn().mockResolvedValue(true),
}));

import { authFetch, wsManager } from '../src/services/api';
const mockAuthFetch = authFetch as jest.MockedFunction<typeof authFetch>;

// ── Test data ───────────────────────────────────────────────────

function mockJsonResponse(data: any, ok = true) {
  return Promise.resolve({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  } as Response);
}

const MOCK_ACCOUNT = {
  balance: 10000,
  equity: 10150,
  unrealized_pnl: 150,
  open_trade_count: 2,
  currency: 'USD',
};

const MOCK_STATUS = {
  running: true,
  mode: 'AUTO',
  broker: 'capital',
  open_positions: 2,
  pending_setups: 0,
  total_risk: 1.5,
  watchlist_count: 11,
  positions: [
    {
      instrument: 'EUR_USD',
      direction: 'BUY',
      entry_price: 1.0850,
      current_sl: 1.0820,
      take_profit: 1.0910,
      phase: 'TRAILING',
      strategy: 'BLUE',
    },
  ],
  daily_activity: {
    scans_completed: 45,
    setups_found: 3,
    setups_executed: 2,
    setups_filtered: 1,
    errors: 0,
  },
};

const MOCK_RISK_CONFIG = { max_total_risk: 7.0 };

const MOCK_RISK_STATUS = {
  current_drawdown: 0.5,
  peak_balance: 10200,
  current_balance: 10000,
  recovery_pct_needed: 0.51,
  loss_dollars: 200,
  dd_alert_level: null,
  recovery_table: [[5, 5.26], [10, 11.11], [20, 25.0], [30, 42.86], [50, 100.0]],
  max_total_risk: 7.0,
  adjusted_risk_day: 1.0,
};

const MOCK_WATCHLIST = [
  { instrument: 'EUR_USD', score: 75, trend: 'BULLISH', convergence: true, strategy_detected: 'BLUE', confidence_level: 'ALTA' },
  { instrument: 'GBP_USD', score: 42, trend: 'BEARISH', convergence: false, strategy_detected: null, confidence_level: null },
  { instrument: 'USD_JPY', score: 60, trend: 'NEUTRAL', convergence: false, condition: 'OVERBOUGHT', strategy_detected: 'RED', confidence_level: 'MEDIA' },
];

const MOCK_ANALYSIS = {
  instrument: 'EUR_USD',
  score: 78,
  confidence: 'ALTA',
  htf_trend: 'BULLISH',
  ltf_trend: 'BULLISH',
  convergence: true,
  timeframes: [
    {
      timeframe: 'D',
      trend: 'BULLISH',
      observations: ['EMA 50 rota al alza', 'Impulso claro'],
      key_levels: { support: [1.0800], resistance: [1.0950] },
      patterns: ['HIGHER_LOW'],
      conclusion: 'Tendencia alcista en Daily',
    },
  ],
  strategy: {
    name: 'BLUE A',
    color: 'BLUE',
    steps: [
      { description: 'EMA 50 en H1 rota', met: true },
      { description: 'Pullback a EMA', met: true },
    ],
    entry_explanation: 'Entrada en pullback a EMA 50',
    sl_explanation: 'SL debajo del último mínimo',
    tp_explanation: 'TP en próxima resistencia',
    risk_assessment: 'Riesgo moderado',
  },
  recommendation: 'EJECUTAR con entrada en 1.0850',
};

const MOCK_CANDLES = [
  { time: '2026-03-27T10:00:00Z', open: 1.0830, high: 1.0855, low: 1.0825, close: 1.0850, volume: 1200 },
  { time: '2026-03-27T11:00:00Z', open: 1.0850, high: 1.0870, low: 1.0840, close: 1.0865, volume: 1500 },
];

const MOCK_PRICE = { instrument: 'EUR_USD', bid: 1.0862, ask: 1.0864, spread: 0.2 };

const MOCK_PENDING_SETUPS = [
  {
    id: 'setup-001',
    timestamp: '2026-03-27T14:30:00Z',
    instrument: 'EUR_USD',
    strategy: 'BLUE',
    direction: 'BUY',
    entry_price: 1.0850,
    stop_loss: 1.0820,
    take_profit: 1.0910,
    units: 10000,
    confidence: 85,
    risk_reward_ratio: 2.0,
    reasoning: 'EMA 50 H1 rota al alza\nPullback confirmado',
    status: 'PENDING',
    expires_at: '2026-03-27T15:30:00Z',
  },
];

const MOCK_HISTORY = [
  {
    id: 'trade-001',
    instrument: 'EUR_USD',
    strategy_color: 'BLUE',
    direction: 'BUY',
    entry_price: 1.0800,
    exit_price: 1.0860,
    pnl: 120.50,
    closed_at: '2026-03-26T16:30:00Z',
    mode: 'AUTO',
  },
];

const MOCK_HISTORY_STATS = {
  total_trades: 25,
  win_rate: 56.0,
  total_pnl: 850.25,
  best_trade: 320.50,
  worst_trade: -150.00,
};

const MOCK_JOURNAL_STATS = {
  total_trades: 50,
  wins: 25,
  losses: 15,
  break_evens: 10,
  win_rate: 50.0,
  win_rate_excl_be: 62.5,
  current_balance: 10500,
  initial_capital: 10000,
  peak_balance: 10800,
  current_drawdown_pct: 2.8,
  max_drawdown_pct: 5.5,
  max_drawdown_dollars: 594,
  current_winning_streak: 3,
  max_winning_streak: 7,
  max_streak_pct: 3.5,
  avg_win_pct: 1.2,
  avg_loss_pct: -0.8,
  profit_factor: 1.87,
  accumulator: 500,
  pnl_accumulated_pct: 5.0,
  monthly_returns: { '2026-01': 2.5, '2026-02': 1.8, '2026-03': 0.7 },
  dd_by_year: { '2026': 5.5 },
};

const MOCK_JOURNAL_TRADES = [
  {
    trade_number: 50,
    trade_id: 'trade-050',
    date: '2026-03-27',
    instrument: 'EUR_USD',
    direction: 'BUY',
    strategy: 'BLUE_A',
    pnl_dollars: 85.50,
    pnl_pct: 0.85,
    result: 'TP',
    balance_after: 10500,
    drawdown_pct: 0,
    max_drawdown_pct: 5.5,
    emotional_notes: {},
  },
];

const MOCK_MODE = { mode: 'AUTO' };
const MOCK_BROKER = { broker: 'capital', connected: true };

const MOCK_SETTINGS_STRATEGIES = {
  BLUE: true,
  BLUE_A: true,
  BLUE_B: true,
  BLUE_C: true,
  RED: true,
  PINK: true,
  WHITE: true,
  BLACK: true,
  GREEN: true,
};

// ── URL matching with specificity ordering ──────────────────────

function setupFetchMock(overrides: Record<string, any> = {}) {
  // Order matters: more specific paths FIRST to avoid substring collisions
  const responses: [string, any][] = [
    ['/api/v1/history/stats', MOCK_HISTORY_STATS],
    ['/api/v1/history', MOCK_HISTORY],
    ['/api/v1/journal/stats', MOCK_JOURNAL_STATS],
    ['/api/v1/journal/trades', MOCK_JOURNAL_TRADES],
    ['/api/v1/risk-config', MOCK_RISK_CONFIG],
    ['/api/v1/risk-status', MOCK_RISK_STATUS],
    ['/api/v1/account', MOCK_ACCOUNT],
    ['/api/v1/status', MOCK_STATUS],
    ['/api/v1/watchlist/categories', { categories: ['forex', 'crypto'] }],
    ['/api/v1/watchlist', MOCK_WATCHLIST],
    ['/api/v1/analysis/', MOCK_ANALYSIS],
    ['/api/v1/candles/', MOCK_CANDLES],
    ['/api/v1/price/', MOCK_PRICE],
    ['/api/v1/pending-setups', MOCK_PENDING_SETUPS],
    ['/api/v1/mode', MOCK_MODE],
    ['/api/v1/broker', MOCK_BROKER],
    ['/api/v1/strategies/config', MOCK_SETTINGS_STRATEGIES],
    ['/api/v1/alerts/config', { telegram_enabled: false, discord_enabled: false }],
    ['/api/v1/scalping/status', { enabled: false }],
    ['/api/v1/funded/status', { enabled: false }],
    ['/api/v1/security/status', { api_key_set: true, keys: [] }],
    ['/api/v1/profiles', []],
  ];

  // Apply overrides: exact path match
  const finalResponses = responses.map(([path, data]) => {
    if (path in overrides) {
      return [path, overrides[path]] as [string, any];
    }
    return [path, data] as [string, any];
  });

  mockAuthFetch.mockImplementation((url: string | Request, _init?: RequestInit) => {
    const urlStr = typeof url === 'string' ? url : url.toString();
    for (const [path, data] of finalResponses) {
      if (urlStr.includes(path)) {
        return mockJsonResponse(data);
      }
    }
    return mockJsonResponse({});
  });
}

// ── Screens ─────────────────────────────────────────────────────

import DashboardScreen from '../src/screens/DashboardScreen';
import AnalysisScreen from '../src/screens/AnalysisScreen';
import ChartScreen from '../src/screens/ChartScreen';
import JournalScreen from '../src/screens/JournalScreen';
import ManualModeScreen from '../src/screens/ManualModeScreen';
import SettingsScreen from '../src/screens/SettingsScreen';
import HistoryScreen from '../src/screens/HistoryScreen';
import WatchlistScreen from '../src/screens/WatchlistScreen';

// ═════════════════════════════════════════════════════════════════

beforeEach(() => {
  jest.useFakeTimers();
  mockAuthFetch.mockReset();
  (wsManager.on as jest.Mock).mockReset();
  (wsManager.on as jest.Mock).mockReturnValue(jest.fn());
  (wsManager.connect as jest.Mock).mockReset();
  setupFetchMock();
});

afterEach(() => {
  jest.useRealTimers();
});

// ─────────────────────────────────────────────────────────────────
// 1. Dashboard Screen
// ─────────────────────────────────────────────────────────────────

describe('DashboardScreen', () => {
  it('renders the dashboard header', async () => {
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => {
      expect(getByText('Dashboard')).toBeTruthy();
    });
  });

  it('displays account balance after loading', async () => {
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => {
      expect(getByText(/10,?000/)).toBeTruthy();
    });
  });

  it('shows engine status', async () => {
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => {
      expect(getByText(/ONLINE|AUTO/i)).toBeTruthy();
    });
  });

  it('displays active positions', async () => {
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => {
      expect(getByText(/EUR.?USD/)).toBeTruthy();
    });
  });

  it('shows daily activity stats', async () => {
    const { getByText, getAllByText } = render(<DashboardScreen />);
    await waitFor(() => {
      expect(getByText('Scans')).toBeTruthy();
      expect(getAllByText('45').length).toBeGreaterThan(0);
    });
  });

  it('subscribes to WebSocket events', () => {
    render(<DashboardScreen />);
    expect(wsManager.on).toHaveBeenCalledWith('engine_status', expect.any(Function));
  });

  it('shows error state when API fails', async () => {
    // Dashboard uses .catch(() => null) per request — rejecting makes accountRes=null
    mockAuthFetch.mockImplementation(() =>
      Promise.reject(new Error('Network error'))
    );
    const { getByText } = render(<DashboardScreen />);
    await waitFor(() => {
      expect(getByText(/No se pudo conectar al servidor/)).toBeTruthy();
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 2. Analysis Screen
// ─────────────────────────────────────────────────────────────────

describe('AnalysisScreen', () => {
  it('renders the analysis screen', async () => {
    const { getByText } = render(<AnalysisScreen />);
    await waitFor(() => {
      expect(getByText(/ANALISIS/)).toBeTruthy();
    });
  });

  it('loads and displays watchlist instruments', async () => {
    const { getByText } = render(<AnalysisScreen />);
    await waitFor(() => {
      expect(getByText(/EUR.?USD/)).toBeTruthy();
    });
  });

  it('displays analysis score', async () => {
    const { getByText } = render(<AnalysisScreen />);
    await waitFor(() => {
      expect(getByText(/78/)).toBeTruthy();
    });
  });

  it('shows strategy detection', async () => {
    const { getByText } = render(<AnalysisScreen />);
    await waitFor(() => {
      expect(getByText(/BLUE/)).toBeTruthy();
    });
  });

  it('fetches analysis for selected instrument', async () => {
    render(<AnalysisScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/analysis/EUR_USD')
      );
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 3. Chart Screen
// ─────────────────────────────────────────────────────────────────

describe('ChartScreen', () => {
  it('renders the chart screen with instrument', async () => {
    const { getByText } = render(<ChartScreen />);
    await waitFor(() => {
      expect(getByText(/EUR.?USD/)).toBeTruthy();
    });
  });

  it('shows timeframe selectors', async () => {
    const { getByText } = render(<ChartScreen />);
    await waitFor(() => {
      expect(getByText('H1')).toBeTruthy();
      expect(getByText('H4')).toBeTruthy();
      expect(getByText('D')).toBeTruthy();
    });
  });

  it('fetches candles data on render', async () => {
    render(<ChartScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/candles/')
      );
    });
  });

  it('fetches price data on render', async () => {
    render(<ChartScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/price/')
      );
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 4. Journal Screen
// ─────────────────────────────────────────────────────────────────

describe('JournalScreen', () => {
  it('renders the journal screen header', async () => {
    const { getByText } = render(<JournalScreen />);
    await waitFor(() => {
      // JournalScreen renders section titles; the sub-tab label "JOURNAL"
      // is now provided by App.tsx's SubTabScreen wrapper, not the screen
      // itself (audit A7 dedupe).
      expect(getByText('ESTADISTICAS GENERALES')).toBeTruthy();
    });
  });

  it('fetches journal stats and trade data', async () => {
    render(<JournalScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/journal/stats')
      );
    });
  });

  it('shows profit factor', async () => {
    const { getByText } = render(<JournalScreen />);
    await waitFor(() => {
      expect(getByText(/1\.87/)).toBeTruthy();
    });
  });

  it('displays trade list items', async () => {
    const { getByText } = render(<JournalScreen />);
    await waitFor(() => {
      expect(getByText(/EUR.?USD/)).toBeTruthy();
    });
  });

  it('fetches journal stats and trades', async () => {
    render(<JournalScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/journal/stats')
      );
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/journal/trades')
      );
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 5. Manual Mode Screen
// ─────────────────────────────────────────────────────────────────

describe('ManualModeScreen', () => {
  it('renders the manual mode header', async () => {
    const { getByText } = render(<ManualModeScreen />);
    await waitFor(() => {
      expect(getByText('PENDING OPS // MANUAL')).toBeTruthy();
    });
  });

  it('displays pending setups', async () => {
    const { getByText } = render(<ManualModeScreen />);
    await waitFor(() => {
      expect(getByText(/EUR\/USD/)).toBeTruthy();
    });
  });

  it('shows strategy and direction', async () => {
    const { getByText } = render(<ManualModeScreen />);
    await waitFor(() => {
      expect(getByText(/BLUE/)).toBeTruthy();
      expect(getByText(/COMPRAR/)).toBeTruthy();
    });
  });

  it('shows risk:reward ratio', async () => {
    const { getByText } = render(<ManualModeScreen />);
    await waitFor(() => {
      expect(getByText('R:R')).toBeTruthy();
      expect(getByText('2.0')).toBeTruthy();
    });
  });

  it('displays approve and reject buttons', async () => {
    const { getByText } = render(<ManualModeScreen />);
    await waitFor(() => {
      expect(getByText('APROBAR')).toBeTruthy();
      expect(getByText('RECHAZAR')).toBeTruthy();
    });
  });

  it('shows empty state when no setups', async () => {
    setupFetchMock({ '/api/v1/pending-setups': [] });
    const { getByText } = render(<ManualModeScreen />);
    await waitFor(() => {
      expect(getByText(/No hay operaciones pendientes/)).toBeTruthy();
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 6. Settings Screen
// ─────────────────────────────────────────────────────────────────

describe('SettingsScreen', () => {
  it('renders the settings screen header', async () => {
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => {
      expect(getByText('SYSTEM CONFIGURATION')).toBeTruthy();
    });
  });

  it('displays mode toggle', async () => {
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => {
      expect(getByText(/AUTO/)).toBeTruthy();
    });
  });

  it('shows broker selection', async () => {
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => {
      expect(getByText(/Capital\.com/)).toBeTruthy();
    });
  });

  it('shows strategy toggles', async () => {
    const { getByText, getAllByText } = render(<SettingsScreen />);
    await waitFor(() => {
      expect(getAllByText(/BLUE/).length).toBeGreaterThan(0);
      expect(getByText(/GREEN/)).toBeTruthy();
    });
  });

  it('displays engine control buttons', async () => {
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => {
      expect(getByText(/INICIAR ENGINE/)).toBeTruthy();
    });
  });

  it('shows risk configuration section', async () => {
    const { getByText } = render(<SettingsScreen />);
    await waitFor(() => {
      expect(getByText(/RISK PARAMETERS/)).toBeTruthy();
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 7. History Screen
// ─────────────────────────────────────────────────────────────────

describe('HistoryScreen', () => {
  it('renders the history screen header', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => {
      expect(getByText('RENDIMIENTO (30 DIAS)')).toBeTruthy();
    });
  });

  it('displays performance stats', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => {
      expect(getByText(/56\.0%/)).toBeTruthy();
    });
  });

  it('shows total P&L', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => {
      expect(getByText(/850\.25/)).toBeTruthy();
    });
  });

  it('displays trade history list', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => {
      expect(getByText(/EUR.?USD/)).toBeTruthy();
    });
  });

  it('shows strategy filter tabs', async () => {
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => {
      expect(getByText('ALL')).toBeTruthy();
      expect(getByText('BLUE')).toBeTruthy();
      expect(getByText('RED')).toBeTruthy();
    });
  });

  it('shows empty state when no trades', async () => {
    setupFetchMock({
      '/api/v1/history': [],
      '/api/v1/history/stats': { total_trades: 0, win_rate: 0, total_pnl: 0, best_trade: 0, worst_trade: 0 },
    });
    const { getByText } = render(<HistoryScreen />);
    await waitFor(() => {
      expect(getByText(/No hay historial de operaciones/)).toBeTruthy();
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 8. Watchlist Screen
// ─────────────────────────────────────────────────────────────────

describe('WatchlistScreen', () => {
  it('displays all watchlist pairs', async () => {
    const { getByText } = render(<WatchlistScreen />);
    await waitFor(() => {
      expect(getByText(/EUR\/USD/)).toBeTruthy();
      expect(getByText(/GBP\/USD/)).toBeTruthy();
      expect(getByText(/USD\/JPY/)).toBeTruthy();
    });
  });

  it('shows scores for pairs', async () => {
    const { getByText } = render(<WatchlistScreen />);
    await waitFor(() => {
      expect(getByText(/75/)).toBeTruthy();
    });
  });

  it('shows strategy detection badge', async () => {
    const { getByText } = render(<WatchlistScreen />);
    await waitFor(() => {
      expect(getByText(/BLUE/)).toBeTruthy();
    });
  });

  it('shows convergence indicator', async () => {
    const { getByText } = render(<WatchlistScreen />);
    await waitFor(() => {
      expect(getByText(/CONV/)).toBeTruthy();
    });
  });

  it('shows trend icons', async () => {
    const { getByText } = render(<WatchlistScreen />);
    await waitFor(() => {
      expect(getByText(/▲/)).toBeTruthy();
    });
  });

  it('shows error state when API fails', async () => {
    mockAuthFetch.mockImplementation(() =>
      Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ detail: 'Error' }) } as Response)
    );
    const { getByText } = render(<WatchlistScreen />);
    await waitFor(() => {
      expect(getByText(/Error al cargar datos/)).toBeTruthy();
    });
  });
});

// ─────────────────────────────────────────────────────────────────
// 9. WebSocket Integration
// ─────────────────────────────────────────────────────────────────

describe('WebSocket Integration', () => {
  it('Dashboard subscribes to engine_status events', () => {
    render(<DashboardScreen />);
    expect(wsManager.on).toHaveBeenCalledWith('engine_status', expect.any(Function));
  });

  it('Dashboard subscribes to trade_executed events', () => {
    render(<DashboardScreen />);
    expect(wsManager.on).toHaveBeenCalledWith('trade_executed', expect.any(Function));
  });

  it('Dashboard subscribes to trade_closed events', () => {
    render(<DashboardScreen />);
    expect(wsManager.on).toHaveBeenCalledWith('trade_closed', expect.any(Function));
  });

  it('wsManager.connect is called by Dashboard', () => {
    render(<DashboardScreen />);
    expect(wsManager.connect).toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────
// 10. API Service Tests
// ─────────────────────────────────────────────────────────────────

describe('API Service', () => {
  it('Dashboard calls account and status endpoints', async () => {
    render(<DashboardScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/account')
      );
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/status')
      );
    });
  });

  it('Watchlist screen calls watchlist endpoint', async () => {
    render(<WatchlistScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/watchlist')
      );
    });
  });

  it('History screen calls history and stats endpoints', async () => {
    render(<HistoryScreen />);
    await waitFor(() => {
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/history?limit=200')
      );
      expect(mockAuthFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/history/stats')
      );
    });
  });
});
