/**
 * NeonTrade AI - Main App
 * Cyberpunk AI-Powered Forex Trading System
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Text, View, StyleSheet, ActivityIndicator, ScrollView } from 'react-native';
import { useFonts } from 'expo-font';
import { theme } from './src/theme/cyberpunk';

// Error Boundary to prevent black screen on crash
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
        <View style={{ flex: 1, backgroundColor: '#0a0812', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
          <Text style={{ color: '#da4453', fontFamily: 'Rajdhani-Bold', fontSize: 48, marginBottom: 8 }}>⚠</Text>
          <Text style={{ color: '#fcee09', fontFamily: 'Rajdhani-Bold', fontSize: 22, letterSpacing: 8, marginBottom: 4, textTransform: 'uppercase' }}>SYSTEM MALFUNCTION</Text>
          <View style={{ width: '50%', height: 1, backgroundColor: '#da4453', marginBottom: 16 }} />
          <ScrollView style={{ maxHeight: 180 }}>
            <Text style={{ color: '#da4453', fontFamily: 'TerminessNerdFont', fontSize: 11, textAlign: 'center', letterSpacing: 1 }}>{this.state.error}</Text>
          </ScrollView>
          <Text
            style={{ color: '#5df4fe', fontFamily: 'Rajdhani-Bold', fontSize: 14, marginTop: 28, letterSpacing: 4, textTransform: 'uppercase', borderWidth: 1, borderColor: '#5df4fe', paddingHorizontal: 24, paddingVertical: 8, borderRadius: 2 }}
            onPress={() => this.setState({ hasError: false, error: '' })}
          >REBOOT SYSTEM</Text>
        </View>
      );
    }
    return this.props.children;
  }
}

// Screens
import DashboardScreen from './src/screens/DashboardScreen';
import ChartScreen from './src/screens/ChartScreen';
import AnalysisScreen from './src/screens/AnalysisScreen';
import ManualModeScreen from './src/screens/ManualModeScreen';
import WatchlistScreen from './src/screens/WatchlistScreen';
import HistoryScreen from './src/screens/HistoryScreen';
import JournalScreen from './src/screens/JournalScreen';
import CryptoScreen from './src/screens/CryptoScreen';
import SettingsScreen from './src/screens/SettingsScreen';

const Tab = createBottomTabNavigator();

// Tab icons using text characters (cyberpunk style)
function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  return (
    <Text style={[
      styles.tabIcon,
      { color: focused ? theme.colors.cp2077Yellow : theme.colors.textMuted }
    ]}>
      {label}
    </Text>
  );
}

export default function App() {
  const [fontsLoaded] = useFonts({
    // Rajdhani — primary UI font (CP2077 geometric style)
    'Rajdhani': require('./src/assets/fonts/Rajdhani-Regular.ttf'),
    'Rajdhani-Light': require('./src/assets/fonts/Rajdhani-Light.ttf'),
    'Rajdhani-Medium': require('./src/assets/fonts/Rajdhani-Medium.ttf'),
    'Rajdhani-SemiBold': require('./src/assets/fonts/Rajdhani-SemiBold.ttf'),
    'Rajdhani-Bold': require('./src/assets/fonts/Rajdhani-Bold.ttf'),
    // Terminess — monospace for financial data/code
    'TerminessNerdFont': require('./src/assets/fonts/TerminessNerdFont-Regular.ttf'),
    'TerminessNerdFont-Bold': require('./src/assets/fonts/TerminessNerdFont-Bold.ttf'),
    'TerminessNerdFont-Italic': require('./src/assets/fonts/TerminessNerdFont-Italic.ttf'),
    'TerminessNerdFont-BoldItalic': require('./src/assets/fonts/TerminessNerdFont-BoldItalic.ttf'),
    'Terminess Nerd Font': require('./src/assets/fonts/TerminessNerdFont-Regular.ttf'),
  });

  if (!fontsLoaded) {
    return (
      <View style={styles.loadingContainer}>
        <Text style={styles.bootLogo}>⬡</Text>
        <ActivityIndicator size="large" color={theme.colors.cp2077Yellow} />
        <Text style={styles.loadingText}>INITIALIZING NEONTRADE AI...</Text>
        <Text style={styles.bootSubtext}>TRADINGLAB SYSTEM v2.2</Text>
      </View>
    );
  }

  return (
    <ErrorBoundary>
    <NavigationContainer>
      <StatusBar style="light" />
      <Tab.Navigator
        screenOptions={{
          headerShown: false,
          tabBarStyle: {
            backgroundColor: theme.colors.backgroundDark,
            borderTopColor: theme.colors.cp2077YellowDim,
            borderTopWidth: 1,
            height: 64,
            paddingBottom: 8,
            paddingTop: 6,
            elevation: 16,
            shadowColor: theme.colors.cp2077Yellow,
            shadowOffset: { width: 0, height: -3 },
            shadowOpacity: 0.2,
            shadowRadius: 12,
          },
          tabBarActiveTintColor: theme.colors.cp2077Yellow,
          tabBarInactiveTintColor: theme.colors.textMuted,
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
              <TabIcon label="⬡" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Analysis"
          component={AnalysisScreen}
          options={{
            tabBarLabel: 'SCAN',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◎" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Chart"
          component={ChartScreen}
          options={{
            tabBarLabel: 'CHART',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="▥" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Watchlist"
          component={WatchlistScreen}
          options={{
            tabBarLabel: 'WATCH',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◉" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Manual"
          component={ManualModeScreen}
          options={{
            tabBarLabel: 'OPS',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="⬢" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Crypto"
          component={CryptoScreen}
          options={{
            tabBarLabel: 'CRYPTO',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="₿" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="History"
          component={HistoryScreen}
          options={{
            tabBarLabel: 'LOG',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="▤" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Journal"
          component={JournalScreen}
          options={{
            tabBarLabel: 'DIARIO',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◆" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Settings"
          component={SettingsScreen}
          options={{
            tabBarLabel: 'SYS',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="⚙" focused={focused} />
            ),
          }}
        />
      </Tab.Navigator>
    </NavigationContainer>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  tabIcon: {
    fontSize: 20,
    marginTop: 2,
    fontFamily: 'Rajdhani-Bold',
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: theme.colors.backgroundDark,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bootLogo: {
    fontSize: 48,
    color: theme.colors.cp2077Yellow,
    marginBottom: 20,
    textShadowColor: theme.colors.cp2077YellowGlow,
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 25,
  },
  loadingText: {
    color: theme.colors.cp2077Yellow,
    fontFamily: 'Rajdhani-Bold',
    fontSize: 14,
    letterSpacing: 6,
    marginTop: 20,
    textTransform: 'uppercase',
  },
  bootSubtext: {
    color: theme.colors.neonCyan,
    fontFamily: 'TerminessNerdFont',
    fontSize: 10,
    letterSpacing: 4,
    marginTop: 8,
    textTransform: 'uppercase',
    opacity: 0.6,
  },
});
