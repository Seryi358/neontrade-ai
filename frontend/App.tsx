/**
 * NeonTrade AI - Main App
 * Cyberpunk 2077 HUD-style AI Trading System
 *
 * Navigation: 5 tabs (HQ, TRADE, MARKET, LOG, SYS)
 * TRADE/MARKET/LOG tabs use internal sub-navigation (state-based)
 */

import React, { useEffect, useRef } from 'react';
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
} from 'react-native';
import { useFonts } from 'expo-font';
import { theme } from './src/theme/cyberpunk';

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
          {/* Scan lines overlay */}
          <View style={errorStyles.scanLines} />

          <Text style={errorStyles.icon}>!</Text>
          <Text style={errorStyles.title}>SYSTEM MALFUNCTION</Text>
          <View style={errorStyles.divider} />

          <ScrollView style={errorStyles.scrollArea}>
            <Text style={errorStyles.errorDetail}>{this.state.error}</Text>
          </ScrollView>

          <Text style={errorStyles.code}>ERR::FATAL_EXCEPTION</Text>

          <Text
            style={errorStyles.rebootBtn}
            onPress={() => this.setState({ hasError: false, error: '' })}
          >
            REBOOT SYSTEM
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
    backgroundColor: '#050505',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  scanLines: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    opacity: 0.04,
    // Simulated scan lines via repeating borders
    borderTopWidth: 1,
    borderTopColor: 'rgba(218, 68, 83, 0.2)',
  },
  icon: {
    fontSize: 52,
    color: '#ff4a57',
    fontFamily: 'Rajdhani-Bold',
    textShadowColor: 'rgba(218, 68, 83, 0.6)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 30,
    marginBottom: 8,
  },
  title: {
    color: '#ff4a57',
    fontFamily: 'Rajdhani-Bold',
    fontSize: 24,
    letterSpacing: 8,
    textTransform: 'uppercase',
    textShadowColor: 'rgba(218, 68, 83, 0.5)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 20,
  },
  divider: {
    width: '50%',
    height: 1,
    backgroundColor: '#ff4a57',
    marginVertical: 16,
    shadowColor: '#ff4a57',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 8,
  },
  scrollArea: {
    maxHeight: 160,
    marginBottom: 12,
  },
  errorDetail: {
    color: '#ff4a57',
    fontFamily: 'TerminessNerdFont',
    fontSize: 11,
    textAlign: 'center',
    letterSpacing: 1,
    opacity: 0.8,
  },
  code: {
    color: '#6b7080',
    fontFamily: 'TerminessNerdFont',
    fontSize: 9,
    letterSpacing: 3,
    marginBottom: 24,
  },
  rebootBtn: {
    color: '#0abdc6',
    fontFamily: 'Rajdhani-Bold',
    fontSize: 14,
    letterSpacing: 4,
    textTransform: 'uppercase',
    borderWidth: 1,
    borderColor: '#0abdc6',
    paddingHorizontal: 28,
    paddingVertical: 10,
    borderRadius: 2,
    textShadowColor: 'rgba(93, 244, 254, 0.4)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 8,
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
    <View style={{ flex: 1, backgroundColor: '#0a0e14' }}>
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
    backgroundColor: '#050505',
  },
  bar: {
    flexDirection: 'row',
    backgroundColor: '#050505',
    borderBottomWidth: 1,
    borderBottomColor: '#2a2445',
    paddingHorizontal: 8,
    paddingTop: 8,
  },
  tab: {
    flex: 1,
    textAlign: 'center',
    fontFamily: 'Rajdhani-Bold',
    fontSize: 11,
    letterSpacing: 3,
    color: '#6b7080',
    paddingVertical: 10,
    textTransform: 'uppercase',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabActive: {
    color: '#f3e600',
    borderBottomColor: '#f3e600',
    textShadowColor: 'rgba(252, 238, 9, 0.4)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 6,
  },
});

// ── Combined Tab Screens ────────────────────────────────

function TradeScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'analysis', label: 'SCAN', component: AnalysisScreen },
        { key: 'chart', label: 'CHART', component: ChartScreen },
        { key: 'manual', label: 'MANUAL', component: ManualModeScreen },
      ]}
    />
  );
}

function MarketScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'watchlist', label: 'WATCHLIST', component: WatchlistScreen },
        { key: 'crypto', label: 'CRYPTO', component: CryptoScreen },
      ]}
    />
  );
}

