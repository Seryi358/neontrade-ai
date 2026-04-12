/**
 * Atlas - Glass UI Components
 * Apple Liquid Glass Light (iOS 26) styled UI components.
 * Translucent glass cards, soft shadows, SF Pro typography.
 *
 * Components:
 * 1. HUDCard — Glass card with blur backdrop, soft shadow, 20px radius
 * 2. HUDHeader — Large bold title (34px) with gray subtitle
 * 3. HUDStatRow — Key-value row with Apple typography and trend arrows
 * 4. HUDDivider — Simple 1px rgba(0,0,0,0.06) separator
 * 5. HUDBadge — Rounded pill with tinted background
 * 6. HUDProgressBar — Thin 4px track with rounded fill, no glow
 * 7. HUDSectionTitle — 13px uppercase label in secondary gray
 * 8. LoadingState — Centered spinner animation with message
 * 9. EmptyState — Centered icon + title + subtitle
 * 10. ErrorState — Red-tinted glass card with retry button
 * + SubNavPills — Apple segmented control with glass background
 */

import React, { useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Animated,
  ViewStyle,
  TouchableOpacity,
  ActivityIndicator,
} from 'react-native';
import { theme } from '../theme/apple-glass';

// ============================================================================
// 1. HUDCard — Glass card with blur, soft shadow, rounded corners
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
  accentColor,
  borderColor,
  backgroundColor,
  style,
}: HUDCardProps) {
  return (
    <View
      style={[
        glassStyles.card,
        borderColor ? { borderColor } : undefined,
        backgroundColor ? { backgroundColor } : undefined,
        style,
      ]}
    >
      {title != null && (
        <Text style={glassStyles.cardTitle}>{title}</Text>
      )}
      {children}
    </View>
  );
}

// ============================================================================
// 2. HUDHeader — Large bold title with gray subtitle
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
  color,
  rightElement,
}: HUDHeaderProps) {
  return (
    <View style={glassStyles.headerContainer}>
      <View style={glassStyles.headerContent}>
        <View style={glassStyles.headerTextBlock}>
          <Text style={glassStyles.headerTitle}>{title}</Text>
          {subtitle && (
            <Text style={glassStyles.headerSubtitle}>{subtitle}</Text>
          )}
        </View>
        {rightElement && (
          <View style={glassStyles.headerRight}>{rightElement}</View>
        )}
      </View>
    </View>
  );
}

// ============================================================================
// 3. HUDStatRow — Key-value display with Apple typography
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
    valueColor || trendColor || theme.colors.textPrimary;

  return (
    <View style={glassStyles.statRow}>
      <Text style={glassStyles.statLabel}>{label}</Text>
      <View style={glassStyles.statValueRow}>
        {trendIcon !== '' && (
          <Text style={[glassStyles.statTrendIcon, { color: trendColor }]}>
            {trendIcon}
          </Text>
        )}
        <Text
          style={[
            glassStyles.statValue,
            { color: resolvedColor },
            mono && { fontVariant: ['tabular-nums' as const] },
            large && { fontSize: 20 },
          ]}
        >
          {String(value)}
        </Text>
      </View>
    </View>
  );
}

// ============================================================================
// 4. HUDDivider — Simple 1px separator
// ============================================================================

interface HUDDividerProps {
  label?: string;
  color?: string;
  style?: ViewStyle;
}

export function HUDDivider({
  label,
  color,
  style,
}: HUDDividerProps) {
  if (label) {
    return (
      <View style={[glassStyles.dividerWithLabel, style]}>
        <View style={glassStyles.dividerLine} />
        <Text style={glassStyles.dividerLabelText}>{label}</Text>
        <View style={glassStyles.dividerLine} />
      </View>
    );
  }

  return (
    <View style={[glassStyles.dividerSimple, style]} />
  );
}

