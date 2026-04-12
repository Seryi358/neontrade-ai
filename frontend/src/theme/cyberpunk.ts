/**
 * Atlas - Cyberpunk Theme
 * Colors matched EXACTLY to user's Daemon 2.0 KDE Plasma theme.
 * Font: Rajdhani EVERYWHERE — geometric, futuristic sans-serif.
 *
 * Daemon 2.0 palette:
 * - Backgrounds: deep burgundy/purple-black (#210e15, #14101f, #040a10)
 * - Primary accent: bright cyan (#5df4fe) — ForegroundNormal & DecorationFocus
 * - Secondary accent: neon purple (#ee00ff) — WM activeBackground
 * - Active blue: #3daee9 — ForegroundActive
 * - Negative/red: #fb3048 / #da4453
 * - Positive/green: #28c775 / #27ae60
 * - Neutral/yellow: #fdf500
 * - Orange: #f67400
 * - Magenta/visited: #cb1dcd
 * - Text muted: #a1a9b1
 */

export const theme = {
  colors: {
    // Primary backgrounds (EXACT Daemon 2.0 values)
    background: '#210e15',      // Daemon: Colors:Window BackgroundNormal (33,14,21)
    backgroundDark: '#040a10',  // Daemon: Colors:Tooltip BackgroundNormal (4,10,16)
    backgroundLight: '#14101f', // Daemon: Colors:Button BackgroundNormal (20,16,31)
    backgroundCard: '#1a0f18',  // Derived: between Window and Tooltip BG
    backgroundHUD: '#0d0610',   // Derived: darker variant for HUD overlays

    // Daemon 2.0 Primary accent — DecorationFocus cyan (93,244,254)
    cp2077Yellow: '#5df4fe',    // Daemon primary — bright cyan (replaces Bitpunk yellow)
    cp2077YellowDim: '#3daee9', // Daemon: ForegroundActive (61,174,233)
    cp2077YellowGlow: 'rgba(93, 244, 254, 0.3)',

    // Daemon Cyan — same as primary (93,244,254)
    neonCyan: '#5df4fe',
    neonCyanDim: '#3daee9',
    neonCyanGlow: 'rgba(93, 244, 254, 0.3)',

    // Daemon Magenta/Purple — WM active (238,0,255) + Visited (203,29,205)
    neonMagenta: '#ee00ff',
    neonMagentaDim: '#cb1dcd',
    neonMagentaGlow: 'rgba(238, 0, 255, 0.3)',

    // Daemon Red — ForegroundNegative (251,48,72) / (218,68,83)
    neonRed: '#fb3048',
    neonRedDim: '#da4453',
    neonRedGlow: 'rgba(251, 48, 72, 0.3)',

    // Daemon Green — ForegroundPositive (40,199,117) / (39,174,96)
    neonGreen: '#28c775',
    neonGreenDim: '#27ae60',
    neonGreenGlow: 'rgba(40, 199, 117, 0.3)',
    neonOrange: '#f67400',      // Daemon: ForegroundNeutral (246,116,0)
    neonYellow: '#fdf500',      // Daemon: View ForegroundNeutral (253,245,0)

    // Daemon accent colors
    neonBlue: '#1d99f3',        // Daemon: ForegroundLink (29,153,243)
    coldGray: '#355d65',        // Daemon: Selection BackgroundNormal (53,93,101)
    iceWhite: '#fcfcfc',        // Daemon: Complementary ForegroundNormal (252,252,252)

    // Text (EXACT Daemon 2.0 values)
    textPrimary: '#5df4fe',     // Daemon: ForegroundNormal cyan (93,244,254)
    textSecondary: '#d1c5c0',   // Daemon: Tooltip ForegroundNormal (209,197,192)
    textMuted: '#a1a9b1',       // Daemon: ForegroundInactive (161,169,177)
    textWhite: '#fcfcfc',       // Daemon: Complementary ForegroundNormal (252,252,252)
    textCyan: '#5df4fe',        // Same as primary

    // Status
    profit: '#28c775',          // Daemon green
    loss: '#fb3048',            // Daemon red
    neutral: '#a1a9b1',         // Daemon muted
    warning: '#f67400',         // Daemon orange

    // Confidence levels
    confidenceHigh: '#5df4fe',  // Daemon cyan
    confidenceMedium: '#f67400', // Daemon orange
    confidenceLow: '#a1a9b1',  // Daemon muted

    // Borders
    border: '#2a1a22',          // Derived from Window BG lightened
    borderActive: '#5df4fe',    // Daemon cyan active border
    borderCyan: '#5df4fe',
    borderMagenta: '#ee00ff',

    // Chart
    chartBullish: '#28c775',
    chartBearish: '#fb3048',
    chartGrid: '#1a0f18',
    chartBackground: '#040a10',
    chartGridLines: '#1a0f18',
    chartCandleUp: '#28c775',
    chartCandleDown: '#fb3048',
    chartVolumeUp: 'rgba(40, 199, 117, 0.3)',
    chartVolumeDown: 'rgba(251, 48, 72, 0.3)',
    chartCrosshair: '#5df4fe',
    chartEma20: '#5df4fe',
    chartEma50: '#ee00ff',
    chartSupport: '#28c775',
    chartResistance: '#fb3048',
    chartPivot: '#f67400',
    chartTextColor: '#a1a9b1',
    chartCurrentPrice: '#fdf500',

    // Strategy detection colors (TradingLab 6-color system, Daemon-aligned)
    strategyBlue: '#3daee9',    // Daemon: ForegroundActive (61,174,233)
    strategyRed: '#fb3048',     // Daemon: ForegroundNegative (251,48,72)
    strategyPink: '#ee00ff',    // Daemon: WM activeBackground (238,0,255)
    strategyWhite: '#fcfcfc',   // Daemon: ForegroundNormal white (252,252,252)
    strategyBlack: '#a1a9b1',   // Daemon: ForegroundInactive (161,169,177)
    strategyGreen: '#28c775',   // Daemon: ForegroundPositive (40,199,117)
    strategyDetected: '#fdf500', // Daemon: ForegroundNeutral yellow (253,245,0)
  },

  fonts: {
    // Rajdhani EVERYWHERE — user's explicit request
    primary: 'Rajdhani',
    heading: 'Rajdhani-Bold',
    medium: 'Rajdhani-Medium',
    semibold: 'Rajdhani-SemiBold',
    light: 'Rajdhani-Light',
    mono: 'Rajdhani',           // Rajdhani even for mono/data (user wants Rajdhani everywhere)
    bold: 'Rajdhani-Bold',
    fallback: "'Rajdhani', 'Segoe UI', sans-serif",
    monoFallback: "'Rajdhani', 'Segoe UI', sans-serif",
  },

  typography: {
    hudMicro: {
      fontSize: 8,
      textTransform: 'uppercase' as const,
      letterSpacing: 3,
      fontFamily: 'Rajdhani-Medium',
      color: '#a1a9b1',
    },
    dataLarge: {
      fontSize: 28,
      fontFamily: 'Rajdhani-Bold',
      fontVariant: ['tabular-nums' as const],
    },
    dataSmall: {
      fontSize: 12,
      fontFamily: 'Rajdhani',
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
    sm: 2,
    md: 4,
    lg: 8,
    xl: 12,
    round: 999,
  },

  shadows: {
    cp2077Yellow: {
      shadowColor: '#5df4fe',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.5,
      shadowRadius: 12,
      elevation: 12,
    },
    neonCyan: {
      shadowColor: '#5df4fe',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.4,
      shadowRadius: 10,
      elevation: 10,
    },
    neonMagenta: {
      shadowColor: '#ee00ff',
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
      shadowColor: '#5df4fe',
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
    --font-mono: 'Rajdhani', sans-serif;

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

  .hud-micro {
    font-family: var(--font-heading);
    font-weight: 500;
    font-size: 8px;
    text-transform: uppercase;
    letter-spacing: 3px;
    color: var(--text-muted);
  }

  .financial-num {
    font-family: var(--font-primary);
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  .data-large {
    font-family: var(--font-heading);
    font-weight: 700;
    font-size: 28px;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  .data-small {
    font-family: var(--font-primary);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

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
                inset 0 0 5px rgba(93, 244, 254, 0.05);
  }

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

  .cp2077-clip {
    clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
  }

  .cp2077-clip-sm {
    clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));
  }

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
    font-family: var(--font-primary);
    font-size: 18px;
    font-weight: 600;
    color: var(--text-white);
    text-shadow: 0 0 4px rgba(252, 252, 252, 0.2);
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

  .grid-bg {
    background-image:
      linear-gradient(rgba(93, 244, 254, 0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(93, 244, 254, 0.03) 1px, transparent 1px);
    background-size: 60px 60px;
  }

  .chromatic-hover {
    position: relative;
    transition: all 0.2s ease;
  }
  .chromatic-hover:hover {
    text-shadow:
      -1px 0 rgba(238, 0, 255, 0.6),
      1px 0 rgba(93, 244, 254, 0.6);
  }

  @keyframes data-flicker {
    0% { opacity: 1; }
    5% { opacity: 0.4; letter-spacing: 2px; }
    10% { opacity: 0.8; }
    15% { opacity: 1; }
    100% { opacity: 1; }
  }
  .data-flicker {
    animation: data-flicker 0.6s ease-out;
  }

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

  .profit { color: var(--profit); }
  .loss { color: var(--loss); }

  @keyframes tick-up {
    0% { background-color: rgba(40, 199, 117, 0.25); }
    100% { background-color: transparent; }
  }
  @keyframes tick-down {
    0% { background-color: rgba(251, 48, 72, 0.25); }
    100% { background-color: transparent; }
  }
  .tick-up { animation: tick-up 0.4s ease-out; }
  .tick-down { animation: tick-down 0.4s ease-out; }

  @keyframes glitch {
    0% { transform: translate(0); }
    20% { transform: translate(-2px, 2px); }
    40% { transform: translate(-2px, -2px); }
    60% { transform: translate(2px, 2px); }
    80% { transform: translate(2px, -2px); }
    100% { transform: translate(0); }
  }
  .glitch { animation: glitch 0.3s ease-in-out; }

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

  .confidence-high { color: ${theme.colors.confidenceHigh}; }
  .confidence-medium { color: ${theme.colors.confidenceMedium}; }
  .confidence-low { color: ${theme.colors.confidenceLow}; }

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
    box-shadow: 0 0 15px rgba(93, 244, 254, 0.1),
                0 0 4px rgba(238, 0, 255, 0.08);
  }

  .glow-yellow {
    box-shadow: 0 0 8px rgba(93, 244, 254, 0.4),
                0 0 16px rgba(93, 244, 254, 0.15);
  }
  .glow-green {
    box-shadow: 0 0 6px rgba(40, 199, 117, 0.4),
                0 0 12px rgba(40, 199, 117, 0.15);
  }
  .glow-red {
    box-shadow: 0 0 6px rgba(251, 48, 72, 0.4),
                0 0 12px rgba(251, 48, 72, 0.15);
  }
  .glow-cyan {
    box-shadow: 0 0 6px rgba(93, 244, 254, 0.4),
                0 0 12px rgba(93, 244, 254, 0.15);
  }
  .glow-magenta {
    box-shadow: 0 0 6px rgba(238, 0, 255, 0.4),
                0 0 12px rgba(238, 0, 255, 0.15);
  }

  .text-glow-yellow {
    text-shadow: 0 0 6px rgba(93, 244, 254, 0.5);
  }
  .text-glow-green {
    text-shadow: 0 0 6px rgba(40, 199, 117, 0.5);
  }
  .text-glow-red {
    text-shadow: 0 0 6px rgba(251, 48, 72, 0.5);
  }
  .text-glow-cyan {
    text-shadow: 0 0 6px rgba(93, 244, 254, 0.5);
  }
  .text-glow-magenta {
    text-shadow: 0 0 6px rgba(238, 0, 255, 0.5);
  }

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

  .status-online {
    color: var(--neon-green);
    text-shadow: 0 0 4px rgba(40, 199, 117, 0.6);
    animation: pulse 2s ease-in-out infinite;
  }
  .status-offline {
    color: var(--neon-red);
    text-shadow: 0 0 4px rgba(251, 48, 72, 0.6);
  }

  .session-active {
    background: linear-gradient(90deg, transparent, rgba(93, 244, 254, 0.08), transparent);
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

// Score color helper
export const getScoreColor = (score: number): string => {
  if (score >= 80) return theme.colors.neonGreen;
  if (score >= 60) return theme.colors.cp2077Yellow;
  if (score >= 40) return theme.colors.neonOrange;
  return theme.colors.neonRed;
};