function LogScreen() {
  return (
    <SubTabScreen
      tabs={[
        { key: 'history', label: 'HISTORY', component: HistoryScreen },
        { key: 'journal', label: 'JOURNAL', component: JournalScreen },
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
          color: focused ? theme.colors.cp2077Yellow : '#8a9bad',
          textShadowColor: focused ? theme.colors.cp2077YellowGlow : 'transparent',
          textShadowOffset: { width: 0, height: 0 },
          textShadowRadius: focused ? 10 : 0,
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
    fontFamily: 'Rajdhani-Bold',
    marginTop: 2,
  },
});

// ── Boot / Loading Screen ───────────────────────────────

function BootScreen() {
  const lineWidth = useRef(new Animated.Value(0)).current;
  const textOpacity = useRef(new Animated.Value(0)).current;
  const subtitleOpacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    // Boot sequence animation
    Animated.sequence([
      Animated.timing(lineWidth, {
        toValue: 1,
        duration: 1200,
        useNativeDriver: false,
      }),
      Animated.timing(textOpacity, {
        toValue: 1,
        duration: 400,
        useNativeDriver: true,
      }),
      Animated.timing(subtitleOpacity, {
        toValue: 1,
        duration: 300,
        useNativeDriver: true,
      }),
    ]).start();
  }, [lineWidth, textOpacity, subtitleOpacity]);

  return (
    <View style={bootStyles.container}>
      {/* Animated yellow boot line */}
      <Animated.View
        style={[
          bootStyles.bootLine,
          {
            width: lineWidth.interpolate({
              inputRange: [0, 1],
              outputRange: ['0%', '60%'],
            }),
          },
        ]}
      />

      {/* Title */}
      <Animated.Text style={[bootStyles.title, { opacity: textOpacity }]}>
        NEONTRADE AI
      </Animated.Text>

      {/* Version info */}
      <Animated.Text style={[bootStyles.versionText, { opacity: textOpacity }]}>
        v1.0 // SYSTEM INITIALIZING...
      </Animated.Text>

      {/* Powered by */}
      <Animated.Text style={[bootStyles.poweredBy, { opacity: subtitleOpacity }]}>
        POWERED BY TRADINGLAB
      </Animated.Text>
    </View>
  );
}

const bootStyles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#050505',
    alignItems: 'center',
    justifyContent: 'center',
  },
  bootLine: {
    height: 2,
    backgroundColor: '#f3e600',
    marginBottom: 24,
    shadowColor: '#f3e600',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.8,
    shadowRadius: 12,
    elevation: 8,
  },
  title: {
    fontFamily: 'Rajdhani-Bold',
    fontSize: 36,
    color: '#f3e600',
    letterSpacing: 12,
    textTransform: 'uppercase',
    textShadowColor: 'rgba(252, 238, 9, 0.4)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 25,
  },
  versionText: {
    fontFamily: 'TerminessNerdFont',
    fontSize: 11,
    color: '#6b7080',
    letterSpacing: 3,
    marginTop: 12,
    textTransform: 'uppercase',
  },
  poweredBy: {
    fontFamily: 'TerminessNerdFont',
    fontSize: 9,
    color: '#6b7080',
    letterSpacing: 4,
    marginTop: 8,
    textTransform: 'uppercase',
    opacity: 0.5,
  },
});

// ── Main Tab Navigator ──────────────────────────────────

const Tab = createBottomTabNavigator();

export default function App() {
  const [fontsLoaded] = useFonts({
    'Rajdhani': require('./src/assets/fonts/Rajdhani-Regular.ttf'),
    'Rajdhani-Light': require('./src/assets/fonts/Rajdhani-Light.ttf'),
    'Rajdhani-Medium': require('./src/assets/fonts/Rajdhani-Medium.ttf'),
    'Rajdhani-SemiBold': require('./src/assets/fonts/Rajdhani-SemiBold.ttf'),
    'Rajdhani-Bold': require('./src/assets/fonts/Rajdhani-Bold.ttf'),
    'TerminessNerdFont': require('./src/assets/fonts/TerminessNerdFont-Regular.ttf'),
    'TerminessNerdFont-Bold': require('./src/assets/fonts/TerminessNerdFont-Bold.ttf'),
    'TerminessNerdFont-Italic': require('./src/assets/fonts/TerminessNerdFont-Italic.ttf'),
    'TerminessNerdFont-BoldItalic': require('./src/assets/fonts/TerminessNerdFont-BoldItalic.ttf'),
    'Terminess Nerd Font': require('./src/assets/fonts/TerminessNerdFont-Regular.ttf'),
  });

  if (!fontsLoaded) {
    return <BootScreen />;
  }

  return (
    <ErrorBoundary>
      <SafeAreaView style={{ flex: 1, backgroundColor: '#050505' }}>
        <NavigationContainer>
          <StatusBar style="light" />
          <Tab.Navigator
            screenOptions={{
              headerShown: false,
              tabBarStyle: {
                backgroundColor: '#050505',
                borderTopWidth: 1,
                borderTopColor: '#f3e600',
                height: 60,
                paddingBottom: 6,
                paddingTop: 6,
                elevation: 16,
                shadowColor: '#f3e600',
                shadowOffset: { width: 0, height: -2 },
                shadowOpacity: 0.15,
                shadowRadius: 10,
              },
              tabBarActiveTintColor: '#f3e600',
              tabBarInactiveTintColor: '#8a9bad',
              tabBarLabelStyle: {
                fontFamily: 'Rajdhani-Bold',
                fontSize: 9,
                letterSpacing: 2,
                textTransform: 'uppercase',
              },
            }}
          >
            <Tab.Screen
              name="Dashboard"
              component={DashboardScreen}
              options={{
                tabBarLabel: 'HQ',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="HQ" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Trade"
              component={TradeScreen}
              options={{
                tabBarLabel: 'TRADE',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="TRADE" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Market"
              component={MarketScreen}
              options={{
                tabBarLabel: 'MARKET',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="MARKET" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Log"
              component={LogScreen}
              options={{
                tabBarLabel: 'LOG',
                tabBarIcon: ({ focused }) => (
                  <TabIcon label="LOG" focused={focused} />
                ),
              }}
            />
            <Tab.Screen
              name="Settings"
              component={SettingsScreen}
              options={{
                tabBarLabel: 'SYS',
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
