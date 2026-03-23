/**
 * NeonTrade AI - API Service
 * Centralized API communication and WebSocket management.
 */

// ── Configuration ────────────────────────────────────────────────
// Backend URL: local by default, configurable for remote VPS deployment.
// Set via localStorage 'neontrade_backend_url' or Electron env.
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
  // 3. Default: local backend
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
    window.localStorage.setItem('neontrade_backend_url', clean);
  }
  API_URL = clean;
  WS_URL = clean.replace('http', 'ws') + '/ws';
}

/**
 * Reset to local backend (clear saved remote URL).
 */
export function resetBackendUrl(): void {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem('neontrade_backend_url');
  }
  API_URL = DEFAULT_URL;
  WS_URL = DEFAULT_URL.replace('http', 'ws') + '/ws';
}

// ── Request timeout ──────────────────────────────────────────────
const REQUEST_TIMEOUT_MS = 15_000;

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
  const resp = await fetchWithTimeout(`${API_URL}${path}`);
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || `API error: ${resp.status}`);
  }
  return resp.json();
}

async function apiPost<T>(path: string, body?: any): Promise<T> {
  const resp = await fetchWithTimeout(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
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
};

// ── Shared Constants ─────────────────────────────────────────────

export const STRATEGY_COLORS: Record<string, string> = {
  BLACK: '#1a1a2e',
  BLUE: '#00f0ff',
  RED: '#ff2e63',
  GREEN: '#00ff88',
  WHITE: '#f0e6ff',
  DETECTED: '#eb4eca',
};

export function getScoreColor(score: number): string {
  if (score >= 80) return '#00ff88';
  if (score >= 60) return '#ffd700';
  if (score >= 40) return '#ff6b35';
  return '#ff2e63';
}

export function getTrendColor(trend: string): string {
  if (trend?.includes('BULL')) return '#00ff88';
  if (trend?.includes('BEAR')) return '#ff2e63';
  return '#7a6b9a';
}

export function getTrendIcon(trend: string): string {
  if (trend?.includes('BULL')) return '▲';
  if (trend?.includes('BEAR')) return '▼';
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
      this.ws = new WebSocket(WS_URL);

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
