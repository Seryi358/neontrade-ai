/**
 * NeonTrade AI - HUD Components
 * Reusable Cyberpunk 2077-styled UI components for the trading HUD.
 * Cold dark backgrounds, neon accents, angular design language.
 *
 * Components:
 * 1. HUDCard — Main card container with left accent border and corner brackets
 * 2. HUDHeader — Screen header with decorative line and dot
 * 3. HUDStatRow — Key-value row for financial data with optional trend
 * 4. HUDDivider — Horizontal line divider with optional centered label
 * 5. HUDBadge — Status/info badge (solid/outline/glow variants)
 * 6. HUDProgressBar — Score/progress bar with animated fill and glow
 * 7. HUDSectionTitle — Section separator ("▸ TITLE" + line)
 * 8. LoadingState — Boot sequence animation with filling line
 * 9. EmptyState — No data state with hexagon icon
 * 10. ErrorState — Error card with retry button
 * + SubNavPills — Pill-style sub-navigation bar
 */

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  ViewStyle,
  TouchableOpacity,
} from 'react-native';
import { theme } from '../theme/cyberpunk';

// ============================================================================
// 1. HUDCard — Main card container with left accent border and corner brackets
// ============================================================================

interface HUDCardProps {
  children: React.ReactNode;
  title?: string;
  accentColor?: string;
  borderColor?: string;
  backgroundColor?: string;
  style?: ViewStyle;
  pulseBorder?: boolean;
}

export function HUDCard({
  children,
  title,
  accentColor = theme.colors.cp2077Yellow,
  borderColor,
  backgroundColor,
  style,
}: HUDCardProps) {
  return (
    <View
      style={[
        hudStyles.card,
        {
          borderLeftColor: accentColor,
          ...(borderColor ? { borderColor } : {}),
          ...(backgroundColor ? { backgroundColor } : {}),
        },
        style,
      ]}
    >
      {/* Top-left corner bracket */}
      <View
        style={[
          hudStyles.cornerBracketTL,
          { borderTopColor: accentColor + '60' },
        ]}
      />
      {/* Bottom-right corner bracket */}
      <View
        style={[
          hudStyles.cornerBracketBR,
          {
            borderBottomColor: accentColor + '60',
            borderRightColor: accentColor + '60',
          },
        ]}
      />

      {title != null && (
        <View style={hudStyles.cardTitleRow}>
          <View
            style={[hudStyles.cardTitleDot, { backgroundColor: accentColor }]}
          />
          <Text style={[hudStyles.cardTitleText, { color: accentColor }]}>
            {title}
          </Text>
        </View>
      )}

      {children}
    </View>
  );
}

// ============================================================================
// 2. HUDHeader — Screen header with decorative line and dot
// ============================================================================

interface HUDHeaderProps {
  title: string;
  subtitle?: string;
  color?: string;
  rightElement?: React.ReactNode;
}

export function HUDHeader({
  title,
  subtitle,
  color = theme.colors.cp2077Yellow,
  rightElement,
}: HUDHeaderProps) {
  return (
    <View style={hudStyles.headerContainer}>
      <View style={hudStyles.headerContent}>
        <View style={hudStyles.headerTextBlock}>
          <Text style={[hudStyles.headerTitle, { color }]}>{title}</Text>
          {subtitle && (
            <Text style={hudStyles.headerSubtitle}>{subtitle}</Text>
          )}
        </View>
        {rightElement && (
          <View style={hudStyles.headerRight}>{rightElement}</View>
        )}
      </View>
      {/* Decorative line below with yellow dot */}
      <View style={hudStyles.headerLineRow}>
        <View style={[hudStyles.headerDot, { backgroundColor: color }]} />
        <View style={[hudStyles.headerLine, { backgroundColor: color + '50' }]} />
      </View>
    </View>
  );
}

// ============================================================================
// 3. HUDStatRow — Key-value display for financial data
// ============================================================================

interface HUDStatRowProps {
  label: string;
  value: string | number;
  valueColor?: string;
  mono?: boolean;
  large?: boolean;
  trend?: 'up' | 'down' | 'neutral';
}

