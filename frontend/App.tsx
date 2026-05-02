/**
 * Atlas - Main App
 * Apple Liquid Glass Light UI
 *
 * Navigation: 5 tabs (HQ, Trade, Market, Log, Settings)
 * TRADE/MARKET/LOG tabs use internal sub-navigation (state-based)
 */

import React, { useEffect, useRef, useState } from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer, useIsFocused } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import {
  Text,
  View,
  StyleSheet,
  Animated,
  ScrollView,
  SafeAreaView,
  Platform,
  TouchableOpacity,
} from 'react-native';
import { useFonts } from 'expo-font';
import Svg, { Circle, Line, Path, Polyline, Rect } from 'react-native-svg';
import { theme, cssTheme } from './src/theme/apple-glass';
import EngineDot from './src/components/visual/EngineDot';
import { useEngineState } from './src/hooks/useEngineState';

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
    backgroundColor: '#eef0f7',
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

// ── FocusOnlyMount ──────────────────────────────────────
// Unmounts children when the tab is blurred. On desktop (web),
// @react-navigation keeps inactive screens mounted by default,
// which multiplies polling (~20 redundant GETs). Mobile is fine.
// This wrapper guarantees inactive tabs stop running effects.

function FocusOnlyMount({ children }: { children: React.ReactNode }) {
  const isFocused = useIsFocused();
  const hasBeenFocused = useRef(false);
  if (isFocused) hasBeenFocused.current = true;
  // Mount only after first focus; unmount when blurred again.
  if (!hasBeenFocused.current || !isFocused) {
    return <View style={{ flex: 1, backgroundColor: theme.colors.background }} />;
  }
  return <>{children}</>;
}

function withFocusOnlyMount<P extends object>(
  Component: React.ComponentType<P>
): React.FC<P> {
  const Wrapped: React.FC<P> = (props) => (
    <FocusOnlyMount>
      <Component {...props} />
    </FocusOnlyMount>
  );
  Wrapped.displayName = `FocusOnlyMount(${Component.displayName || Component.name || 'Component'})`;
  return Wrapped;
}

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
  const { state: engineState } = useEngineState(10_000);

  return (
    <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
      {/* Sub-tab bar at top */}
      <SafeAreaView style={subTabStyles.safeArea}>
        <View style={subTabStyles.bar}>
          {tabs.map((tab, index) => {
            const isActive = index === activeTab;
            return (
              <TouchableOpacity
                key={tab.key}
                style={[
                  subTabStyles.tab,
                  isActive && subTabStyles.tabActive,
                ]}
                onPress={() => setActiveTab(index)}
                activeOpacity={0.72}
                accessibilityRole="tab"
                accessibilityState={{ selected: isActive }}
              >
                <Text style={[subTabStyles.tabText, isActive && subTabStyles.tabTextActive]}>
                  {tab.label}
                </Text>
              </TouchableOpacity>
            );
          })}
          <View style={subTabStyles.engineSlot}>
            <EngineDot state={engineState} size={10} />
          </View>
        </View>
      </SafeAreaView>
      <ActiveComponent />
    </View>
  );
}

const subTabStyles = StyleSheet.create({
  safeArea: {
    backgroundColor: 'transparent',
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 6,
  },
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.48)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.78)',
    borderRadius: 24,
    padding: 4,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.08,
    shadowRadius: 24,
    elevation: 8,
    ...(Platform.OS === 'web'
      ? ({
          backdropFilter: 'blur(34px) saturate(190%)',
          WebkitBackdropFilter: 'blur(34px) saturate(190%)',
          boxShadow:
            '0 18px 50px rgba(20,22,30,0.10), inset 0 1px 0 rgba(255,255,255,0.92), inset 0 -1px 0 rgba(255,255,255,0.32)',
        } as any)
      : {}),
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 36,
    borderRadius: 20,
  },
  tabActive: {
    backgroundColor: 'rgba(255,255,255,0.72)',
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.14,
    shadowRadius: 14,
    elevation: 4,
    ...(Platform.OS === 'web'
      ? ({
          boxShadow:
            '0 10px 24px rgba(0,122,255,0.16), inset 0 1px 0 rgba(255,255,255,0.95), inset 0 -1px 0 rgba(0,0,0,0.04)',
        } as any)
      : {}),
  },
  tabText: {
    fontFamily: theme.fonts.medium,
    fontWeight: '600',
    fontSize: 13,
    letterSpacing: 0,
    color: '#7b7d86',
  },
  tabTextActive: {
    color: '#007AFF',
  },
  engineSlot: {
    width: 34,
    height: 34,
    marginLeft: 4,
    borderRadius: 17,
    backgroundColor: 'rgba(255,255,255,0.56)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.72)',
  },
});

// ── Combined Tab Screens ────────────────────────────────

function TradeScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'analysis', label: 'Scan', component: AnalysisScreen },
        { key: 'chart', label: 'Chart', component: ChartScreen },
        { key: 'queue', label: 'Queue', component: ManualModeScreen },
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

