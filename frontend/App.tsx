/**
 * Atlas - Main App
 * Apple Liquid Glass Light UI
 *
 * Navigation: 5 tabs (HQ, Trade, Market, Log, Settings)
 * TRADE/MARKET/LOG tabs use internal sub-navigation (state-based)
 */

import React, { useEffect, useRef, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  Text,
  View,
  StyleSheet,
  Animated,
  ScrollView,
  SafeAreaView,
  Platform,
} from 'react-native';
import { useFonts } from 'expo-font';
import { theme, cssTheme } from './src/theme/apple-glass';

// ── Error Boundary ──────────────────────────────────────

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: string }
> {
  state = { hasError: false, error: '' };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: `${error.name}: ${error.message}` };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <SafeAreaView style={errorStyles.container}>
          <Text style={errorStyles.icon}>!</Text>
          <Text style={errorStyles.title}>Something Went Wrong</Text>
          <View style={errorStyles.divider} />

          <ScrollView style={errorStyles.scrollArea}>
            <Text style={errorStyles.errorDetail}>{this.state.error}</Text>
          </ScrollView>

          <Text style={errorStyles.code}>An unexpected error occurred</Text>

          <Text
            style={errorStyles.rebootBtn}
            onPress={() => this.setState({ hasError: false, error: '' })}
          >
            Try Again
          </Text>
        </SafeAreaView>
      );
    }
    return this.props.children;
  }
}

const errorStyles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  icon: {
    fontSize: 48,
    color: '#FF3B30',
    fontWeight: '700',
    marginBottom: 8,
  },
  title: {
    color: '#1d1d1f',
    fontWeight: '600',
    fontSize: 22,
    letterSpacing: 0.3,
    marginBottom: 4,
  },
  divider: {
    width: '40%',
    height: StyleSheet.hairlineWidth,
    backgroundColor: 'rgba(0,0,0,0.12)',
    marginVertical: 16,
  },
  scrollArea: {
    maxHeight: 160,
    marginBottom: 12,
  },
  errorDetail: {
    color: '#86868b',
    fontSize: 13,
    textAlign: 'center',
    lineHeight: 18,
  },
  code: {
    color: '#aeaeb2',
    fontSize: 12,
    marginBottom: 24,
  },
  rebootBtn: {
    color: '#007AFF',
    fontWeight: '600',
    fontSize: 16,
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: 'rgba(0,122,255,0.08)',
    overflow: 'hidden',
  },
});

// ── Screen Imports ──────────────────────────────────────

import DashboardScreen from './src/screens/DashboardScreen';
import ChartScreen from './src/screens/ChartScreen';
import AnalysisScreen from './src/screens/AnalysisScreen';
import ManualModeScreen from './src/screens/ManualModeScreen';
import WatchlistScreen from './src/screens/WatchlistScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import JournalScreen from './src/screens/JournalScreen';
import ExamScreen from './src/screens/ExamScreen';
import CryptoScreen from './src/screens/CryptoScreen';
import SettingsScreen from './src/screens/SettingsScreen';

// ── Sub-Tab Navigator Component ─────────────────────────
// State-based sub-navigation for multi-screen tabs

interface SubTab {
  key: string;
  label: string;
  component: React.ComponentType<any>;
}

function SubTabScreen({ tabs }: { tabs: SubTab[] }) {
  const [activeTab, setActiveTab] = React.useState(0);
  const ActiveComponent = tabs[activeTab].component;

  return (
    <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
      {/* Sub-tab bar at top */}
      <SafeAreaView style={subTabStyles.safeArea}>
        <View style={subTabStyles.bar}>
          {tabs.map((tab, index) => {
            const isActive = index === activeTab;
            return (
              <Text
                key={tab.key}
                style={[
                  subTabStyles.tab,
                  isActive && subTabStyles.tabActive,
                ]}
                onPress={() => setActiveTab(index)}
              >
                {tab.label}
              </Text>
            );
          })}
        </View>
      </SafeAreaView>
      <ActiveComponent />
    </View>
  );
}