export function HUDStatRow({
  label,
  value,
  valueColor,
  mono = true,
  large = false,
  trend,
}: HUDStatRowProps) {
  const trendIcon =
    trend === 'up' ? '\u25B2' : trend === 'down' ? '\u25BC' : '';
  const trendColor =
    trend === 'up'
      ? theme.colors.profit
      : trend === 'down'
        ? theme.colors.loss
        : undefined;

  const resolvedColor =
    valueColor || trendColor || theme.colors.textSecondary;

  return (
    <View style={hudStyles.statRow}>
      <Text style={hudStyles.statLabel}>{label}</Text>
      <View style={hudStyles.statValueRow}>
        {trendIcon !== '' && (
          <Text style={[hudStyles.statTrendIcon, { color: trendColor }]}>
            {trendIcon}
          </Text>
        )}
        <Text
          style={[
            hudStyles.statValue,
            { color: resolvedColor },
            mono && { fontFamily: theme.fonts.mono },
            large && { fontSize: 18 },
          ]}
        >
          {String(value)}
        </Text>
      </View>
    </View>
  );
}

// ============================================================================
// 4. HUDDivider — Horizontal line divider with optional centered label
// ============================================================================

interface HUDDividerProps {
  label?: string;
  color?: string;
  style?: ViewStyle;
}

export function HUDDivider({
  label,
  color = theme.colors.coldGray,
  style,
}: HUDDividerProps) {
  if (label) {
    return (
      <View style={[hudStyles.dividerWithLabel, style]}>
        <View style={[hudStyles.dividerLine, { backgroundColor: color }]} />
        <Text style={hudStyles.dividerLabelText}>{label}</Text>
        <View style={[hudStyles.dividerLine, { backgroundColor: color }]} />
      </View>
    );
  }

  return (
    <View style={[hudStyles.dividerContainer, style]}>
      <View
        style={[
          hudStyles.dividerAccent,
          { backgroundColor: theme.colors.cp2077YellowDim },
        ]}
      />
      <View style={[hudStyles.dividerLine, { backgroundColor: color }]} />
    </View>
  );
}

// ============================================================================
// 5. HUDBadge — Status/info badge (solid / outline / glow)
// ============================================================================

interface HUDBadgeProps {
  /** Text content for the badge */
  label?: string;
  /** Alias for label (either works) */
  text?: string;
  color?: string;
  small?: boolean;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'solid' | 'outline' | 'glow';
}

export function HUDBadge({
  label,
  text,
  color = theme.colors.cp2077Yellow,
  small = false,
  size,
  variant = 'solid',
}: HUDBadgeProps) {
  const displayText = label ?? text ?? '';

  // Resolve effective size: legacy `small` prop maps to 'sm'
  const effectiveSize = size ?? (small ? 'sm' : 'md');

  const sizeMap = {
    sm: { px: 6, py: 2, fs: 8, ls: 1 },
    md: { px: 10, py: 3, fs: 10, ls: 2 },
    lg: { px: 14, py: 6, fs: 13, ls: 2 },
  };
  const s = sizeMap[effectiveSize];

  const containerStyle: ViewStyle[] = [
    hudStyles.badge,
    {
      paddingHorizontal: s.px,
      paddingVertical: s.py,
    },
  ];

  if (variant === 'solid') {
    containerStyle.push({
      backgroundColor: color + '25',
      borderColor: color,
    });
  } else if (variant === 'outline') {
    containerStyle.push({
      backgroundColor: 'transparent',
      borderColor: color,
    });
  } else if (variant === 'glow') {
    containerStyle.push({
      backgroundColor: color + '22',
      borderColor: color,
      shadowColor: color,
      shadowOffset: { width: 0, height: 0 },
      shadowOpacity: 0.5,
      shadowRadius: 8,
      elevation: 6,
    });
  }

  return (
    <View style={containerStyle}>
      <Text
        style={[
          hudStyles.badgeText,
          { color, fontSize: s.fs, letterSpacing: s.ls },
        ]}
      >
        {displayText}
      </Text>
    </View>
  );
}

// ============================================================================
// 6. HUDProgressBar — Score/progress bar with animated fill and glow
// ============================================================================

interface HUDProgressBarProps {
  value: number; // 0-100
  label?: string;
  maxLabel?: string;
  color?: string;
  showValue?: boolean;
  showLabel?: boolean;
  height?: number;
}

