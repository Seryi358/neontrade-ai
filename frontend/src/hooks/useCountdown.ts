/**
 * useCountdown — generic countdown towards a UTC ISO target (or minutes duration).
 * Returns total seconds remaining, mm:ss, hh:mm:ss strings.
 */

import { useEffect, useState } from 'react';

export interface CountdownValue {
  totalSeconds: number;
  hours: number;
  minutes: number;
  seconds: number;
  mmss: string;
  hhmmss: string;
  expired: boolean;
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function computeFromTarget(targetMs: number | null): CountdownValue {
  if (targetMs == null) {
    return { totalSeconds: 0, hours: 0, minutes: 0, seconds: 0, mmss: '--:--', hhmmss: '--:--:--', expired: true };
  }
  const diffMs = targetMs - Date.now();
  const totalSeconds = Math.max(0, Math.floor(diffMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return {
    totalSeconds,
    hours,
    minutes,
    seconds,
    mmss: `${pad(hours * 60 + minutes)}:${pad(seconds)}`,
    hhmmss: `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`,
    expired: totalSeconds <= 0,
  };
}

/**
 * Countdown towards a UTC ISO string like "2026-04-20T17:10:00+00:00"
 * or a Date/number (ms epoch). Null resets to expired.
 */
export function useCountdown(target: string | number | Date | null | undefined): CountdownValue {
  const [now, setNow] = useState<number>(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  let targetMs: number | null = null;
  if (target != null) {
    if (target instanceof Date) targetMs = target.getTime();
    else if (typeof target === 'number') targetMs = target;
    else if (typeof target === 'string') {
      const d = new Date(target);
      if (!isNaN(d.getTime())) targetMs = d.getTime();
    }
  }

  // recompute each tick
  void now;
  return computeFromTarget(targetMs);
}
