/**
 * Atlas - Apple Liquid Glass Theme
 * Inspired by iOS 26 Liquid Glass design language.
 * Font: SF Pro Display (system font) — clean, professional, Apple-native.
 *
 * Design principles:
 * - Translucent glass cards with blur and saturation
 * - Light background (#f2f2f7) with white glass overlays
 * - Subtle inner reflections and soft shadows
 * - Apple system colors for status indicators
 * - Generous whitespace, minimal borders
 * - Smooth 0.3s transitions on all interactive elements
 */

export const theme = {
  colors: {
    // Backgrounds (Apple Light Mode)
    background: '#f2f2f7',          // Apple: systemGroupedBackground
    backgroundDark: '#e5e5ea',      // Apple: systemGray5
    backgroundLight: '#ffffff',     // Apple: systemBackground
    backgroundCard: 'rgba(255, 255, 255, 0.75)',  // Glass card base
    backgroundHUD: 'rgba(255, 255, 255, 0.85)',   // Glass card opaque

    // Primary accent — Apple Blue
    cp2077Yellow: '#007AFF',        // Apple: systemBlue (maps from old cyan primary)
    cp2077YellowDim: '#5856D6',     // Apple: systemIndigo
    cp2077YellowGlow: 'rgba(0, 122, 255, 0.15)',

    // Apple Blue (primary)
    neonCyan: '#007AFF',            // Apple: systemBlue
    neonCyanDim: '#5AC8FA',         // Apple: systemTeal
    neonCyanGlow: 'rgba(0, 122, 255, 0.12)',

    // Apple Purple
    neonMagenta: '#AF52DE',         // Apple: systemPurple
    neonMagentaDim: '#5856D6',      // Apple: systemIndigo
    neonMagentaGlow: 'rgba(175, 82, 222, 0.12)',

    // Apple Red
    neonRed: '#FF3B30',             // Apple: systemRed
    neonRedDim: '#FF6961',
    neonRedGlow: 'rgba(255, 59, 48, 0.12)',

    // Apple Green
    neonGreen: '#34C759',           // Apple: systemGreen
    neonGreenDim: '#30D158',
    neonGreenGlow: 'rgba(52, 199, 89, 0.12)',
    neonOrange: '#FF9500',          // Apple: systemOrange
    neonYellow: '#FFCC00',          // Apple: systemYellow

    // Apple accent colors
    neonBlue: '#007AFF',            // Apple: systemBlue
    coldGray: '#C7C7CC',            // Apple: systemGray4
    iceWhite: '#ffffff',

    // Text (Apple typography)
    textPrimary: '#1d1d1f',         // Apple: label
    textSecondary: '#86868b',       // Apple: secondaryLabel
    textMuted: '#aeaeb2',           // Apple: tertiaryLabel
    textWhite: '#ffffff',
    textCyan: '#007AFF',            // Apple: link color

    // Status
    profit: '#34C759',              // Apple green
    loss: '#FF3B30',                // Apple red
    neutral: '#8E8E93',             // Apple: systemGray
    warning: '#FF9500',             // Apple orange

    // Confidence levels
    confidenceHigh: '#34C759',
    confidenceMedium: '#FF9500',
    confidenceLow: '#8E8E93',

    // Borders (Liquid Glass)
    border: 'rgba(0, 0, 0, 0.04)',
    borderActive: '#007AFF',
    borderCyan: '#007AFF',
    borderMagenta: '#AF52DE',

    // Glass borders
    glassBorder: 'rgba(255, 255, 255, 0.6)',
    glassBorderSubtle: 'rgba(255, 255, 255, 0.4)',

    // Chart (Apple-aligned)
    chartBullish: '#34C759',
    chartBearish: '#FF3B30',
    chartGrid: '#f2f2f7',
    chartBackground: '#ffffff',
    chartGridLines: 'rgba(0, 0, 0, 0.06)',
    chartCandleUp: '#34C759',
    chartCandleDown: '#FF3B30',
    chartVolumeUp: 'rgba(52, 199, 89, 0.2)',
    chartVolumeDown: 'rgba(255, 59, 48, 0.2)',
    chartCrosshair: '#007AFF',
    chartEma20: '#007AFF',
    chartEma50: '#AF52DE',
    chartSupport: '#34C759',
    chartResistance: '#FF3B30',
    chartPivot: '#FF9500',
    chartTextColor: '#86868b',
    chartCurrentPrice: '#1d1d1f',

    // Strategy detection colors (TradingLab 6-color system, Apple-aligned)
    strategyBlue: '#007AFF',
    strategyRed: '#FF3B30',
    strategyPink: '#FF2D55',        // Apple: systemPink
    strategyWhite: '#8E8E93',       // Apple: systemGray (visible on light bg)
    strategyBlack: '#1d1d1f',
    strategyGreen: '#34C759',
    strategyDetected: '#FF9500',
  },

  fonts: {
    // SF Pro Display — bundled, works on ALL platforms
    primary: 'SFProDisplay-Regular',
    heading: 'SFProDisplay-Bold',
    medium: 'SFProDisplay-Medium',
    semibold: 'SFProDisplay-Semibold',
    light: 'SFProDisplay-Light',
    mono: 'SFProDisplay-Regular',
    bold: 'SFProDisplay-Bold',
    fallback: "'SFProDisplay-Regular', -apple-system, 'Helvetica Neue', sans-serif",
    monoFallback: "'SFProDisplay-Regular', 'Menlo', 'Courier New', monospace",
  },

  typography: {
    hudMicro: {
      fontSize: 11,
      textTransform: 'uppercase' as const,
      letterSpacing: 0.5,
      fontWeight: '500' as const,
      color: '#86868b',
    },
    dataLarge: {
      fontSize: 34,
      fontWeight: '700' as const,
      letterSpacing: -0.5,
      fontVariant: ['tabular-nums' as const],
    },
    dataSmall: {
      fontSize: 13,
      fontWeight: '400' as const,
      fontVariant: ['tabular-nums' as const],
    },
  },

  spacing: {
    xs: 4,
    sm: 8,
    md: 16,
    lg: 24,
    xl: 32,
    xxl: 48,
  },

  borderRadius: {
    sm: 8,
    md: 12,
    lg: 16,
    xl: 20,
    round: 999,
  },

  // Liquid Glass effects
  glass: {
    card: {
      background: 'linear-gradient(135deg, rgba(255,255,255,0.85), rgba(255,255,255,0.45))',
      backdropFilter: 'blur(40px) saturate(180%)',
      border: '1px solid rgba(255,255,255,0.6)',
      boxShadow: '0 8px 32px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.8)',
      borderRadius: 20,
    },
    cardSubtle: {
      background: 'linear-gradient(135deg, rgba(255,255,255,0.75), rgba(255,255,255,0.35))',
      backdropFilter: 'blur(30px) saturate(150%)',
      border: '1px solid rgba(255,255,255,0.5)',
      boxShadow: '0 4px 16px rgba(0,0,0,0.04), inset 0 1px 0 rgba(255,255,255,0.7)',
      borderRadius: 14,
    },
    pill: {
      background: 'linear-gradient(135deg, rgba(255,255,255,0.7), rgba(255,255,255,0.3))',
      backdropFilter: 'blur(20px) saturate(140%)',
      border: '1px solid rgba(255,255,255,0.4)',
      boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.6)',
      borderRadius: 12,
    },
    tabBar: {
      background: 'rgba(255,255,255,0.75)',
      backdropFilter: 'blur(40px) saturate(180%)',
      borderTop: '1px solid rgba(0,0,0,0.06)',
    },
  },

  shadows: {
    cp2077Yellow: {
      shadowColor: '#007AFF',
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.15,
      shadowRadius: 12,
      elevation: 8,
    },
    neonCyan: {
      shadowColor: '#007AFF',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.12,
      shadowRadius: 8,
      elevation: 6,
    },
    neonMagenta: {
      shadowColor: '#AF52DE',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.1,
      shadowRadius: 6,
      elevation: 4,
    },
    card: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 4 },
      shadowOpacity: 0.06,
      shadowRadius: 16,
      elevation: 4,
    },
    hudGlow: {
      shadowColor: '#007AFF',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.08,
      shadowRadius: 20,
      elevation: 2,
    },
    glass: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.06,
      shadowRadius: 32,
      elevation: 6,
    },
  },
} as const;