export function HUDProgressBar({
  value,
  label,
  maxLabel,
  color = theme.colors.cp2077Yellow,
  showValue = true,
  showLabel,
  height = 6,
}: HUDProgressBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value));
  const animValue = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(animValue, {
      toValue: clampedValue,
      duration: 800,
      useNativeDriver: false,
    }).start();
  }, [clampedValue]);

  const widthInterp = animValue.interpolate({
    inputRange: [0, 100],
    outputRange: ['0%', '100%'],
  });

  // Determine if we show the label (backward compat: showValue or showLabel)
  const shouldShowLabel = showLabel ?? showValue;

  return (
    <View style={hudStyles.progressContainer}>
      {(label || shouldShowLabel) && (
        <View style={hudStyles.progressHeader}>
          {label ? (
            <Text style={hudStyles.progressLabel}>{label}</Text>
          ) : (
            <View />
          )}
          {shouldShowLabel && (
            <Text style={[hudStyles.progressValue, { color }]}>
              {clampedValue.toFixed(1)}%{maxLabel ? ` / ${maxLabel}` : ''}
            </Text>
          )}
        </View>
      )}
      <View style={[hudStyles.progressTrack, { height }]}>
        <Animated.View
          style={[
            hudStyles.progressFill,
            {
              width: widthInterp as unknown as number,
              height,
              backgroundColor: color,
            },
          ]}
        />
        {/* Glow overlay */}
        <Animated.View
          style={[
            hudStyles.progressGlow,
            {
              width: widthInterp as unknown as number,
              height: height + 4,
              backgroundColor: color,
              opacity: 0.2,
            },
          ]}
        />
      </View>
    </View>
  );
}

// ============================================================================
// 7. HUDSectionTitle — Section separator with title
// ============================================================================

interface HUDSectionTitleProps {
  title: string;
  color?: string;
  icon?: string; // unicode char, defaults to "▸"
}

export function HUDSectionTitle({
  title,
  color = theme.colors.cp2077Yellow,
  icon = '\u25B8',
}: HUDSectionTitleProps) {
  return (
    <View style={hudStyles.sectionTitleContainer}>
      <Text style={[hudStyles.sectionTitleText, { color }]}>
        {icon} {title}
      </Text>
      <View
        style={[hudStyles.sectionTitleLine, { backgroundColor: color + '50' }]}
      />
    </View>
  );
}

// ============================================================================
// 8. LoadingState — Boot sequence animation with filling line
// ============================================================================

interface LoadingStateProps {
  message?: string;
}

export function LoadingState({ message = 'LOADING DATA...' }: LoadingStateProps) {
  const lineAnim = useRef(new Animated.Value(0)).current;
  const textOpacity = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    // Boot line fills left to right, repeating
    Animated.loop(
      Animated.sequence([
        Animated.timing(lineAnim, {
          toValue: 1,
          duration: 1500,
          useNativeDriver: false,
        }),
        Animated.timing(lineAnim, {
          toValue: 0,
          duration: 0,
          useNativeDriver: false,
        }),
      ]),
    ).start();

    // Pulsing text opacity
    Animated.loop(
      Animated.sequence([
        Animated.timing(textOpacity, {
          toValue: 1,
          duration: 600,
          useNativeDriver: true,
        }),
        Animated.timing(textOpacity, {
          toValue: 0.4,
          duration: 600,
          useNativeDriver: true,
        }),
      ]),
    ).start();
  }, []);

  const lineWidth = lineAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });

  return (
    <View style={hudStyles.loadingContainer}>
      <Animated.Text
        style={[hudStyles.loadingText, { opacity: textOpacity }]}
      >
        {message}
      </Animated.Text>
      <View style={hudStyles.bootLineTrack}>
        <Animated.View
          style={[
            hudStyles.bootLineFill,
            { width: lineWidth as unknown as number },
          ]}
        />
      </View>
      <Text style={hudStyles.loadingSubtext}>
        NEONTRADE AI // SYSTEM INIT
      </Text>
    </View>
  );
}

// ============================================================================
// 9. EmptyState — No data state with icon
// ============================================================================

interface EmptyStateProps {
  /** Primary message or title */
  message?: string;
  title?: string;
  subtitle?: string;
  hint?: string;
  icon?: string;
}

export function EmptyState({
  message,
  title,
  subtitle,
  hint,
  icon = '\u2B21', // hexagon
}: EmptyStateProps) {
  const displayTitle = title ?? message ?? 'NO DATA';

  return (
    <View style={hudStyles.emptyContainer}>
      <Text style={hudStyles.emptyIcon}>{icon}</Text>
      <Text style={hudStyles.emptyTitle}>{displayTitle}</Text>
      {subtitle && (
        <Text style={hudStyles.emptySubtitle}>{subtitle}</Text>
      )}
      {hint && <Text style={hudStyles.emptyHint}>{hint}</Text>}
      <View style={hudStyles.emptyDecorLine} />
    </View>
  );
}