const subTabStyles = StyleSheet.create({
  safeArea: {
    backgroundColor: 'rgba(255,255,255,0.92)',
  },
  bar: {
    flexDirection: 'row',
    backgroundColor: 'rgba(255,255,255,0.92)',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: 'rgba(0,0,0,0.06)',
    paddingHorizontal: 8,
    paddingTop: 8,
  },
  tab: {
    flex: 1,
    textAlign: 'center',
    fontWeight: '600',
    fontSize: 13,
    letterSpacing: 0.2,
    color: '#8E8E93',
    paddingVertical: 10,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    color: '#007AFF',
    borderBottomColor: '#007AFF',
  },
});

// ── Combined Tab Screens ────────────────────────────────

function TradeScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'analysis', label: 'Scan', component: AnalysisScreen },
        { key: 'chart', label: 'Chart', component: ChartScreen },
        { key: 'manual', label: 'Manual', component: ManualModeScreen },
      ]}
    />
  );
}

function MarketScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'watchlist', label: 'Watchlist', component: WatchlistScreen },
        { key: 'crypto', label: 'Crypto', component: CryptoScreen },
      ]}
    />
  );
}

function LogScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'history', label: 'History', component: HistoryScreen },
        { key: 'journal', label: 'Journal', component: JournalScreen },
        { key: 'exam', label: 'Exam', component: ExamScreen },
      ]}
    />
  );
}

// ── Tab Bar Icon ────────────────────────────────────────

const TAB_ICONS: Record<string, string> = {
  HQ: '\u25C7',       // ◇
  TRADE: '\u25C8',    // ◈
  MARKET: '\u25C6',   // ◆
  LOG: '\u25A3',      // ▣
  SYS: '\u2699',      // ⚙
};

function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  return (
    <Text
      style={[
        tabIconStyles.icon,
        {
          color: focused ? '#007AFF' : '#8E8E93',
        },
      ]}
    >
      {TAB_ICONS[label] || label}
    </Text>
  );
}

const tabIconStyles = StyleSheet.create({
  icon: {
    fontSize: 18,
    marginTop: 2,
  },
});

// ── Boot / Loading Screen ───────────────────────────────

function BootScreen() {
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(opacity, {
      toValue: 1,
      duration: 600,
      useNativeDriver: true,
    }).start();
  }, [opacity]);

  return (
    <View style={bootStyles.container}>
      <Animated.Text style={[bootStyles.title, { opacity }]}>
        Atlas
      </Animated.Text>

      <Animated.Text style={[bootStyles.subtitle, { opacity }]}>
        Loading...
      </Animated.Text>
    </View>
  );
}

const bootStyles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontWeight: '700',
    fontSize: 28,
    color: '#1d1d1f',
    letterSpacing: 0.5,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 15,
    color: '#8E8E93',
    fontWeight: '400',
  },
});

// ── Main Tab Navigator ──────────────────────────────────

const Tab = createBottomTabNavigator();

