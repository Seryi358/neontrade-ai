/**
 * Atlas - Currency flag helpers
 * Keeps news/session labels text-only.
 */

export const CURRENCY_FLAGS: Record<string, string> = {
  USD: 'USD',
  EUR: 'EUR',
  GBP: 'GBP',
  JPY: 'JPY',
  AUD: 'AUD',
  NZD: 'NZD',
  CAD: 'CAD',
  CHF: 'CHF',
  CNY: 'CNY',
  MXN: 'MXN',
  SEK: 'SEK',
  NOK: 'NOK',
};

export function flagForCurrency(currency?: string | null): string {
  if (!currency) return 'NEWS';
  return CURRENCY_FLAGS[currency.toUpperCase()] || currency.toUpperCase();
}

export function impactStars(impact?: string | null): string {
  const lvl = (impact || '').toLowerCase();
  if (lvl === 'high') return 'HIGH';
  if (lvl === 'medium') return 'MED';
  if (lvl === 'low') return 'LOW';
  return '';
}
