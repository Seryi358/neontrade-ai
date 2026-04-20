/**
 * Atlas - Currency flag helpers
 * Maps currency codes to emoji flags for news/session UI.
 */

export const CURRENCY_FLAGS: Record<string, string> = {
  USD: '\u{1F1FA}\u{1F1F8}',  // 🇺🇸
  EUR: '\u{1F1EA}\u{1F1FA}',  // 🇪🇺
  GBP: '\u{1F1EC}\u{1F1E7}',  // 🇬🇧
  JPY: '\u{1F1EF}\u{1F1F5}',  // 🇯🇵
  AUD: '\u{1F1E6}\u{1F1FA}',  // 🇦🇺
  NZD: '\u{1F1F3}\u{1F1FF}',  // 🇳🇿
  CAD: '\u{1F1E8}\u{1F1E6}',  // 🇨🇦
  CHF: '\u{1F1E8}\u{1F1ED}',  // 🇨🇭
  CNY: '\u{1F1E8}\u{1F1F3}',  // 🇨🇳
  MXN: '\u{1F1F2}\u{1F1FD}',  // 🇲🇽
  SEK: '\u{1F1F8}\u{1F1EA}',  // 🇸🇪
  NOK: '\u{1F1F3}\u{1F1F4}',  // 🇳🇴
};

export function flagForCurrency(currency?: string | null): string {
  if (!currency) return '\u{1F3F3}';  // white flag fallback
  return CURRENCY_FLAGS[currency.toUpperCase()] || '\u{1F3F3}';
}

export function impactStars(impact?: string | null): string {
  const lvl = (impact || '').toLowerCase();
  if (lvl === 'high') return '\u2B50\u2B50\u2B50';
  if (lvl === 'medium') return '\u2B50\u2B50';
  if (lvl === 'low') return '\u2B50';
  return '';
}
