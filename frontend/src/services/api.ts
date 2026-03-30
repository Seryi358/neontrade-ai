/**
 * NeonTrade AI - API Service
 * Centralized API communication and WebSocket management.
 */

// ── Configuration ────────────────────────────────────────────────
// Backend URL: auto-detected from window.location when served from
// the same origin (EasyPanel/Docker), configurable via localStorage
// or Electron env variable for other setups.
const DEFAULT_URL = 'http://localhost:8000';

function getBaseUrl(): string {
  // 1. Check localStorage for user-configured remote URL
  if (typeof window !== 'undefined') {
    try {
      const saved = window.localStorage.getItem('neontrade_backend_url');
      if (saved && saved.startsWith('http')) {
        return saved.replace(/\/+$/, '');
      }
    } catch {}
  }
  // 2. Check Electron injected variable
  if (typeof window !== 'undefined' && (window as any).__NEONTRADE_API_HOST__) {
    return `http://${(window as any).__NEONTRADE_API_HOST__}`;
  }
  // 3. Auto-detect: if served from a non-localhost origin (EasyPanel/VPS),
  //    use that origin as the API base URL (same-origin deployment)
  if (typeof window !== 'undefined' && window.location) {
    const { hostname, protocol, port } = window.location;
    if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
      const base = `${protocol}//${hostname}${port ? ':' + port : ''}`;
      return base;
    }
  }
  // 4. Default: local backend
  return DEFAULT_URL;
}

export let API_URL = getBaseUrl();
export let WS_URL = API_URL.replace('http', 'ws') + '/ws';

/**
 * Change the backend URL at runtime (for remote VPS deployment).
 * Saves to localStorage so it persists across sessions.
 */
export function setBackendUrl(url: string): void {
  const clean = url.replace(/\/+$/, '');
  if (typeof window !== 'undefined') {
    try { window.localStorage.setItem('neontrade_backend_url', clean); } catch {}
  }
  API_URL = clean;
  WS_URL = clean.replace('http', 'ws') + '/ws';
  // Reconnect WebSocket to new URL
  wsManager.disconnect();
  wsManager.connect();
}

/**
 * Reset to local backend (clear saved remote URL).
 */
export function resetBackendUrl(): void {
  if (typeof window !== 'undefined') {
    try { window.localStorage.removeItem('neontrade_backend_url'); } catch {}
  }
  API_URL = DEFAULT_URL;
  WS_URL = DEFAULT_URL.replace('http', 'ws') + '/ws';
  // Reconnect WebSocket to default URL
  wsManager.disconnect();
  wsManager.connect();
}

// ── API Key for authenticated requests ──────────────────────────
// Priority: 1) localStorage (user-set), 2) injected by backend (same-origin), 3) empty
function getApiKey(): string {
  if (typeof window !== 'undefined') {
    try {
      const saved = window.localStorage.getItem('neontrade_api_key');
      if (saved) return saved;
    } catch {}
    // Auto-injected by backend when served from same origin (EasyPanel/Docker)
    try {
      const injected = (window as any).__NEONTRADE_API_KEY__;
      if (injected) return injected;
    } catch {}
  }
  return '';
}

export function setApiKey(key: string): void {
  if (typeof window !== 'undefined') {
    try { window.localStorage.setItem('neontrade_api_key', key); } catch {}
  }
}

export function clearApiKey(): void {
  if (typeof window !== 'undefined') {
    try { window.localStorage.removeItem('neontrade_api_key'); } catch {}
  }
}

/**
 * Authenticated fetch - drop-in replacement for window.fetch
 * that automatically includes the X-API-Key header.
 */
export function authFetch(input: RequestInfo, init?: RequestInit): Promise<Response> {
  const key = getApiKey();
  const headers: Record<string, string> = {};
  if (init?.headers) {
    if (init.headers instanceof Headers) {
      init.headers.forEach((v: string, k: string) => { headers[k] = v; });
    } else if (Array.isArray(init.headers)) {
      init.headers.forEach(([k, v]) => { headers[k] = v; });
    } else {
      Object.assign(headers, init.headers);
    }
  }
  if (key) headers['X-API-Key'] = key;

  // Add 15s timeout to prevent indefinite hangs
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  return fetch(input, { ...init, headers, signal: controller.signal })
    .finally(() => clearTimeout(timeout));
}

