/**
 * NeonTrade AI - Cyberpunk 2077 Theme
 * Colors matched EXACTLY to user's Bitpunk KDE Plasma theme.
 * Font: Rajdhani (user's system font) — geometric, futuristic sans-serif.
 *
 * Design principles:
 * - Bitpunk yellow (#f3e600) as primary accent (ForegroundNeutral)
 * - Bitpunk cyan (#0abdc6) for tech/AI elements (DecorationFocus)
 * - Bitpunk magenta (#ea00d9) for critical alerts (DecorationHover)
 * - Angular, clipped corners (CP2077 UI signature)
 * - Scan lines, grid overlays, glitch effects
 * - HUD-style data presentation (trading = combat readiness)
 * - Bitpunk dark backgrounds (#0a0e14 window, #050505 view)
 */

export const theme = {
  colors: {
    // Primary backgrounds (EXACT Bitpunk KDE theme values)
    background: '#0a0e14',      // Bitpunk: Colors:Window BackgroundNormal (10,14,20)
    backgroundDark: '#050505',  // Bitpunk: Colors:View BackgroundNormal (5,5,5)
    backgroundLight: '#1c2632', // Bitpunk: Colors:Button BackgroundNormal (28,38,50)
    backgroundCard: '#131a24',  // Bitpunk: Colors:Tooltip BackgroundNormal (19,26,36)
    backgroundHUD: '#080c12',   // Derived: between View and Window BG

    // Bitpunk Primary accent — ForegroundNeutral yellow (243,230,0)
    cp2077Yellow: '#f3e600',
    cp2077YellowDim: '#a9a000',
    cp2077YellowGlow: 'rgba(243, 230, 0, 0.3)',

    // Bitpunk Cyan — DecorationFocus (10,189,198)
    neonCyan: '#0abdc6',
    neonCyanDim: '#08919a',
    neonCyanGlow: 'rgba(10, 189, 198, 0.3)',

    // Bitpunk Magenta — DecorationHover (234,0,217)
    neonMagenta: '#ea00d9',
    neonMagentaDim: '#bb00ae',
    neonMagentaGlow: 'rgba(234, 0, 217, 0.3)',

    // Bitpunk Red — ForegroundNegative (255,74,87)
    neonRed: '#ff4a57',
    neonRedDim: '#c83a44',
    neonRedGlow: 'rgba(255, 74, 87, 0.3)',

    // Bitpunk Green — Color2/ForegroundPositive (46,216,140)
    neonGreen: '#2ed88c',
    neonGreenDim: '#24aa6e',
    neonGreenGlow: 'rgba(46, 216, 140, 0.3)',
    neonOrange: '#ff6b35',      // Warning (no Bitpunk equivalent, kept)
    neonYellow: '#ffef4a',      // Caution/pending — Bitpunk Color3Intense (255,239,74)

    // Bitpunk accent colors
    neonBlue: '#08919a',        // Bitpunk: Color4/ForegroundVisited (8,145,154)
    coldGray: '#2a3a4d',        // Bitpunk: Color0Intense (42,58,77)
    iceWhite: '#e0e8f0',        // Bitpunk: ForegroundNormal (224,232,240)

    // Text (EXACT Bitpunk values)
    textPrimary: '#f3e600',     // Bitpunk: ForegroundNeutral (243,230,0)
    textSecondary: '#e0e8f0',   // Bitpunk: ForegroundNormal (224,232,240)
    textMuted: '#8a9bad',       // Bitpunk: ForegroundInactive (138,155,173)
    textWhite: '#f0eef5',       // Pure content text
    textCyan: '#0abdc6',        // Tech/AI text

    // Status
    profit: '#2ed88c',
    loss: '#ff4a57',
    neutral: '#8a9bad',
    warning: '#ffb800',

    // Confidence levels
    confidenceHigh: '#0abdc6',
    confidenceMedium: '#ffb800',
    confidenceLow: '#8a9bad',

    // Borders (angular CP2077 style — colder)
    border: '#1a2535',
    borderActive: '#f3e600',    // CP2077 yellow active border
    borderCyan: '#0abdc6',
    borderMagenta: '#ea00d9',

    // Chart
    chartBullish: '#2ed88c',
    chartBearish: '#ff4a57',
    chartGrid: '#111824',
    chartBackground: '#050505',
    chartGridLines: '#111824',
    chartCandleUp: '#2ed88c',
    chartCandleDown: '#ff4a57',
    chartVolumeUp: 'rgba(0, 255, 136, 0.3)',
    chartVolumeDown: 'rgba(218, 68, 83, 0.3)',
    chartCrosshair: '#f3e600',
    chartEma20: '#0abdc6',
    chartEma50: '#ea00d9',
    chartSupport: '#2ed88c',
    chartResistance: '#ff4a57',
    chartPivot: '#ffb800',
    chartTextColor: '#8a9bad',
    chartCurrentPrice: '#f3e600',

    // Strategy detection colors (TradingLab 6-color system, Bitpunk-aligned)
    strategyBlue: '#08919a',    // Bitpunk: Color4 (8,145,154)
    strategyRed: '#ff4a57',     // Bitpunk: ForegroundNegative (255,74,87)
    strategyPink: '#ea00d9',    // Bitpunk: DecorationHover (234,0,217)
    strategyWhite: '#e0e8f0',   // Bitpunk: ForegroundNormal (224,232,240)
    strategyBlack: '#8a9bad',   // Bitpunk: ForegroundInactive (138,155,173)
    strategyGreen: '#2ed88c',   // Bitpunk: Color2 (46,216,140)
    strategyDetected: '#f3e600', // Bitpunk: ForegroundNeutral (243,230,0)
  },

  fonts: {
    // Rajdhani — geometric, futuristic, perfect for CP2077 HUD aesthetic
    primary: 'Rajdhani',
    heading: 'Rajdhani-Bold',
    medium: 'Rajdhani-Medium',
    semibold: 'Rajdhani-SemiBold',
    light: 'Rajdhani-Light',
    mono: 'TerminessNerdFont',  // Keep monospace for code/data
    bold: 'Rajdhani-Bold',
    fallback: "'Rajdhani', 'Segoe UI', sans-serif",
    monoFallback: "'TerminessNerdFont', 'Fira Code', monospace",
  },

  typography: {
    hudMicro: {
      fontSize: 8,
      textTransform: 'uppercase' as const,
      letterSpacing: 3,
      fontFamily: 'Rajdhani-Medium',
      color: '#8a9bad',
    },
    dataLarge: {
      fontSize: 28,
      fontFamily: 'Rajdhani-Bold',
      fontVariant: ['tabular-nums' as const],
    },
    dataSmall: {
      fontSize: 12,
      fontFamily: 'TerminessNerdFont',
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
    sm: 2,    // Sharper — CP2077 angular style
    md: 4,
    lg: 8,
    xl: 12,
    round: 999,
  },

  shadows: {
    cp2077Yellow: {
      shadowColor: '#f3e600',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.5,
      shadowRadius: 12,
      elevation: 12,
    },
    neonCyan: {
      shadowColor: '#0abdc6',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.4,
      shadowRadius: 10,
      elevation: 10,
    },
    neonMagenta: {
      shadowColor: '#ea00d9',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.4,
      shadowRadius: 8,
      elevation: 8,
    },
    card: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.4,
      shadowRadius: 6,
      elevation: 6,
    },
    hudGlow: {
      shadowColor: '#f3e600',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.15,
      shadowRadius: 20,
      elevation: 4,
    },
  },
} as const;