export type Theme = typeof theme;

// CSS variables version for web/electron
export const cssTheme = `
  /* SF Pro Display — Apple's system font, loaded from server */
  @font-face {
    font-family: 'SFProDisplay-Regular';
    src: url('/assets/fonts/SFProDisplay-Regular.otf') format('opentype');
    font-weight: 400;
    font-style: normal;
    font-display: swap;
  }
  @font-face {
    font-family: 'SFProDisplay-Light';
    src: url('/assets/fonts/SFProDisplay-Light.otf') format('opentype');
    font-weight: 300;
    font-style: normal;
    font-display: swap;
  }
  @font-face {
    font-family: 'SFProDisplay-Medium';
    src: url('/assets/fonts/SFProDisplay-Medium.otf') format('opentype');
    font-weight: 500;
    font-style: normal;
    font-display: swap;
  }
  @font-face {
    font-family: 'SFProDisplay-Semibold';
    src: url('/assets/fonts/SFProDisplay-Semibold.otf') format('opentype');
    font-weight: 600;
    font-style: normal;
    font-display: swap;
  }
  @font-face {
    font-family: 'SFProDisplay-Bold';
    src: url('/assets/fonts/SFProDisplay-Bold.otf') format('opentype');
    font-weight: 700;
    font-style: normal;
    font-display: swap;
  }

  :root {
    --bg-primary: ${theme.colors.background};
    --bg-dark: ${theme.colors.backgroundDark};
    --bg-light: ${theme.colors.backgroundLight};
    --bg-card: ${theme.colors.backgroundCard};
    --bg-hud: ${theme.colors.backgroundHUD};

    --cp2077-yellow: ${theme.colors.cp2077Yellow};
    --cp2077-yellow-dim: ${theme.colors.cp2077YellowDim};
    --cp2077-yellow-glow: ${theme.colors.cp2077YellowGlow};
    --neon-cyan: ${theme.colors.neonCyan};
    --neon-cyan-dim: ${theme.colors.neonCyanDim};
    --neon-cyan-glow: ${theme.colors.neonCyanGlow};
    --neon-magenta: ${theme.colors.neonMagenta};
    --neon-magenta-glow: ${theme.colors.neonMagentaGlow};
    --neon-red: ${theme.colors.neonRed};
    --neon-green: ${theme.colors.neonGreen};
    --neon-blue: ${theme.colors.neonBlue};
    --cold-gray: ${theme.colors.coldGray};
    --ice-white: ${theme.colors.iceWhite};

    --text-primary: ${theme.colors.textPrimary};
    --text-secondary: ${theme.colors.textSecondary};
    --text-muted: ${theme.colors.textMuted};
    --text-white: ${theme.colors.textWhite};
    --text-cyan: ${theme.colors.textCyan};

    --profit: ${theme.colors.profit};
    --loss: ${theme.colors.loss};

    --border: ${theme.colors.border};
    --border-active: ${theme.colors.borderActive};

    --glass-bg: rgba(255, 255, 255, 0.75);
    --glass-bg-opaque: rgba(255, 255, 255, 0.85);
    --glass-border: rgba(255, 255, 255, 0.6);
    --glass-blur: blur(40px) saturate(180%);
    --glass-shadow: 0 8px 32px rgba(0,0,0,0.06);
    --glass-inner: inset 0 1px 0 rgba(255,255,255,0.8);

    --font-primary: 'SFProDisplay-Regular', -apple-system, 'Helvetica Neue', sans-serif;
    --font-heading: 'SFProDisplay-Bold', -apple-system, 'Helvetica Neue', sans-serif;
    --font-mono: 'SFProDisplay-Regular', 'Menlo', 'Courier New', monospace;

    --radius-sm: ${theme.borderRadius.sm}px;
    --radius-md: ${theme.borderRadius.md}px;
    --radius-lg: ${theme.borderRadius.lg}px;
    --radius-xl: ${theme.borderRadius.xl}px;
  }

  * {
    font-family: var(--font-primary);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  body {
    background-color: var(--bg-primary);
    color: var(--text-primary);
    margin: 0;
    padding: 0;
  }

  h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-heading);
    font-weight: 700;
    letter-spacing: -0.3px;
    color: var(--text-primary);
  }

  h1 { font-size: 34px; letter-spacing: -0.5px; }
  h2 { font-size: 28px; letter-spacing: -0.4px; }
  h3 { font-size: 22px; letter-spacing: -0.3px; }
  h4, h5, h6 { font-size: 17px; letter-spacing: -0.2px; }

  /* Liquid Glass Card */
  .glass-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.85), rgba(255,255,255,0.45));
    backdrop-filter: blur(40px) saturate(180%);
    -webkit-backdrop-filter: blur(40px) saturate(180%);
    border: 1px solid rgba(255,255,255,0.6);
    border-radius: var(--radius-xl);
    padding: 20px;
    box-shadow: var(--glass-shadow), var(--glass-inner);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
  }

  .glass-card:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 40px rgba(0,0,0,0.08), var(--glass-inner);
  }

  /* Subtle Glass Card */
  .glass-card-subtle {
    background: linear-gradient(135deg, rgba(255,255,255,0.75), rgba(255,255,255,0.35));
    backdrop-filter: blur(30px) saturate(150%);
    -webkit-backdrop-filter: blur(30px) saturate(150%);
    border: 1px solid rgba(255,255,255,0.5);
    border-radius: var(--radius-lg);
    padding: 14px;
    box-shadow: 0 4px 16px rgba(0,0,0,0.04), inset 0 1px 0 rgba(255,255,255,0.7);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
  }

  /* Glass Pill */
  .glass-pill {
    background: linear-gradient(135deg, rgba(255,255,255,0.7), rgba(255,255,255,0.3));
    backdrop-filter: blur(20px) saturate(140%);
    -webkit-backdrop-filter: blur(20px) saturate(140%);
    border: 1px solid rgba(255,255,255,0.4);
    border-radius: var(--radius-md);
    padding: 10px 14px;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.6);
  }

  /* Glass Tab Bar */
  .glass-tab-bar {
    background: rgba(255,255,255,0.75);
    backdrop-filter: blur(40px) saturate(180%);
    -webkit-backdrop-filter: blur(40px) saturate(180%);
    border-top: 1px solid rgba(0,0,0,0.06);
    padding: 8px 0;
  }

  /* Apple-style labels */
  .label-primary {
    font-size: 17px;
    font-weight: 600;
    color: var(--text-primary);
    letter-spacing: -0.2px;
  }

  .label-secondary {
    font-size: 15px;
    font-weight: 400;
    color: var(--text-secondary);
  }

  .label-caption {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .financial-num {
    font-family: var(--font-primary);
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  .data-large {
    font-family: var(--font-heading);
    font-weight: 700;
    font-size: 34px;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
    letter-spacing: -0.5px;
    color: var(--text-primary);
  }

  .data-small {
    font-family: var(--font-primary);
    font-size: 13px;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  /* Status colors */
  .profit { color: var(--profit); }
  .loss { color: var(--loss); }

  /* Animations — smooth Apple-style */
  @keyframes fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .fade-in {
    animation: fade-in 0.4s ease-out;
  }

  @keyframes scale-in {
    from { opacity: 0; transform: scale(0.95); }
    to { opacity: 1; transform: scale(1); }
  }
  .scale-in {
    animation: scale-in 0.3s ease-out;
  }

  @keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }
  .shimmer {
    background: linear-gradient(90deg, rgba(255,255,255,0) 0%, rgba(255,255,255,0.4) 50%, rgba(255,255,255,0) 100%);
    background-size: 200% 100%;
    animation: shimmer 2s ease-in-out infinite;
  }

  @keyframes pulse-soft {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }
  .pulse-live {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--neon-green);
    animation: pulse-soft 2s ease-in-out infinite;
  }

  /* Tick animations for price changes */
  @keyframes tick-up {
    0% { background-color: rgba(52, 199, 89, 0.15); }
    100% { background-color: transparent; }
  }
  @keyframes tick-down {
    0% { background-color: rgba(255, 59, 48, 0.15); }
    100% { background-color: transparent; }
  }
  .tick-up { animation: tick-up 0.5s ease-out; }
  .tick-down { animation: tick-down 0.5s ease-out; }

  /* Progress bar */
  .progress-track {
    height: 4px;
    background: rgba(0,0,0,0.06);
    border-radius: 2px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.6s ease;
  }

  /* Chart styling */
  .tv-lightweight-charts {
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
  }

  /* Confidence badges */
  .confidence-high { color: ${theme.colors.confidenceHigh}; }
  .confidence-medium { color: ${theme.colors.confidenceMedium}; }
  .confidence-low { color: ${theme.colors.confidenceLow}; }

  /* Scrollbar (minimal Apple-style) */
  ::-webkit-scrollbar {
    width: 6px;
    height: 6px;
  }
  ::-webkit-scrollbar-track {
    background: transparent;
  }
  ::-webkit-scrollbar-thumb {
    background: rgba(0,0,0,0.15);
    border-radius: 3px;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: rgba(0,0,0,0.25);
  }

  /* Selection */
  ::selection {
    background: rgba(0, 122, 255, 0.2);
  }

  /* ═══════════════════════════════════════════════════════════
     iOS 26 LIQUID GLASS - DARK MODE (auto by time of day)
     Dark: 6PM-6AM local time | Light: 6AM-6PM local time
     ═══════════════════════════════════════════════════════════ */

  /* Dark mode variables - applied by JS based on time */
  body.dark-mode {
    --bg-primary: #000000;
    --bg-dark: #1c1c1e;
    --bg-light: #1c1c1e;
    --bg-card: #1c1c1e;
    --text-primary: #f5f5f7;
    --text-secondary: #a1a1a6;
    --text-muted: #636366;
    --border: rgba(255, 255, 255, 0.08);
    --border-active: #0a84ff;
    --profit: #30d158;
    --loss: #ff453a;
    --glass-bg: rgba(44, 44, 46, 0.75);
    --glass-bg-opaque: rgba(44, 44, 46, 0.88);
    --glass-border: rgba(255, 255, 255, 0.12);
    --glass-shadow: 0 8px 32px rgba(0,0,0,0.4);
    --glass-inner: inset 0 1px 0 rgba(255,255,255,0.08);
    --neon-cyan: #0a84ff;
    --neon-green: #30d158;
    --neon-red: #ff453a;
    --neon-orange: #ff9f0a;
    background-color: #000000 !important;
    color: #f5f5f7 !important;
  }

  /* Dark mode glass cards - iOS 26 Liquid Glass on dark */
  body.dark-mode .glass-card,
  body.dark-mode [style*="backgroundColor: rgb(255, 255, 255)"],
  body.dark-mode [style*="background-color: #ffffff"] {
    background: linear-gradient(135deg, rgba(58,58,60,0.65), rgba(44,44,46,0.35)) !important;
    border-color: rgba(255,255,255,0.1) !important;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.06) !important;
  }

  /* Dark mode tab bar */
  body.dark-mode .glass-tab-bar,
  body.dark-mode [style*="backgroundColor: rgba(255,255,255"] {
    background: rgba(28, 28, 30, 0.8) !important;
    border-top-color: rgba(255,255,255,0.06) !important;
  }

  /* Dark mode text overrides */
  body.dark-mode [style*="color: rgb(29, 29, 31)"],
  body.dark-mode [style*="color: #1d1d1f"] {
    color: #f5f5f7 !important;
  }
  body.dark-mode [style*="color: rgb(134, 134, 139)"],
  body.dark-mode [style*="color: #86868b"] {
    color: #a1a1a6 !important;
  }

  /* Dark mode backgrounds */
  body.dark-mode [style*="backgroundColor: #f2f2f7"],
  body.dark-mode [style*="background-color: #f2f2f7"] {
    background-color: #000000 !important;
  }
  body.dark-mode [style*="backgroundColor: #ffffff"],
  body.dark-mode [style*="background-color: #ffffff"],
  body.dark-mode [style*="backgroundColor: rgb(255, 255, 255)"] {
    background-color: #1c1c1e !important;
  }

  /* Dark mode scrollbar */
  body.dark-mode ::-webkit-scrollbar-thumb {
    background: rgba(255,255,255,0.2);
  }
  body.dark-mode ::-webkit-scrollbar-thumb:hover {
    background: rgba(255,255,255,0.3);
  }

  /* Smooth transition between modes */
  body {
    transition: background-color 0.5s ease, color 0.5s ease;
  }
`;

