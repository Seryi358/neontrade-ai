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
        <View style={{ flex: 1, backgroundColor: '#0f0a1a', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
          <Text style={{ color: '#eb4eca', fontFamily: 'monospace', fontSize: 20, letterSpacing: 4, marginBottom: 16 }}>SYSTEM ERROR</Text>
          <ScrollView style={{ maxHeight: 200 }}>
            <Text style={{ color: '#ff073a', fontFamily: 'monospace', fontSize: 11, textAlign: 'center' }}>{this.state.error}</Text>
          </ScrollView>
          <Text
            style={{ color: '#00f0ff', fontFamily: 'monospace', fontSize: 12, marginTop: 24, letterSpacing: 2 }}
            onPress={() => this.setState({ hasError: false, error: '' })}
          >[ REINICIAR ]</Text>
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
import SettingsScreen from './src/screens/SettingsScreen';

const Tab = createBottomTabNavigator();

// Tab icons using text characters (cyberpunk style)
function TabIcon({ label, focused }: { label: string; focused: boolean }) {
  return (
    <Text style={[
      styles.tabIcon,
      { color: focused ? theme.colors.neonPink : theme.colors.textMuted }
    ]}>
      {label}
    </Text>
  );
}

export default function App() {
  const [fontsLoaded] = useFonts({
    'TerminessNerdFont': require('./src/assets/fonts/TerminessNerdFont-Regular.ttf'),
    'TerminessNerdFont-Bold': require('./src/assets/fonts/TerminessNerdFont-Bold.ttf'),
    'TerminessNerdFont-Italic': require('./src/assets/fonts/TerminessNerdFont-Italic.ttf'),
    'TerminessNerdFont-BoldItalic': require('./src/assets/fonts/TerminessNerdFont-BoldItalic.ttf'),
    'Terminess Nerd Font': require('./src/assets/fonts/TerminessNerdFont-Regular.ttf'),
  });

  if (!fontsLoaded) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color={theme.colors.neonPink} />
        <Text style={styles.loadingText}>CARGANDO FUENTES...</Text>
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
            borderTopColor: theme.colors.border,
            borderTopWidth: 1,
            height: 65,
            paddingBottom: 8,
            paddingTop: 4,
          },
          tabBarActiveTintColor: theme.colors.neonPink,
          tabBarInactiveTintColor: theme.colors.textMuted,
          tabBarLabelStyle: {
            fontFamily: 'TerminessNerdFont',
            fontSize: 8,
            letterSpacing: 1.5,
          },
        }}
      >
        <Tab.Screen
          name="Dashboard"
          component={DashboardScreen}
          options={{
            tabBarLabel: 'DASH',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◈" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Chart"
          component={ChartScreen}
          options={{
            tabBarLabel: 'CHART',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◫" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Analysis"
          component={AnalysisScreen}
          options={{
            tabBarLabel: 'ANÁLISIS',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◎" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Manual"
          component={ManualModeScreen}
          options={{
            tabBarLabel: 'MANUAL',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="◇" focused={focused} />
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
          name="History"
          component={HistoryScreen}
          options={{
            tabBarLabel: 'HIST',
            tabBarIcon: ({ focused }) => (
              <TabIcon label="▤" focused={focused} />
            ),
          }}
        />
        <Tab.Screen
          name="Settings"
          component={SettingsScreen}
          options={{
            tabBarLabel: 'CONFIG',
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
    fontSize: 18,
    marginTop: 2,
    fontFamily: 'TerminessNerdFont',
  },
  loadingContainer: {
    flex: 1,
    backgroundColor: theme.colors.background,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadingText: {
    color: theme.colors.neonPink,
    fontFamily: 'monospace',
    fontSize: 12,
    letterSpacing: 3,
    marginTop: 16,
  },
});