// ============================================================================
// 10. ErrorState — Error card with retry button
// ============================================================================

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <View style={hudStyles.errorContainer}>
      {/* Red left accent is via borderLeftColor */}
      <View style={hudStyles.errorContent}>
        <View style={hudStyles.errorHeaderRow}>
          <Text style={hudStyles.errorIconText}>{'\u26A0'}</Text>
          <Text style={hudStyles.errorTitle}>SYSTEM ERROR</Text>
        </View>
        <Text style={hudStyles.errorMessage}>{message}</Text>
        {onRetry && (
          <TouchableOpacity
            style={hudStyles.retryButton}
            onPress={onRetry}
            activeOpacity={0.7}
          >
            <Text style={hudStyles.retryButtonText}>
              {'\u27F3'} RETRY
            </Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

// ============================================================================
// SubNavPills — Pill-style sub-navigation bar
// ============================================================================

interface SubNavPillsProps {
  options: { key: string; label: string }[];
  activeKey: string;
  onSelect: (key: string) => void;
}

export function SubNavPills({ options, activeKey, onSelect }: SubNavPillsProps) {
  return (
    <View style={hudStyles.pillsContainer}>
      {options.map((opt) => {
        const isActive = opt.key === activeKey;
        return (
          <TouchableOpacity
            key={opt.key}
            style={[hudStyles.pill, isActive && hudStyles.pillActive]}
            onPress={() => onSelect(opt.key)}
          >
            <Text
              style={[
                hudStyles.pillText,
                isActive && hudStyles.pillTextActive,
              ]}
            >
              {opt.label}
            </Text>
          </TouchableOpacity>
        );
      })}
    </View>
  );
}

// ============================================================================
// Styles
// ============================================================================

const hudStyles = StyleSheet.create({
  // -- HUDCard --------------------------------------------------------
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.borderRadius.sm,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.cp2077Yellow,
    padding: theme.spacing.md,
    marginBottom: theme.spacing.md,
    position: 'relative',
    overflow: 'hidden',
  },
  cornerBracketTL: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: 14,
    height: 14,
    borderTopWidth: 1,
    borderLeftWidth: 0,
    borderColor: 'transparent',
  },
  cornerBracketBR: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 14,
    height: 14,
    borderBottomWidth: 1,
    borderRightWidth: 1,
    borderColor: 'transparent',
  },
  cardTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  cardTitleDot: {
    width: 5,
    height: 5,
    borderRadius: 3,
    marginRight: theme.spacing.sm,
  },
  cardTitleText: {
    fontFamily: theme.fonts.bold,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 4,
  },

  // -- HUDHeader ------------------------------------------------------
  headerContainer: {
    paddingVertical: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  headerContent: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
  },
  headerTextBlock: {
    flex: 1,
  },
  headerTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 20,
    letterSpacing: 6,
    textTransform: 'uppercase',
  },
  headerSubtitle: {
    fontFamily: theme.fonts.mono,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 3,
    textTransform: 'uppercase',
    marginTop: 2,
  },
  headerRight: {
    marginLeft: theme.spacing.md,
  },
  headerLineRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: theme.spacing.sm,
  },
  headerDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: theme.spacing.sm,
  },
  headerLine: {
    flex: 1,
    height: 1,
  },

  // -- HUDStatRow -----------------------------------------------------
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 5,
  },
  statLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    textTransform: 'uppercase',
    flex: 1,
  },
  statValueRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  statTrendIcon: {
    fontSize: 10,
    marginRight: 4,
  },
  statValue: {
    fontFamily: theme.fonts.semibold,
    fontSize: 14,
    color: theme.colors.textSecondary,
  },

  // -- HUDDivider -----------------------------------------------------
  dividerContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: theme.spacing.sm,
    height: 1,
  },
  dividerAccent: {
    width: 30,
    height: 1,
  },
  dividerLine: {
    flex: 1,
    height: 1,
  },
  dividerWithLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: theme.spacing.sm,
  },
  dividerLabelText: {
    fontFamily: theme.fonts.medium,
    fontSize: 9,
    color: theme.colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 3,
    marginHorizontal: theme.spacing.sm,
  },

  // -- HUDBadge -------------------------------------------------------
  badge: {
    borderWidth: 1,
    borderRadius: theme.borderRadius.sm,
    alignSelf: 'flex-start',
  },
  badgeText: {
    fontFamily: theme.fonts.heading,
    textTransform: 'uppercase',
  },

  // -- HUDProgressBar -------------------------------------------------
  progressContainer: {
    marginVertical: theme.spacing.xs,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  progressLabel: {
    fontFamily: theme.fonts.medium,
    fontSize: 10,
    color: theme.colors.textMuted,
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  progressValue: {
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  progressTrack: {
    backgroundColor: theme.colors.coldGray + '40',
    borderRadius: 1,
    overflow: 'hidden',
    position: 'relative',
  },
  progressFill: {
    position: 'absolute',
    top: 0,
    left: 0,
    borderRadius: 1,
  },
  progressGlow: {
    position: 'absolute',
    top: -2,
    left: 0,
    borderRadius: 4,
  },

  // -- HUDSectionTitle ------------------------------------------------
  sectionTitleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: theme.spacing.md,
    marginBottom: theme.spacing.sm,
  },
  sectionTitleText: {
    fontFamily: theme.fonts.bold,
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 4,
    marginRight: theme.spacing.sm,
  },
  sectionTitleLine: {
    flex: 1,
    height: 1,
  },

  // -- LoadingState ---------------------------------------------------
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.xxl,
    backgroundColor: theme.colors.backgroundDark,
  },
  loadingText: {
    fontFamily: theme.fonts.heading,
    fontSize: 14,
    color: theme.colors.cp2077Yellow,
    letterSpacing: 6,
    textTransform: 'uppercase',
    marginBottom: theme.spacing.lg,
  },
  bootLineTrack: {
    width: 200,
    height: 2,
    backgroundColor: theme.colors.coldGray + '40',
    borderRadius: 1,
    overflow: 'hidden',
  },
  bootLineFill: {
    height: 2,
    backgroundColor: theme.colors.cp2077Yellow,
    shadowColor: theme.colors.cp2077Yellow,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 6,
    elevation: 4,
  },
  loadingSubtext: {
    fontFamily: theme.fonts.mono,
    fontSize: 9,
    color: theme.colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 3,
    marginTop: theme.spacing.md,
  },

  // -- EmptyState -----------------------------------------------------
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: theme.spacing.xxl * 1.5,
    paddingHorizontal: theme.spacing.lg,
  },
  emptyIcon: {
    fontSize: 40,
    color: theme.colors.coldGray,
    marginBottom: theme.spacing.md,
    opacity: 0.5,
  },
  emptyTitle: {
    fontFamily: theme.fonts.heading,
    fontSize: 14,
    color: theme.colors.textMuted,
    letterSpacing: 3,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  emptySubtitle: {
    fontFamily: theme.fonts.primary,
    fontSize: 11,
    color: theme.colors.textMuted,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    opacity: 0.6,
    lineHeight: 18,
  },
  emptyHint: {
    fontFamily: theme.fonts.primary,
    fontSize: 10,
    color: theme.colors.neonCyan,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    letterSpacing: 1,
  },
  emptyDecorLine: {
    width: 40,
    height: 1,
    backgroundColor: theme.colors.coldGray,
    marginTop: theme.spacing.lg,
  },

  // -- ErrorState -----------------------------------------------------
  errorContainer: {
    backgroundColor: theme.colors.backgroundCard,
    borderWidth: 1,
    borderColor: theme.colors.neonRedDim,
    borderLeftWidth: 3,
    borderLeftColor: theme.colors.neonRed,
    borderRadius: theme.borderRadius.sm,
    overflow: 'hidden',
    marginVertical: theme.spacing.md,
  },
  errorContent: {
    padding: theme.spacing.md,
  },
  errorHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  errorIconText: {
    fontSize: 16,
    color: theme.colors.neonRed,
    marginRight: theme.spacing.sm,
    textShadowColor: theme.colors.neonRedGlow,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 12,
  },
  errorTitle: {
    fontFamily: theme.fonts.bold,
    fontSize: 12,
    color: theme.colors.neonRed,
    textTransform: 'uppercase',
    letterSpacing: 4,
  },
  errorMessage: {
    fontFamily: theme.fonts.primary,
    fontSize: 13,
    color: theme.colors.textSecondary,
    lineHeight: 18,
    marginBottom: theme.spacing.md,
  },
  retryButton: {
    backgroundColor: theme.colors.neonRed + '22',
    borderWidth: 1,
    borderColor: theme.colors.neonRed,
    borderRadius: theme.borderRadius.sm,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    alignSelf: 'flex-start',
  },
  retryButtonText: {
    fontFamily: theme.fonts.bold,
    fontSize: 12,
    color: theme.colors.neonRed,
    textTransform: 'uppercase',
    letterSpacing: 2,
  },

  // -- SubNavPills ----------------------------------------------------
  pillsContainer: {
    flexDirection: 'row',
    alignSelf: 'center',
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.borderRadius.round,
    overflow: 'hidden',
    marginBottom: theme.spacing.md,
  },
  pill: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    backgroundColor: 'transparent',
  },
  pillActive: {
    backgroundColor: theme.colors.cp2077Yellow,
  },
  pillText: {
    fontFamily: theme.fonts.heading,
    fontSize: 11,
    color: theme.colors.textMuted,
    letterSpacing: 3,
    textTransform: 'uppercase',
  },
  pillTextActive: {
    color: theme.colors.backgroundDark,
  },
});