function LiquidIcon({ routeName, color }: { routeName: string; color: string }) {
  const common = {
    stroke: color,
    strokeWidth: 2.2,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    fill: 'none',
  };
  if (routeName === 'Dashboard') {
    return (
      <Svg width={24} height={24} viewBox="0 0 24 24">
        <Path d="M4 11.2 12 4l8 7.2" {...common} />
        <Path d="M6.6 10.4v8.3h4.1v-5h2.6v5h4.1v-8.3" {...common} />
      </Svg>
    );
  }
  if (routeName === 'Trade') {
    return (
      <Svg width={24} height={24} viewBox="0 0 24 24">
        <Line x1="6" y1="5" x2="6" y2="19" {...common} />
        <Rect x="4.1" y="8" width="3.8" height="6.2" rx="1.4" {...common} />
        <Line x1="13" y1="4" x2="13" y2="20" {...common} />
        <Rect x="11.1" y="6.2" width="3.8" height="9.8" rx="1.4" {...common} />
        <Polyline points="17.2 15.8 19.3 13.6 21 15.1" {...common} />
      </Svg>
    );
  }
  if (routeName === 'Market') {
    return (
      <Svg width={24} height={24} viewBox="0 0 24 24">
        <Rect x="4" y="4" width="6.2" height="6.2" rx="1.6" {...common} />
        <Rect x="13.8" y="4" width="6.2" height="6.2" rx="1.6" {...common} />
        <Rect x="4" y="13.8" width="6.2" height="6.2" rx="1.6" {...common} />
        <Rect x="13.8" y="13.8" width="6.2" height="6.2" rx="1.6" {...common} />
      </Svg>
    );
  }
  if (routeName === 'Log') {
    return (
      <Svg width={24} height={24} viewBox="0 0 24 24">
        <Path d="M7 4.5h7.2L18 8.3v11.2H7z" {...common} />
        <Path d="M14.2 4.7v3.8H18" {...common} />
        <Line x1="9.7" y1="12" x2="15.2" y2="12" {...common} />
        <Line x1="9.7" y1="15.5" x2="14.2" y2="15.5" {...common} />
      </Svg>
    );
  }
  return (
    <Svg width={24} height={24} viewBox="0 0 24 24">
      <Circle cx="12" cy="12" r="3.2" {...common} />
      <Path d="M12 3.8v2.1M12 18.1v2.1M5.2 5.2l1.5 1.5M17.3 17.3l1.5 1.5M3.8 12h2.1M18.1 12h2.1M5.2 18.8l1.5-1.5M17.3 6.7l1.5-1.5" {...common} />
    </Svg>
  );
}

function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  return (
    <View
      style={[
        tabIconStyles.icon,
        {
          opacity: focused ? 1 : 0.78,
        },
      ]}
    >
      <Text style={[tabIconStyles.legacyText, { color: focused ? '#007AFF' : '#7b7d86' }]}>
        {label.slice(0, 2)}
      </Text>
    </View>
  );
}

const tabIconStyles = StyleSheet.create({
  icon: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  legacyText: {
    fontFamily: theme.fonts.semibold,
    fontSize: 11,
    fontWeight: '700',
  },
});