// ── Request timeout ──────────────────────────────────────────────
const REQUEST_TIMEOUT_MS = 15_000;

function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { 'X-API-Key': key } : {};
}

async function fetchWithTimeout(
  input: RequestInfo,
  init?: RequestInit,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(input, { ...init, signal: controller.signal });
    return resp;
  } finally {
    clearTimeout(timer);
  }
}

// ── REST API Helpers ──────────────────────────────────────────────

async function apiGet<T>(path: string): Promise<T> {
  const resp = await fetchWithTimeout(`${API_URL}${path}`, {
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `API error: ${resp.status}`);
  }
  return resp.json();
}

async function apiPost<T>(path: string, body?: any): Promise<T> {
  const resp = await fetchWithTimeout(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `API error: ${resp.status}`);
  }
  return resp.json();
}

async function apiPut<T>(path: string, body?: any): Promise<T> {
  const resp = await fetchWithTimeout(`${API_URL}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `API error: ${resp.status}`);
  }
  return resp.json();
}

async function apiDelete<T>(path: string): Promise<T> {
  const resp = await fetchWithTimeout(`${API_URL}${path}`, {
    method: 'DELETE',
    headers: { ...authHeaders() },
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `API error: ${resp.status}`);
  }
  return resp.json();
}

// ── API Methods ──────────────────────────────────────────────────

export const api = {
  // Status
  getStatus: () => apiGet<any>('/api/v1/status'),
  getHealth: () => apiGet<any>('/health'),

  // Account
  getAccount: () => apiGet<any>('/api/v1/account'),

  // Mode
  getMode: () => apiGet<any>('/api/v1/mode'),
  setMode: (mode: 'AUTO' | 'MANUAL') => apiPost<any>('/api/v1/mode', { mode }),

  // Watchlist & Analysis
  getWatchlist: () => apiGet<any[]>('/api/v1/watchlist'),
  getAnalysis: (instrument: string) => apiGet<any>(`/api/v1/analysis/${instrument}`),
  getAllAnalyses: () => apiGet<any[]>('/api/v1/analysis'),

  // Candles & Price
  getCandles: (instrument: string, granularity = 'H1', count = 200) =>
    apiGet<any[]>(`/api/v1/candles/${instrument}?granularity=${granularity}&count=${count}`),
  getPrice: (instrument: string) => apiGet<any>(`/api/v1/price/${instrument}`),

  // Positions
  getPositions: () => apiGet<any>('/api/v1/positions'),

  // Pending Setups (Manual Mode)
  getPendingSetups: () => apiGet<any[]>('/api/v1/pending-setups'),
  approveSetup: (id: string) => apiPost<any>(`/api/v1/pending-setups/${id}/approve`),
  rejectSetup: (id: string) => apiPost<any>(`/api/v1/pending-setups/${id}/reject`),
  approveAllSetups: () => apiPost<any>('/api/v1/pending-setups/approve-all'),
  rejectAllSetups: () => apiPost<any>('/api/v1/pending-setups/reject-all'),

  // History
  getHistory: (params?: { limit?: number; offset?: number; strategy?: string; instrument?: string }) => {
    const query = new URLSearchParams();
    if (params?.limit) query.set('limit', String(params.limit));
    if (params?.offset) query.set('offset', String(params.offset));
    if (params?.strategy) query.set('strategy', params.strategy);
    if (params?.instrument) query.set('instrument', params.instrument);
    return apiGet<any[]>(`/api/v1/history?${query}`);
  },
  getPerformanceStats: (days = 30) => apiGet<any>(`/api/v1/history/stats?days=${days}`),

  // Broker
  getBroker: () => apiGet<any>('/api/v1/broker'),
  setBroker: (broker: string) => apiPost<any>('/api/v1/broker', { broker }),

  // Engine Control
  startEngine: () => apiPost<any>('/api/v1/engine/start'),
  stopEngine: () => apiPost<any>('/api/v1/engine/stop'),
  emergencyCloseAll: () => apiPost<any>('/api/v1/emergency/close-all'),

  // Strategies Info
  getStrategies: () => apiGet<any[]>('/api/v1/strategies'),

  // Diagnostic
  getDiagnostic: () => apiGet<any>('/api/v1/diagnostic'),

  // Security
  getSecurityStatus: () => apiGet<any>('/api/v1/security/status'),
  generateApiKey: (label = 'electron') => apiPost<any>(`/api/v1/security/generate-key?label=${label}`),
  updateSecurity: (config: any) => apiPut<any>('/api/v1/security/config', config),
  revokeApiKey: (hashPrefix: string) => apiDelete<any>(`/api/v1/security/revoke-key/${hashPrefix}`),

  // Watchlist Categories (TradingLab extended watchlists)
  getWatchlistCategories: () => apiGet<any>('/api/v1/watchlist/categories'),
  updateWatchlistCategories: (categories: string[]) =>
    apiPut<any>('/api/v1/watchlist/categories', { categories }),
  getFullWatchlist: () => apiGet<any>('/api/v1/watchlist/full'),

  // Screenshots (Trading Plan: capture every trade)
  getTradeScreenshots: (tradeId: string) => apiGet<any>(`/api/v1/screenshots/${tradeId}`),
  getScreenshotUrl: (tradeId: string, filename: string) =>
    `${API_URL}/api/v1/screenshots/${tradeId}/image/${filename}`,

  // Monthly Review (Trading Plan: monthly trade review)
  listMonthlyReviews: () => apiGet<any>('/api/v1/monthly-review'),
  getMonthlyReview: (month: string) => apiGet<any>(`/api/v1/monthly-review/${month}`),
  generateMonthlyReview: (month: string) =>
    apiPost<any>(`/api/v1/monthly-review/generate?month=${month}`),

  // Discretionary Trade Tracking
  markTradeDiscretionary: (tradeId: string, isDiscretionary: boolean, notes: string) =>
    apiPut<any>(`/api/v1/journal/trades/${tradeId}/discretionary`, {
      is_discretionary: isDiscretionary, discretionary_notes: notes,
    }),

  // Missed Trades
  getMissedTrades: (limit = 50, offset = 0) =>
    apiGet<any>(`/api/v1/missed-trades?limit=${limit}&offset=${offset}`),
  getMissedTradeStats: () => apiGet<any>('/api/v1/missed-trades/stats'),

  // Risk Management
  getRiskConfig: () => apiGet<any>('/api/v1/risk-config'),
  updateRiskConfig: (data: any) => apiPut<any>('/api/v1/risk-config', data),
  getRiskStatus: () => apiGet<any>('/api/v1/risk-status'),

  // Equity
  getEquityCurve: () => apiGet<any>('/api/v1/equity-curve'),

  // Alerts
  getAlertConfig: () => apiGet<any>('/api/v1/alerts/config'),
  updateAlertConfig: (data: any) => apiPut<any>('/api/v1/alerts/config', data),
  testAlert: (channel: string) => apiPost<any>(`/api/v1/alerts/test/${channel}`),

  // Crypto
  getCryptoIndicators: () => apiGet<any>('/api/v1/crypto/indicators'),

  // Scalping
  getScalpingStatus: () => apiGet<any>('/api/v1/scalping/status'),
  toggleScalping: (enabled: boolean) => apiPost<any>('/api/v1/scalping/toggle', { enabled }),

  // Funded Account
  getFundedStatus: () => apiGet<any>('/api/v1/funded/status'),
  toggleFunded: (enabled: boolean) => apiPost<any>('/api/v1/funded/toggle', { enabled }),

  // Calendar & News
  getCalendar: () => apiGet<any>('/api/v1/calendar'),
  getNews: () => apiGet<any>('/api/v1/news'),

  // Profiles
  getProfiles: () => apiGet<any>('/api/v1/profiles'),
  applyProfile: (name: string) => apiPost<any>('/api/v1/profiles/apply', { profile: name }),

  // Journal
  getJournalStats: () => apiGet<any>('/api/v1/journal/stats'),
  getJournalTrades: (limit = 50, offset = 0) =>
    apiGet<any>(`/api/v1/journal/trades?limit=${limit}&offset=${offset}`),
  updateEmotionalNotes: (tradeId: string, data: any) =>
    apiPut<any>(`/api/v1/journal/trades/${tradeId}/emotional-notes`, data),
  updateASR: (tradeId: string, data: any) =>
    apiPut<any>(`/api/v1/journal/trades/${tradeId}/asr`, data),
  getASRStats: () => apiGet<any>('/api/v1/journal/asr-stats'),

  // Backtest
  runBacktest: (config: any) => apiPost<any>('/api/v1/backtest', config),

  // Daily Activity
  getDailyActivity: () => apiGet<any>('/api/v1/daily-activity'),

  // Strategies Config
  getStrategiesConfig: () => apiGet<any>('/api/v1/strategies/config'),
  updateStrategiesConfig: (data: any) => apiPut<any>('/api/v1/strategies/config', data),
};

// ── Shared Constants ─────────────────────────────────────────────

export const STRATEGY_COLORS: Record<string, string> = {
  BLUE: '#3daee9',    // Daemon: ForegroundActive (61,174,233)
  RED: '#fb3048',     // Daemon: ForegroundNegative (251,48,72)
  PINK: '#ee00ff',    // Daemon: WM activeBackground (238,0,255)
  WHITE: '#fcfcfc',   // Daemon: ForegroundNormal (252,252,252)
  BLACK: '#a1a9b1',   // Daemon: ForegroundInactive (161,169,177)
  GREEN: '#28c775',   // Daemon: ForegroundPositive (40,199,117)
  DETECTED: '#fdf500', // Daemon: ForegroundNeutral (253,245,0)
};

export function getScoreColor(score: number): string {
  if (score >= 80) return '#2ed88c';  // Bitpunk green
  if (score >= 60) return '#f3e600';  // Bitpunk yellow
  if (score >= 40) return '#ff6b35';  // Warning orange
  return '#ff4a57';                   // Bitpunk red
}

export function getTrendColor(trend: string): string {
  const upper = trend?.toUpperCase() || '';
  if (upper.includes('BULL')) return '#2ed88c';  // Bitpunk green
  if (upper.includes('BEAR')) return '#ff4a57';  // Bitpunk red
  return '#7a6b9a';
}

export function getTrendIcon(trend: string): string {
  const upper = trend?.toUpperCase() || '';
  if (upper.includes('BULL')) return '▲';
  if (upper.includes('BEAR')) return '▼';
  return '◆';
}

// ── WebSocket Manager ────────────────────────────────────────────

type WSEventHandler = (data: any) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private handlers: Map<string, WSEventHandler[]> = new Map();
  private reconnectTimer: any = null;
  private isConnected = false;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 20;

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    try {
      // Include API key in WS connection for authentication
      const apiKey = getApiKey();
      const wsUrlAuth = apiKey ? `${WS_URL}?api_key=${encodeURIComponent(apiKey)}` : WS_URL;
      this.ws = new WebSocket(wsUrlAuth);

      this.ws.onopen = () => {
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.emit('connection', { connected: true });
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          if (message && typeof message.type === 'string') {
            this.emit(message.type, message.data);
          }
        } catch {
          // Ignore malformed messages
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.emit('connection', { connected: false });
        this._scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch {
      this._scheduleReconnect();
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.emit('connection', { connected: false, error: 'Max reconnect attempts reached' });
      return;
    }
    // Exponential backoff: 1s, 2s, 4s, 8s, 16s, max 30s
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30_000);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = this.maxReconnectAttempts; // Prevent reconnect
    this.ws?.close();
    this.ws = null;
    this.isConnected = false;
  }

  send(action: string, data?: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action, ...data }));
    }
  }

  on(event: string, handler: WSEventHandler) {
    const list = this.handlers.get(event) || [];
    list.push(handler);
    this.handlers.set(event, list);
    return () => {
      const idx = list.indexOf(handler);
      if (idx >= 0) list.splice(idx, 1);
    };
  }

  private emit(event: string, data: any) {
    const list = this.handlers.get(event) || [];
    for (const handler of list) {
      try {
        handler(data);
      } catch {
        // Don't let handler errors crash the WS loop
      }
    }
  }

  get connected() {
    return this.isConnected;
  }
}

export const wsManager = new WebSocketManager();