// ============================================================================
// 5. HUDBadge — Rounded pill with tinted background
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
    sm: { px: 8, py: 3, fs: 11, lh: 14 },
    md: { px: 12, py: 5, fs: 13, lh: 16 },
    lg: { px: 16, py: 7, fs: 15, lh: 18 },
  };
  const s = sizeMap[effectiveSize];

  const containerStyle: ViewStyle[] = [
    glassStyles.badge,
    {
      paddingHorizontal: s.px,
      paddingVertical: s.py,
    },
  ];

  // "glow" variant maps to "tinted" in Apple style (light color bg)
  if (variant === 'solid' || variant === 'glow') {
    containerStyle.push({
      backgroundColor: color + '18',
    });
  } else if (variant === 'outline') {
    containerStyle.push({
      backgroundColor: 'transparent',
      borderWidth: 1,
      borderColor: color + '40',
    });
  }

  return (
    <View style={containerStyle}>
      <Text
        style={[
          glassStyles.badgeText,
          { color, fontSize: s.fs, lineHeight: s.lh },
        ]}
      >
        {displayText}
      </Text>
    </View>
  );
}

// ============================================================================
// 6. HUDProgressBar — Apple-style thin track with rounded fill
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
  height = 4,
}: HUDProgressBarProps) {
  const clampedValue = Math.min(100, Math.max(0, value));
  const animValue = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(animValue, {
      toValue: clampedValue,
      duration: 600,
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
    <View style={glassStyles.progressContainer}>
      {(label || shouldShowLabel) && (
        <View style={glassStyles.progressHeader}>
          {label ? (
            <Text style={glassStyles.progressLabel}>{label}</Text>
          ) : (
            <View />
          )}
          {shouldShowLabel && (
            <Text style={[glassStyles.progressValue, { color }]}>
              {clampedValue.toFixed(1)}%{maxLabel ? ` / ${maxLabel}` : ''}
            </Text>
          )}
        </View>
      )}
      <View style={[glassStyles.progressTrack, { height, borderRadius: height / 2 }]}>
        <Animated.View
          style={[
            glassStyles.progressFill,
            {
              width: widthInterp as unknown as number,
              height,
              backgroundColor: color,
              borderRadius: height / 2,
            },
          ]}
        />
      </View>
    </View>
  );
}

// ============================================================================
// 7. HUDSectionTitle — Uppercase label in secondary gray
// ============================================================================

interface HUDSectionTitleProps {
  title: string;
  color?: string;
  icon?: string;
}

export function HUDSectionTitle({
  title,
  color = theme.colors.textSecondary,
}: HUDSectionTitleProps) {
  return (
    <View style={glassStyles.sectionTitleContainer}>
      <Text style={[glassStyles.sectionTitleText, { color }]}>
        {title}
      </Text>
    </View>
  );
}

// ============================================================================
// 8. LoadingState — Centered spinner with message
// ============================================================================

interface LoadingStateProps {
  message?: string;
}

export function LoadingState({ message = 'Loading...' }: LoadingStateProps) {
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeAnim, {
      toValue: 1,
      duration: 400,
      useNativeDriver: true,
    }).start();
  }, []);

  return (
    <Animated.View style={[glassStyles.loadingContainer, { opacity: fadeAnim }]}>
      <ActivityIndicator
        size="large"
        color={theme.colors.cp2077Yellow}
        style={glassStyles.loadingSpinner}
      />
      <Text style={glassStyles.loadingText}>{message}</Text>
    </Animated.View>
  );
}

// ============================================================================
// 9. EmptyState — Centered icon + title + subtitle
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
  icon = '\u25CB', // simple circle
}: EmptyStateProps) {
  const displayTitle = title ?? message ?? 'No Data';

  return (
    <View style={glassStyles.emptyContainer}>
      <Text style={glassStyles.emptyIcon}>{icon}</Text>
      <Text style={glassStyles.emptyTitle}>{displayTitle}</Text>
      {subtitle && (
        <Text style={glassStyles.emptySubtitle}>{subtitle}</Text>
      )}
      {hint && <Text style={glassStyles.emptyHint}>{hint}</Text>}
    </View>
  );
}

// ============================================================================
// 10. ErrorState — Red-tinted glass card with retry button
// ============================================================================