function LiquidTabButton({ route, descriptor, navigation, isFocused }: any) {
  const progress = useRef(new Animated.Value(isFocused ? 1 : 0)).current;

  useEffect(() => {
    Animated.spring(progress, {
      toValue: isFocused ? 1 : 0,
      friction: 7,
      tension: 90,
      useNativeDriver: true,
    }).start();
  }, [isFocused, progress]);

  const { options } = descriptor;
  const label =
    options.tabBarLabel !== undefined
      ? options.tabBarLabel
      : options.title !== undefined
        ? options.title
        : route.name;

  const onPress = () => {
    const event = navigation.emit({
      type: 'tabPress',
      target: route.key,
      canPreventDefault: true,
    });

    if (!isFocused && !event.defaultPrevented) {
      navigation.navigate(route.name, route.params);
    }
  };

  return (
    <TouchableOpacity
      accessibilityRole="tab"
      accessibilityState={isFocused ? { selected: true } : {}}
      accessibilityLabel={options.tabBarAccessibilityLabel}
      testID={options.tabBarButtonTestID}
      onPress={onPress}
      activeOpacity={0.78}
      style={liquidTabStyles.item}
    >
      <Animated.View
        pointerEvents="none"
        style={[
          liquidTabStyles.selectedLens,
          {
            opacity: progress,
            transform: [
              {
                scale: progress.interpolate({
                  inputRange: [0, 1],
                  outputRange: [0.82, 1],
                }),
              },
            ],
          },
        ]}
      />
      <Animated.View
        style={[
          liquidTabStyles.iconWrap,
          {
            transform: [
              {
                translateY: progress.interpolate({
                  inputRange: [0, 1],
                  outputRange: [2, -2],
                }),
              },
            ],
          },
        ]}
      >
        <LiquidIcon routeName={route.name} color={isFocused ? '#007AFF' : '#6f737d'} />
      </Animated.View>
      <Text style={[liquidTabStyles.label, isFocused && liquidTabStyles.labelActive]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

function LiquidTabBar({ state, descriptors, navigation }: any) {
  return (
    <View style={liquidTabStyles.host} pointerEvents="box-none">
      <View style={liquidTabStyles.bar}>
        <View pointerEvents="none" style={liquidTabStyles.edgeGlow} />
        <View pointerEvents="none" style={liquidTabStyles.bottomLens} />
        {state.routes.map((route: any, index: number) => (
          <LiquidTabButton
            key={route.key}
            route={route}
            descriptor={descriptors[route.key]}
            navigation={navigation}
            isFocused={state.index === index}
          />
        ))}
      </View>
    </View>
  );
}

const liquidTabStyles = StyleSheet.create({
  host: {
    height: 98,
    backgroundColor: 'transparent',
    paddingHorizontal: 14,
    paddingBottom: 12,
    justifyContent: 'flex-end',
  },
  bar: {
    minHeight: 76,
    borderRadius: 40,
    padding: 7,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.48)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.82)',
    shadowColor: '#3a4150',
    shadowOffset: { width: 0, height: 18 },
    shadowOpacity: 0.18,
    shadowRadius: 34,
    elevation: 14,
    overflow: 'hidden',
    ...(Platform.OS === 'web'
      ? ({
          backdropFilter: 'blur(46px) saturate(210%)',
          WebkitBackdropFilter: 'blur(46px) saturate(210%)',
          boxShadow:
            '0 24px 70px rgba(36,40,52,0.18), inset 0 1px 0 rgba(255,255,255,0.96), inset 0 -1px 0 rgba(255,255,255,0.30)',
        } as any)
      : {}),
  },
  edgeGlow: {
    position: 'absolute',
    top: 1,
    left: 24,
    right: 24,
    height: 22,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.58)',
  },
  bottomLens: {
    position: 'absolute',
    left: 10,
    right: 10,
    bottom: 4,
    height: 12,
    borderRadius: 18,
    backgroundColor: 'rgba(255,255,255,0.22)',
  },
  item: {
    flex: 1,
    minHeight: 62,
    borderRadius: 32,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  selectedLens: {
    position: 'absolute',
    top: 2,
    left: 3,
    right: 3,
    bottom: 2,
    borderRadius: 32,
    backgroundColor: 'rgba(255,255,255,0.68)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.92)',
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.18,
    shadowRadius: 18,
    elevation: 6,
    ...(Platform.OS === 'web'
      ? ({
          boxShadow:
            '0 14px 32px rgba(0,122,255,0.16), inset 0 1px 0 rgba(255,255,255,1), inset 0 -1px 0 rgba(0,0,0,0.05)',
        } as any)
      : {}),
  },
  iconWrap: {
    height: 26,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 2,
  },
  label: {
    fontFamily: theme.fonts.medium,
    fontSize: 10,
    fontWeight: '600',
    letterSpacing: 0,
    color: '#777b85',
  },
  labelActive: {
    color: '#007AFF',
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
    backgroundColor: '#eef0f7',
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

// Wrap tab-level screens so they only render while focused.
// This prevents the 5 tab polling cycles from running in parallel on desktop.
const DashboardScreenFocused = withFocusOnlyMount(DashboardScreen);
const TradeScreenFocused = withFocusOnlyMount(TradeScreen);
const MarketScreenFocused = withFocusOnlyMount(MarketScreen);
const LogScreenFocused = withFocusOnlyMount(LogScreen);
const SettingsScreenFocused = withFocusOnlyMount(SettingsScreen);

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
    document.body.style.setProperty(
      'background',
      'linear-gradient(180deg, #fbfbff 0%, #eef0f7 52%, #f8f8fb 100%)',
    );
    document.body.style.setProperty('min-height', '100vh');
    return () => {
      document.body.style.removeProperty('background');
      document.body.style.removeProperty('min-height');
    };
  }, []);

  if (!fontsLoaded && !fontTimeout) {
    return <BootScreen />;
  }

  return (
    <ErrorBoundary>
      <SafeAreaView style={appStyles.shell}>
        <NavigationContainer>
          <StatusBar style="dark" />
          <Tab.Navigator
            detachInactiveScreens
            tabBar={(props) => <LiquidTabBar {...props} />}
            screenOptions={{
              headerShown: false,
              lazy: true,
              freezeOnBlur: true,
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
              component={DashboardScreenFocused}
              options={{
                tabBarLabel: 'Home',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="HQ" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Trade"
              component={TradeScreenFocused}
              options={{
                tabBarLabel: 'Trade',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="TRADE" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Market"
              component={MarketScreenFocused}
              options={{
                tabBarLabel: 'Market',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="MARKET" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Log"
              component={LogScreenFocused}
              options={{
                tabBarLabel: 'Log',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="LOG" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Settings"
              component={SettingsScreenFocused}
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

const appStyles = StyleSheet.create({
  shell: {
    flex: 1,
    backgroundColor: '#eef0f7',
    ...(Platform.OS === 'web'
      ? ({
          background:
            'linear-gradient(180deg, #fbfbff 0%, #eef0f7 52%, #f8f8fb 100%)',
        } as any)
      : {}),
  },
});
