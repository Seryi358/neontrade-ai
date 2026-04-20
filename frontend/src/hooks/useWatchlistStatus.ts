/**
 * useWatchlistStatus — polls /watchlist-status every 20s.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { API_URL, authFetch } from '../services/api';

export type InstrumentStatus =
  | 'ready_waiting'
  | 'forming'
  | 'weak'
  | 'no_pattern'
  | 'setup_queued';

export interface InstrumentStatusItem {
  instrument: string;
  score: number;
  htf_trend: string;
  ltf_trend: string;
  convergence: boolean;
  status: InstrumentStatus;
  status_text: string;
}

const DEFAULT_POLL_MS = 20_000;

export function useWatchlistStatus(pollMs: number = DEFAULT_POLL_MS) {
  const [items, setItems] = useState<InstrumentStatusItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const res = await authFetch(`${API_URL}/api/v1/watchlist-status`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as InstrumentStatusItem[];
      if (mounted.current) {
        // Guard: only accept items that look like InstrumentStatusItem.
        // Prevents false-positive rendering when the endpoint is missing
        // and a proxy returns some other shape (e.g. /api/v1/watchlist).
        const valid = Array.isArray(data)
          ? data.filter(
              (x) =>
                x &&
                typeof (x as any).status === 'string' &&
                typeof (x as any).status_text === 'string'
            )
          : [];
        setItems(valid);
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
    refresh();
    const id = setInterval(refresh, pollMs);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [refresh, pollMs]);

  return { items, loading, error, refresh };
}