interface ErrorStateProps {
  message: string;
  onRetry?: () => void;
}

export function ErrorState({ message, onRetry }: ErrorStateProps) {
  return (
    <View style={glassStyles.errorContainer}>
      <View style={glassStyles.errorContent}>
        <View style={glassStyles.errorHeaderRow}>
          <Text style={glassStyles.errorIconText}>{'\u26A0'}</Text>
          <Text style={glassStyles.errorTitle}>Something went wrong</Text>
        </View>
        <Text style={glassStyles.errorMessage}>{message}</Text>
        {onRetry && (
          <TouchableOpacity
            style={glassStyles.retryButton}
            onPress={onRetry}
            activeOpacity={0.7}
          >
            <Text style={glassStyles.retryButtonText}>Try Again</Text>
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

// ============================================================================
// SubNavPills — Apple segmented control style
// ============================================================================

interface SubNavPillsProps {
  options: { key: string; label: string }[];
  activeKey: string;
  onSelect: (key: string) => void;
}

export function SubNavPills({ options, activeKey, onSelect }: SubNavPillsProps) {
  return (
    <View style={glassStyles.pillsContainer}>
      {options.map((opt) => {
        const isActive = opt.key === activeKey;
        return (
          <TouchableOpacity
            key={opt.key}
            style={[glassStyles.pill, isActive && glassStyles.pillActive]}
            onPress={() => onSelect(opt.key)}
            activeOpacity={0.7}
          >
            <Text
              style={[
                glassStyles.pillText,
                isActive && glassStyles.pillTextActive,
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
// Styles — Apple Liquid Glass Light
// ============================================================================

const glassStyles = StyleSheet.create({
  // -- HUDCard (Glass Card) -----------------------------------------------
  card: {
    backgroundColor: theme.colors.backgroundCard,
    borderRadius: theme.glass.card.borderRadius,
    borderWidth: 1,
    borderColor: theme.colors.glassBorder,
    padding: theme.spacing.md + 4,
    marginBottom: theme.spacing.md,
    // Soft shadow
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.06,
    shadowRadius: 16,
    elevation: 4,
  },
  cardTitle: {
    fontFamily: theme.fonts.semibold,
    fontWeight: '600',
    fontSize: 17,
    color: theme.colors.textPrimary,
    letterSpacing: -0.2,
    marginBottom: theme.spacing.sm + 4,
  },

  // -- HUDHeader ----------------------------------------------------------
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
    fontWeight: '700',
    fontSize: 34,
    letterSpacing: -0.5,
    color: theme.colors.textPrimary,
  },
  headerSubtitle: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 15,
    color: theme.colors.textSecondary,
    marginTop: 4,
  },
  headerRight: {
    marginLeft: theme.spacing.md,
  },

  // -- HUDStatRow ---------------------------------------------------------
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 6,
  },
  statLabel: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 13,
    color: theme.colors.textSecondary,
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
    fontWeight: '600',
    fontSize: 17,
    color: theme.colors.textPrimary,
  },

  // -- HUDDivider ---------------------------------------------------------
  dividerSimple: {
    height: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.06)',
    marginVertical: theme.spacing.sm,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.06)',
  },
  dividerWithLabel: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: theme.spacing.sm,
  },
  dividerLabelText: {
    fontFamily: theme.fonts.primary,
    fontWeight: '500',
    fontSize: 12,
    color: theme.colors.textMuted,
    marginHorizontal: theme.spacing.sm,
  },

  // -- HUDBadge -----------------------------------------------------------
  badge: {
    borderRadius: theme.borderRadius.md,
    alignSelf: 'flex-start',
  },
  badgeText: {
    fontFamily: theme.fonts.medium,
    fontWeight: '500',
  },

  // -- HUDProgressBar -----------------------------------------------------
  progressContainer: {
    marginVertical: theme.spacing.xs,
  },
  progressHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  progressLabel: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 13,
    color: theme.colors.textSecondary,
  },
  progressValue: {
    fontFamily: theme.fonts.semibold,
    fontWeight: '600',
    fontSize: 13,
  },
  progressTrack: {
    backgroundColor: 'rgba(0, 0, 0, 0.06)',
    overflow: 'hidden',
    position: 'relative',
  },
  progressFill: {
    position: 'absolute',
    top: 0,
    left: 0,
  },

  // -- HUDSectionTitle ----------------------------------------------------
  sectionTitleContainer: {
    marginTop: theme.spacing.lg,
    marginBottom: theme.spacing.sm,
  },
  sectionTitleText: {
    fontFamily: theme.fonts.medium,
    fontWeight: '500',
    fontSize: 13,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    color: theme.colors.textSecondary,
  },

  // -- LoadingState -------------------------------------------------------
  loadingContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: theme.spacing.xxl,
  },
  loadingSpinner: {
    marginBottom: theme.spacing.md,
  },
  loadingText: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 15,
    color: theme.colors.textSecondary,
  },

  // -- EmptyState ---------------------------------------------------------
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: theme.spacing.xxl * 1.5,
    paddingHorizontal: theme.spacing.lg,
  },
  emptyIcon: {
    fontSize: 44,
    color: theme.colors.textMuted,
    marginBottom: theme.spacing.md,
    opacity: 0.4,
  },
  emptyTitle: {
    fontFamily: theme.fonts.semibold,
    fontWeight: '600',
    fontSize: 17,
    color: theme.colors.textPrimary,
    textAlign: 'center',
  },
  emptySubtitle: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 15,
    color: theme.colors.textSecondary,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
    lineHeight: 20,
  },
  emptyHint: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 13,
    color: theme.colors.cp2077Yellow,
    textAlign: 'center',
    marginTop: theme.spacing.sm,
  },

  // -- ErrorState ---------------------------------------------------------
  errorContainer: {
    backgroundColor: 'rgba(255, 59, 48, 0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255, 59, 48, 0.15)',
    borderRadius: theme.glass.card.borderRadius,
    overflow: 'hidden',
    marginVertical: theme.spacing.md,
  },
  errorContent: {
    padding: theme.spacing.md + 4,
  },
  errorHeaderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: theme.spacing.sm,
  },
  errorIconText: {
    fontSize: 18,
    color: theme.colors.neonRed,
    marginRight: theme.spacing.sm,
  },
  errorTitle: {
    fontFamily: theme.fonts.semibold,
    fontWeight: '600',
    fontSize: 17,
    color: theme.colors.neonRed,
  },
  errorMessage: {
    fontFamily: theme.fonts.primary,
    fontWeight: '400',
    fontSize: 15,
    color: theme.colors.textSecondary,
    lineHeight: 20,
    marginBottom: theme.spacing.md,
  },
  retryButton: {
    backgroundColor: 'rgba(255, 59, 48, 0.1)',
    borderRadius: theme.borderRadius.md,
    paddingVertical: theme.spacing.sm + 2,
    paddingHorizontal: theme.spacing.md,
    alignSelf: 'flex-start',
  },
  retryButtonText: {
    fontFamily: theme.fonts.semibold,
    fontWeight: '600',
    fontSize: 15,
    color: theme.colors.neonRed,
  },

  // -- SubNavPills (Segmented Control) ------------------------------------
  pillsContainer: {
    flexDirection: 'row',
    alignSelf: 'center',
    backgroundColor: 'rgba(0, 0, 0, 0.04)',
    borderRadius: theme.borderRadius.md,
    padding: 2,
    marginBottom: theme.spacing.md,
  },
  pill: {
    paddingHorizontal: 20,
    paddingVertical: 8,
    borderRadius: theme.borderRadius.md - 2,
    backgroundColor: 'transparent',
  },
  pillActive: {
    backgroundColor: '#ffffff',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  pillText: {
    fontFamily: theme.fonts.medium,
    fontWeight: '500',
    fontSize: 13,
    color: theme.colors.textSecondary,
  },
  pillTextActive: {
    color: theme.colors.textPrimary,
    fontWeight: '600',
  },
});
