/**
 * useAlertSounds — plays a short chime and vibrates for setup events.
 * Uses browser Web Audio API + navigator.vibrate (works on Expo Web).
 * Preferences persisted to localStorage when available.
 *
 * Keys:
 *   atlas.alerts.sound  => "1" | "0"
 *   atlas.alerts.haptic => "1" | "0"
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';

const SOUND_KEY = 'atlas.alerts.sound';
const HAPTIC_KEY = 'atlas.alerts.haptic';

function readPref(key: string, defaultValue: boolean): boolean {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return defaultValue;
  try {
    const raw = window.localStorage.getItem(key);
    if (raw == null) return defaultValue;
    return raw === '1';
  } catch {
    return defaultValue;
  }
}

function writePref(key: string, value: boolean): void {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value ? '1' : '0');
  } catch {
    /* ignore */
  }
}

function playChime(): void {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return;
  const Ctx: any = (window as any).AudioContext || (window as any).webkitAudioContext;
  if (!Ctx) return;
  try {
    const ctx = new Ctx();
    const now = ctx.currentTime;
    // Two-note chime: C6 then E6 — short, Apple-style
    const notes: Array<[number, number]> = [
      [1046.5, 0],     // C6
      [1318.5, 0.12],  // E6
    ];
    for (const [freq, offset] of notes) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, now + offset);
      gain.gain.setValueAtTime(0, now + offset);
      gain.gain.linearRampToValueAtTime(0.18, now + offset + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.22);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now + offset);
      osc.stop(now + offset + 0.24);
    }
    // Auto-close ctx after playback to free resources
    setTimeout(() => {
      try { ctx.close(); } catch { /* noop */ }
    }, 600);
  } catch {
    /* ignore playback errors */
  }
}

function triggerHaptic(): void {
  if (Platform.OS !== 'web' || typeof navigator === 'undefined') return;
  try {
    if (typeof (navigator as any).vibrate === 'function') {
      // Double tap pattern: 40ms on, 120ms off, 40ms on
      (navigator as any).vibrate([40, 120, 40]);
    }
  } catch {
    /* ignore */
  }
}

export function useAlertSounds() {
  const [soundEnabled, setSoundEnabledState] = useState<boolean>(() => readPref(SOUND_KEY, true));
  const [hapticEnabled, setHapticEnabledState] = useState<boolean>(() => readPref(HAPTIC_KEY, true));
  const soundRef = useRef(soundEnabled);
  const hapticRef = useRef(hapticEnabled);

  useEffect(() => { soundRef.current = soundEnabled; }, [soundEnabled]);
  useEffect(() => { hapticRef.current = hapticEnabled; }, [hapticEnabled]);

  const setSoundEnabled = useCallback((val: boolean) => {
    writePref(SOUND_KEY, val);
    setSoundEnabledState(val);
  }, []);

  const setHapticEnabled = useCallback((val: boolean) => {
    writePref(HAPTIC_KEY, val);
    setHapticEnabledState(val);
  }, []);

  const fireSetupAlert = useCallback(() => {
    if (soundRef.current) playChime();
    if (hapticRef.current) triggerHaptic();
  }, []);

  return {
    soundEnabled,
    hapticEnabled,
    setSoundEnabled,
    setHapticEnabled,
    fireSetupAlert,
  };
}

/** Read-only helper for non-React callers. */
export function readAlertPrefs(): { sound: boolean; haptic: boolean } {
  return {
    sound: readPref(SOUND_KEY, true),
    haptic: readPref(HAPTIC_KEY, true),
  };
}

export function fireSetupAlertDirect(): void {
  const prefs = readAlertPrefs();
  if (prefs.sound) playChime();
  if (prefs.haptic) triggerHaptic();
}