export default function App() {
  const [fontsLoaded] = useFonts({
    'SFProDisplay-Regular': require('./src/assets/fonts/SFProDisplay-Regular.otf'),
    'SFProDisplay-Light': require('./src/assets/fonts/SFProDisplay-Light.otf'),
    'SFProDisplay-Medium': require('./src/assets/fonts/SFProDisplay-Medium.otf'),
    'SFProDisplay-Semibold': require('./src/assets/fonts/SFProDisplay-Semibold.otf'),
    'SFProDisplay-Bold': require('./src/assets/fonts/SFProDisplay-Bold.otf'),
  });

  // Timeout: load app after 3s even if fonts fail (web fallback to system fonts)
  const [fontTimeout, setFontTimeout] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setFontTimeout(true), 3000);
    return () => clearTimeout(timer);
  }, []);

  // Inject CSS theme with @font-face for SF Pro Display on web
  useEffect(() => {
    if (Platform.OS === 'web') {
      const existing = document.getElementById('atlas-theme-css');
      if (!existing) {
        const style = document.createElement('style');
        style.id = 'atlas-theme-css';
        style.textContent = cssTheme;
        document.head.appendChild(style);
      }
    }
  }, []);

  // Auto dark/light mode + iOS 26 Liquid Glass effect
  // Transforms React Native Web white cards into translucent glass panels
  useEffect(() => {
    if (Platform.OS !== 'web') return;

    // Dark mode color map
    const DARK_COLOR_MAP: Record<string, string> = {
      'rgb(29, 29, 31)': '#f5f5f7',
      'rgb(134, 134, 139)': '#a1a1a6',
      'rgb(174, 174, 178)': '#636366',
      'rgb(242, 242, 247)': '#000000',
    };

    // Cards/white backgrounds to transform (both modes get glass)
    const CARD_BG_LIGHT = 'rgb(255, 255, 255)';
    const GROUPED_BG_LIGHT = 'rgb(242, 242, 247)';

    let originalStyles = new WeakMap<HTMLElement, {
      color?: string; bg?: string; backdrop?: string;
      border?: string; boxShadow?: string; backgroundImage?: string;
    }>();

    const saveOriginal = (el: HTMLElement) => {
      if (!originalStyles.has(el)) {
        originalStyles.set(el, {
          color: el.style.color,
          bg: el.style.backgroundColor,
          backdrop: (el.style as any).backdropFilter,
          border: el.style.border,
          boxShadow: el.style.boxShadow,
          backgroundImage: el.style.backgroundImage,
        });
      }
    };

    const applyLiquidGlass = (isDark: boolean) => {
      // Root background gradient (iOS 26 style)
      if (isDark) {
        document.body.style.setProperty('background',
          'radial-gradient(ellipse at top, #1a1a2e 0%, #000000 60%, #000000 100%)',
          'important');
        document.body.style.setProperty('min-height', '100vh', 'important');
      } else {
        document.body.style.setProperty('background',
          'radial-gradient(ellipse at top, #f5f5f7 0%, #e8e8f0 100%)',
          'important');
      }

      const all = document.querySelectorAll('*') as NodeListOf<HTMLElement>;
      all.forEach(el => {
        saveOriginal(el);
        const cs = getComputedStyle(el);
        const color = cs.color;
        const bg = cs.backgroundColor;
        const rect = el.getBoundingClientRect();
        const isLarge = rect.width > 100 && rect.height > 40;

        // Dark mode: invert text colors
        if (isDark && DARK_COLOR_MAP[color]) {
          el.style.setProperty('color', DARK_COLOR_MAP[color], 'important');
        }

        // Liquid Glass transformation for card-like elements (white bg + large size)
        if (bg === CARD_BG_LIGHT && isLarge) {
          if (isDark) {
            // Dark glass: translucent dark with saturated blur
            el.style.setProperty('background',
              'linear-gradient(135deg, rgba(44,44,46,0.72) 0%, rgba(28,28,30,0.48) 100%)',
              'important');
            el.style.setProperty('backdrop-filter', 'blur(40px) saturate(200%)', 'important');
            (el.style as any).webkitBackdropFilter = 'blur(40px) saturate(200%)';
            el.style.setProperty('border', '1px solid rgba(255,255,255,0.12)', 'important');
            el.style.setProperty('box-shadow',
              '0 8px 32px rgba(0,0,0,0.5), inset 0 1px 0 rgba(255,255,255,0.08)',
              'important');
          } else {
            // Light glass: translucent white with blur
            el.style.setProperty('background',
              'linear-gradient(135deg, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0.55) 100%)',
              'important');
            el.style.setProperty('backdrop-filter', 'blur(40px) saturate(180%)', 'important');
            (el.style as any).webkitBackdropFilter = 'blur(40px) saturate(180%)';
            el.style.setProperty('border', '1px solid rgba(255,255,255,0.6)', 'important');
            el.style.setProperty('box-shadow',
              '0 8px 32px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.8)',
              'important');
          }
        }

        // Background layer (grouped background → black in dark mode)
        if (bg === GROUPED_BG_LIGHT && isDark) {
          el.style.setProperty('background-color', 'transparent', 'important');
        }
      });
    };

    const removeAllStyles = () => {
      document.body.style.removeProperty('background');
      document.body.style.removeProperty('min-height');
      const all = document.querySelectorAll('*') as NodeListOf<HTMLElement>;
      all.forEach(el => {
        const orig = originalStyles.get(el);
        if (orig) {
          if (orig.color !== undefined) el.style.color = orig.color;
          else el.style.removeProperty('color');
          if (orig.bg !== undefined) el.style.backgroundColor = orig.bg;
          else el.style.removeProperty('background-color');
          if (orig.backgroundImage !== undefined) el.style.backgroundImage = orig.backgroundImage;
          else el.style.removeProperty('background-image');
          if (orig.backdrop !== undefined) (el.style as any).backdropFilter = orig.backdrop;
          else el.style.removeProperty('backdrop-filter');
          (el.style as any).webkitBackdropFilter = '';
          if (orig.border !== undefined) el.style.border = orig.border;
          else el.style.removeProperty('border');
          if (orig.boxShadow !== undefined) el.style.boxShadow = orig.boxShadow;
          else el.style.removeProperty('box-shadow');
        }
      });
      originalStyles = new WeakMap();
    };

    let observer: MutationObserver | null = null;
    let currentMode: 'dark' | 'light' | null = null;

    const updateTheme = () => {
      const hour = new Date().getHours();
      const isDark = hour >= 18 || hour < 6;
      const newMode = isDark ? 'dark' : 'light';
      document.body.classList.toggle('dark-mode', isDark);

      if (newMode !== currentMode) {
        if (observer) { observer.disconnect(); observer = null; }
        if (currentMode !== null) removeAllStyles();
        currentMode = newMode;
        applyLiquidGlass(isDark);
        // MutationObserver re-applies to new elements
        observer = new MutationObserver(() => applyLiquidGlass(isDark));
        observer.observe(document.body, {
          childList: true, subtree: true,
          attributes: true, attributeFilter: ['style', 'class']
        });
      }
    };

    updateTheme();
    const interval = setInterval(updateTheme, 60000);
    return () => {
      clearInterval(interval);
      if (observer) observer.disconnect();
    };
  }, []);

  if (!fontsLoaded && !fontTimeout) {
    return <BootScreen />;
  }

  return (
    <ErrorBoundary>
      <SafeAreaView style={{ flex: 1, backgroundColor: '#f2f2f7' }}>
        <NavigationContainer>
          <StatusBar style="dark" />
          <Tab.Navigator
            screenOptions={{
              headerShown: false,
              tabBarStyle: {
                backgroundColor: 'rgba(255,255,255,0.92)',
                borderTopWidth: StyleSheet.hairlineWidth,
                borderTopColor: 'rgba(0,0,0,0.06)',
                height: 60,
                paddingBottom: 6,
                paddingTop: 6,
                elevation: 0,
              },
              tabBarActiveTintColor: '#007AFF',
              tabBarInactiveTintColor: '#8E8E93',
              tabBarLabelStyle: {
                fontWeight: '500',
                fontSize: 10,
                letterSpacing: 0.1,
              },
            }}
          >
            <Tab.Screen
              name="Dashboard"
              component={DashboardScreen}
              options={{
                tabBarLabel: 'Home',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="HQ" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Trade"
              component={TradeScreen}
              options={{
                tabBarLabel: 'Trade',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="TRADE" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Market"
              component={MarketScreen}
              options={{
                tabBarLabel: 'Market',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="MARKET" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Log"
              component={LogScreen}
              options={{
                tabBarLabel: 'Log',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="LOG" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Settings"
              component={SettingsScreen}
              options={{
                tabBarLabel: 'Settings',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="SYS" focused={focused} />
                ),
              }}
            />
          </Tab.Navigator>
        </NavigationContainer>
      </SafeAreaView>
    </ErrorBoundary>
  );
}