// Divider and status CSS
export const hudDividerCss = `
  .glass-divider {
    border: none;
    border-top: 1px solid rgba(0,0,0,0.06);
    margin: 16px 0;
  }

  .status-online {
    color: var(--neon-green);
    animation: pulse-soft 2s ease-in-out infinite;
  }
  .status-offline {
    color: var(--neon-red);
  }

  .session-active {
    background: linear-gradient(90deg, transparent, rgba(0, 122, 255, 0.04), transparent);
    padding: 4px 0;
    border-radius: 8px;
  }
`;

// Strategy badge color helper (TradingLab 6-color system)
export const getStrategyColor = (strategy: string): string => {
  const map: Record<string, string> = {
    BLUE: theme.colors.strategyBlue,
    BLUE_A: theme.colors.strategyBlue,
    BLUE_B: theme.colors.strategyBlue,
    BLUE_C: theme.colors.strategyBlue,
    RED: theme.colors.strategyRed,
    PINK: theme.colors.strategyPink,
    WHITE: theme.colors.strategyWhite,
    BLACK: theme.colors.strategyBlack,
    GREEN: theme.colors.strategyGreen,
  };
  return map[strategy.toUpperCase()] || theme.colors.cp2077Yellow;
};

// Score color helper
export const getScoreColor = (score: number): string => {
  if (score >= 80) return theme.colors.neonGreen;
  if (score >= 60) return theme.colors.cp2077Yellow;
  if (score >= 40) return theme.colors.neonOrange;
  return theme.colors.neonRed;
};