export type Theme = typeof theme;

// CSS variables version for web/electron
export const cssTheme = `
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@300;400;500;600;700&display=swap');

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

    --font-primary: 'Rajdhani', 'Segoe UI', sans-serif;
    --font-heading: 'Rajdhani', sans-serif;
    --font-mono: 'TerminessNerdFont', 'Fira Code', monospace;

    --radius-sm: ${theme.borderRadius.sm}px;
    --radius-md: ${theme.borderRadius.md}px;
    --radius-lg: ${theme.borderRadius.lg}px;
  }

  * {
    font-family: var(--font-primary);
  }

  body {
    background-color: var(--bg-primary);
    color: var(--text-secondary);
    margin: 0;
    padding: 0;
  }

  /* -- CP2077 HUD Typography ----------------------------------------- */

  h1, h2, h3, h4, h5, h6 {
    font-family: var(--font-heading);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 5px;
    color: var(--cp2077-yellow);
  }

  h1 { letter-spacing: 6px; }
  h2 { letter-spacing: 5px; }
  h3 { letter-spacing: 4px; }
  h4, h5, h6 { letter-spacing: 4px; }

  /* HUD micro text — tiny uppercase labels */
  .hud-micro {
    font-family: var(--font-heading);
    font-weight: 500;
    font-size: 8px;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: var(--text-muted);
  }

  /* Tabular numerals for financial data */
  .financial-num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  /* Data display — large numbers */
  .data-large {
    font-family: var(--font-heading);
    font-weight: 700;
    font-size: 28px;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  /* Data display — small monospace numbers */
  .data-small {
    font-family: var(--font-mono);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  /* -- CP2077 Neon Text Effects -------------------------------------- */

  .neon-text {
    color: var(--cp2077-yellow);
    text-shadow: 0 0 7px var(--cp2077-yellow-glow),
                 0 0 14px var(--cp2077-yellow-glow),
                 0 0 28px var(--cp2077-yellow-glow);
  }

  .neon-text-cyan {
    color: var(--neon-cyan);
    text-shadow: 0 0 7px var(--neon-cyan-glow),
                 0 0 14px var(--neon-cyan-glow);
  }

  .neon-text-magenta {
    color: var(--neon-magenta);
    text-shadow: 0 0 7px var(--neon-magenta-glow),
                 0 0 14px var(--neon-magenta-glow);
  }

  /* -- CP2077 Card & Border Styles ----------------------------------- */

  .neon-border {
    border: 1px solid var(--cp2077-yellow);
    box-shadow: 0 0 5px var(--cp2077-yellow-glow),
                inset 0 0 5px var(--cp2077-yellow-glow);
  }

  .neon-border-cyan {
    border: 1px solid var(--neon-cyan);
    box-shadow: 0 0 5px var(--neon-cyan-glow),
                inset 0 0 5px var(--neon-cyan-glow);
  }

  .cp2077-card {
    background: var(--bg-card);
    border: 1px solid var(--cold-gray);
    border-left: 3px solid var(--cp2077-yellow);
    border-radius: var(--radius-sm);
    padding: 16px;
    position: relative;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
  }

  .cp2077-card:hover {
    border-color: var(--cp2077-yellow);
    box-shadow: 0 0 15px var(--cp2077-yellow-glow),
                inset 0 0 5px rgba(252, 238, 9, 0.05);
  }

  /* CP2077 header bar — thin line with yellow dot */
  .cp2077-header-bar {
    position: relative;
    padding-left: 16px;
    margin-bottom: 12px;
  }
  .cp2077-header-bar::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--cp2077-yellow);
    box-shadow: 0 0 6px var(--cp2077-yellow-glow);
    transform: translateY(-50%);
  }
  .cp2077-header-bar::after {
    content: '';
    position: absolute;
    left: 10px;
    top: 50%;
    right: 0;
    height: 1px;
    background: linear-gradient(90deg, var(--cp2077-yellow-dim), transparent);
    transform: translateY(-50%);
  }

  /* CP2077 clipped corner effect */
  .cp2077-clip {
    clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
  }

  .cp2077-clip-sm {
    clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));
  }

  /* -- CP2077 HUD Elements ------------------------------------------- */

  .hud-header {
    font-family: var(--font-heading);
    font-weight: 700;
    font-size: 14px;
    text-transform: uppercase;
    letter-spacing: 5px;
    color: var(--cp2077-yellow);
    border-bottom: 1px solid var(--cp2077-yellow);
    padding-bottom: 4px;
    margin-bottom: 12px;
  }

  .hud-label {
    font-family: var(--font-heading);
    font-weight: 500;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 2px;
    color: var(--text-muted);
  }

  .hud-value {
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 600;
    color: var(--text-white);
    text-shadow: 0 0 4px rgba(240, 238, 245, 0.2);
  }

  .hud-divider {
    border: none;
    border-top: 1px solid var(--cold-gray);
    margin: 12px 0;
    position: relative;
  }

  .hud-divider::after {
    content: '';
    position: absolute;
    top: -1px;
    left: 0;
    width: 40px;
    height: 1px;
    background: var(--cp2077-yellow);
  }

  /* -- Scan Lines (CP2077 CRT effect) -------------------------------- */

  .scan-lines {
    position: relative;
  }

  .scan-lines::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: repeating-linear-gradient(
      0deg,
      transparent,
      transparent 2px,
      rgba(0, 0, 0, 0.06) 2px,
      rgba(0, 0, 0, 0.06) 4px
    );
    pointer-events: none;
    z-index: 10;
  }

  /* -- CP2077 Grid Background ---------------------------------------- */

  .grid-bg {
    background-image:
      linear-gradient(rgba(93, 244, 254, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(93, 244, 254, 0.03) 1px, transparent 1px);
    background-size: 60px 60px;
  }

  /* -- Chromatic Hover (RGB channel split) ---------------------------- */

  .chromatic-hover {
    position: relative;
    transition: all 0.2s ease;
  }
  .chromatic-hover:hover {
    text-shadow:
      -1px 0 rgba(237, 0, 217, 0.6),
      1px 0 rgba(93, 244, 254, 0.6);
  }

  /* -- Data Flicker Animation ---------------------------------------- */

  @keyframes data-flicker {
    0% { opacity: 1; }
    5% { opacity: 0.4; letter-spacing: 2px; }
    10% { opacity: 0.8; content: '##.##'; }
    15% { opacity: 1; }
    100% { opacity: 1; }
  }
  .data-flicker {
    animation: data-flicker 0.6s ease-out;
  }

  /* -- Boot Line Animation ------------------------------------------- */

  @keyframes boot-line-fill {
    0% { width: 0; }
    100% { width: 100%; }
  }
  .boot-line {
    position: relative;
    height: 2px;
    background: var(--cold-gray);
    overflow: hidden;
  }
  .boot-line::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    background: var(--cp2077-yellow);
    box-shadow: 0 0 8px var(--cp2077-yellow-glow);
    animation: boot-line-fill 1.5s ease-out forwards;
  }

  /* -- Price Animations ---------------------------------------------- */

  .profit { color: var(--profit); }
  .loss { color: var(--loss); }

  @keyframes tick-up {
    0% { background-color: rgba(0, 255, 136, 0.25); }
    100% { background-color: transparent; }
  }
  @keyframes tick-down {
    0% { background-color: rgba(218, 68, 83, 0.25); }
    100% { background-color: transparent; }
  }
  .tick-up { animation: tick-up 0.4s ease-out; }
  .tick-down { animation: tick-down 0.4s ease-out; }

  /* CP2077 glitch effect (use sparingly on alerts) */
  @keyframes glitch {
    0% { transform: translate(0); }
    20% { transform: translate(-2px, 2px); }
    40% { transform: translate(-2px, -2px); }
    60% { transform: translate(2px, 2px); }
    80% { transform: translate(2px, -2px); }
    100% { transform: translate(0); }
  }
  .glitch { animation: glitch 0.3s ease-in-out; }

  /* Pulsing dot for live status */
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 4px var(--neon-green); }
    50% { opacity: 0.5; box-shadow: 0 0 8px var(--neon-green); }
  }
  .pulse-live {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--neon-green);
    animation: pulse 2s ease-in-out infinite;
  }

  /* HUD corner decorations */
  @keyframes corner-scan {
    0% { width: 0; }
    100% { width: 20px; }
  }

  .hud-corner::before,
  .hud-corner::after {
    content: '';
    position: absolute;
    background: var(--cp2077-yellow);
    height: 1px;
    animation: corner-scan 0.5s ease-out forwards;
  }
  .hud-corner::before { top: 0; left: 0; }
  .hud-corner::after { bottom: 0; right: 0; }

  /* -- Confidence Levels --------------------------------------------- */

  .confidence-high { color: ${theme.colors.confidenceHigh}; }
  .confidence-medium { color: ${theme.colors.confidenceMedium}; }
  .confidence-low { color: ${theme.colors.confidenceLow}; }

  /* -- Chart Styles -------------------------------------------------- */

  --chart-bg: ${theme.colors.chartBackground};
  --chart-grid: ${theme.colors.chartGridLines};
  --chart-candle-up: ${theme.colors.chartCandleUp};
  --chart-candle-down: ${theme.colors.chartCandleDown};
  --chart-volume-up: ${theme.colors.chartVolumeUp};
  --chart-volume-down: ${theme.colors.chartVolumeDown};
  --chart-crosshair: ${theme.colors.chartCrosshair};
  --chart-ema20: ${theme.colors.chartEma20};
  --chart-ema50: ${theme.colors.chartEma50};
  --chart-support: ${theme.colors.chartSupport};
  --chart-resistance: ${theme.colors.chartResistance};
  --chart-pivot: ${theme.colors.chartPivot};

  .tv-lightweight-charts {
    border-radius: var(--radius-sm);
    transition: box-shadow 0.3s ease;
  }
  .tv-lightweight-charts:hover {
    box-shadow: 0 0 15px rgba(252, 238, 9, 0.1),
                0 0 4px rgba(93, 244, 254, 0.08);
  }

  /* -- Glow Utilities ------------------------------------------------ */

  .glow-yellow {
    box-shadow: 0 0 8px rgba(252, 238, 9, 0.4),
                0 0 16px rgba(252, 238, 9, 0.15);
  }
  .glow-green {
    box-shadow: 0 0 6px rgba(0, 255, 136, 0.4),
                0 0 12px rgba(0, 255, 136, 0.15);
  }
  .glow-red {
    box-shadow: 0 0 6px rgba(218, 68, 83, 0.4),
                0 0 12px rgba(218, 68, 83, 0.15);
  }
  .glow-cyan {
    box-shadow: 0 0 6px rgba(93, 244, 254, 0.4),
                0 0 12px rgba(93, 244, 254, 0.15);
  }
  .glow-magenta {
    box-shadow: 0 0 6px rgba(237, 0, 217, 0.4),
                0 0 12px rgba(237, 0, 217, 0.15);
  }

  .text-glow-yellow {
    text-shadow: 0 0 6px rgba(252, 238, 9, 0.5);
  }
  .text-glow-green {
    text-shadow: 0 0 6px rgba(0, 255, 136, 0.5);
  }
  .text-glow-red {
    text-shadow: 0 0 6px rgba(218, 68, 83, 0.5);
  }
  .text-glow-cyan {
    text-shadow: 0 0 6px rgba(93, 244, 254, 0.5);
  }
  .text-glow-magenta {
    text-shadow: 0 0 6px rgba(237, 0, 217, 0.5);
  }

  /* -- Scrollbar (CP2077 thin style — cold gray) --------------------- */

  ::-webkit-scrollbar {
    width: 4px;
    height: 4px;
  }
  ::-webkit-scrollbar-track {
    background: var(--bg-dark);
  }
  ::-webkit-scrollbar-thumb {
    background: var(--cold-gray);
    border-radius: 2px;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: var(--cp2077-yellow);
  }
`;

