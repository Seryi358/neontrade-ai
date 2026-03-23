/**
 * NeonTrade AI - Cyberpunk Theme
 * Colors, fonts, and styling optimized for trading psychology.
 *
 * Neuromarketing principles applied:
 * - Dark backgrounds reduce cognitive fatigue during long sessions
 * - Cyan triggers trust (reads as "blue" to the brain's trust circuits)
 * - Neon green/red preserve universal profit/loss associations
 * - High contrast text ensures readability for financial data
 * - Glow effects used sparingly (<15% of screen) to maintain focus
 */

export const theme = {
  colors: {
    // Primary backgrounds (deep navy/near-black - reduces eye strain)
    background: '#0f0a1a',
    backgroundDark: '#0a0713',
    backgroundLight: '#1a1530',
    backgroundCard: '#161225',

    // Accent (neon pink - brand identity + urgency)
    neonPink: '#eb4eca',
    neonPinkDim: '#b33d9b',
    neonPinkGlow: 'rgba(235, 78, 202, 0.3)',

    // Secondary accents (trust + status)
    neonCyan: '#00f0ff',       // Trust, AI, technology
    neonCyanGlow: 'rgba(0, 240, 255, 0.3)',
    neonGreen: '#00ff88',      // Profit (softer green - less anxiety)
    neonRed: '#ff2e63',        // Loss (softer red - less panic-inducing)
    neonYellow: '#ffb800',     // Warning, caution, pending
    neonOrange: '#ff6b35',     // Alerts

    // Text (high readability hierarchy)
    textPrimary: '#eb4eca',
    textSecondary: '#e2e8f0',  // Brighter for better readability
    textMuted: '#8892a0',      // Blue-gray muted
    textWhite: '#f0e6ff',

    // Status (profit/loss - universal associations)
    profit: '#00ff88',
    loss: '#ff2e63',
    neutral: '#8892a0',
    warning: '#ffb800',

    // Confidence levels (for AI signals)
    confidenceHigh: '#00f0ff',
    confidenceMedium: '#ffb800',
    confidenceLow: '#8892a0',

    // Borders
    border: '#2a2445',
    borderActive: '#eb4eca',

    // Chart
    chartBullish: '#00ff88',
    chartBearish: '#ff2e63',
    chartGrid: '#1a1530',
  },

  fonts: {
    primary: 'TerminessNerdFont',
    mono: 'TerminessNerdFont',
    bold: 'TerminessNerdFont-Bold',
    italic: 'TerminessNerdFont-Italic',
    fallback: 'monospace',
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
    sm: 4,
    md: 8,
    lg: 12,
    xl: 16,
    round: 999,
  },

  shadows: {
    neonPink: {
      shadowColor: '#eb4eca',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.5,
      shadowRadius: 10,
      elevation: 10,
    },
    neonCyan: {
      shadowColor: '#00f0ff',
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.4,
      shadowRadius: 8,
      elevation: 8,
    },
    card: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.3,
      shadowRadius: 4,
      elevation: 4,
    },
  },
} as const;

export type Theme = typeof theme;

// CSS variables version for web/electron
export const cssTheme = `
  :root {
    --bg-primary: ${theme.colors.background};
    --bg-dark: ${theme.colors.backgroundDark};
    --bg-light: ${theme.colors.backgroundLight};
    --bg-card: ${theme.colors.backgroundCard};

    --neon-pink: ${theme.colors.neonPink};
    --neon-pink-dim: ${theme.colors.neonPinkDim};
    --neon-pink-glow: ${theme.colors.neonPinkGlow};
    --neon-cyan: ${theme.colors.neonCyan};
    --neon-cyan-glow: ${theme.colors.neonCyanGlow};
    --neon-green: ${theme.colors.neonGreen};
    --neon-red: ${theme.colors.neonRed};

    --text-primary: ${theme.colors.textPrimary};
    --text-secondary: ${theme.colors.textSecondary};
    --text-muted: ${theme.colors.textMuted};
    --text-white: ${theme.colors.textWhite};

    --profit: ${theme.colors.profit};
    --loss: ${theme.colors.loss};

    --border: ${theme.colors.border};
    --border-active: ${theme.colors.borderActive};

    --font-primary: 'TerminessNerdFont', 'Terminess Nerd Font', monospace;
    --font-mono: 'TerminessNerdFont', 'Terminess Nerd Font', monospace;

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

  /* Tabular numerals for financial data (prevents layout jitter) */
  .financial-num {
    font-variant-numeric: tabular-nums;
    font-feature-settings: "tnum";
  }

  /* Neon glow effects */
  .neon-text {
    color: var(--neon-pink);
    text-shadow: 0 0 7px var(--neon-pink-glow),
                 0 0 10px var(--neon-pink-glow),
                 0 0 21px var(--neon-pink-glow);
  }

  .neon-text-cyan {
    color: var(--neon-cyan);
    text-shadow: 0 0 7px var(--neon-cyan-glow),
                 0 0 10px var(--neon-cyan-glow);
  }

  .neon-border {
    border: 1px solid var(--neon-pink);
    box-shadow: 0 0 5px var(--neon-pink-glow),
                inset 0 0 5px var(--neon-pink-glow);
  }

  .neon-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px;
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
  }

  .neon-card:hover {
    border-color: var(--neon-pink);
    box-shadow: 0 0 10px var(--neon-pink-glow);
  }

  .profit { color: var(--profit); }
  .loss { color: var(--loss); }

  /* Price tick flash animation */
  @keyframes tick-up {
    0% { background-color: rgba(0, 255, 136, 0.2); }
    100% { background-color: transparent; }
  }
  @keyframes tick-down {
    0% { background-color: rgba(255, 46, 99, 0.2); }
    100% { background-color: transparent; }
  }
  .tick-up { animation: tick-up 0.4s ease-out; }
  .tick-down { animation: tick-down 0.4s ease-out; }

  /* Confidence gauge gradient */
  .confidence-high { color: ${theme.colors.confidenceHigh}; }
  .confidence-medium { color: ${theme.colors.confidenceMedium}; }
  .confidence-low { color: ${theme.colors.confidenceLow}; }
`;
