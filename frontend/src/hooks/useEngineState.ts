/**
 * useEngineState — polls /engine-state every 10s.
 * Exposes the typed state + error + loading + manual refresh.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL, authFetch } from '../services/api';

export interface NewsEvent {
  title: string;
  currency: string;
  impact?: string;
  time_utc?: string;
  ends_at_utc?: string;
  minutes_remaining?: number;
  minutes_until?: number;
}

export type PausedReason =
  | 'news_blackout'
  | 'out_of_hours'
  | 'friday_close'
  | 'friday_no_new_trades'
  | 'max_trades_reached'
  | 'cooldown_after_losses'
  | null;

export type SessionName =
  | 'london'
  | 'london_ny_overlap'
  | 'ny'
  | 'asia'
  | 'quiet';

export interface EngineState {
  running: boolean;
  paused_reason: PausedReason;
  paused_reason_text: string | null;
  resumes_at_utc: string | null;
  session: SessionName;
  news: {
    active: NewsEvent | null;
    next: NewsEvent | null;
  };
  consecutive_losses_today: number;
  setups_executed_today: number;
  max_trades_per_day: number;
  now_utc: string;
  trading_hours_utc: string;
}

const DEFAULT_POLL_MS = 10_000;

export function useEngineState(pollMs: number = DEFAULT_POLL_MS) {
  const [state, setState] = useState<EngineState | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const fetchState = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/api/v1/engine-state`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as EngineState;
      if (mounted.current) {
        setState(data);
        setError(null);
      }
    } catch (err: any) {
      if (mounted.current) setError(err?.message || 'fetch_failed');
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    fetchState();
    const id = setInterval(fetchState, pollMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [fetchState, pollMs]);

  return { state, loading, error, refresh: fetchState };
}