// HUD-style divider component CSS (for web)
export const hudDividerCss = `
  .hud-divider-glow {
    border: none;
    border-top: 1px solid var(--cp2077-yellow-dim);
    margin: 16px 0;
    position: relative;
  }
  .hud-divider-glow::before {
    content: '';
    position: absolute;
    top: -1px;
    left: 50%;
    transform: translateX(-50%);
    width: 60px;
    height: 1px;
    background: var(--cp2077-yellow);
    box-shadow: 0 0 8px var(--cp2077-yellow-glow);
  }

  /* CP2077 Status indicator */
  .status-online {
    color: var(--neon-green);
    text-shadow: 0 0 4px rgba(0, 255, 136, 0.6);
    animation: pulse 2s ease-in-out infinite;
  }
  .status-offline {
    color: var(--neon-red);
    text-shadow: 0 0 4px rgba(218, 68, 83, 0.6);
  }

  /* Trading session indicator */
  .session-active {
    background: linear-gradient(90deg, transparent, rgba(252, 238, 9, 0.08), transparent);
    padding: 4px 0;
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

// Score color helper (confidence/quality tiers)
export const getScoreColor = (score: number): string => {
  if (score >= 80) return theme.colors.neonGreen;
  if (score >= 60) return theme.colors.cp2077Yellow;
  if (score >= 40) return theme.colors.neonOrange;
  return theme.colors.neonRed;
};
