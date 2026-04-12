/**
 * Atlas - Exam Screen
 * TradingLab Final Exam: select 5 trades, generate analysis report.
 * Design: Apple Liquid Glass Light
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Linking,
  Platform,
} from 'react-native';
import { theme } from '../theme/apple-glass';
import {
  HUDCard,
  HUDHeader,
  HUDBadge,
  LoadingState,
  ErrorState,
} from '../components/HUDComponents';
import { API_URL, authFetch } from '../services/api';

const safe = (v: any, d = 2): string => (v == null || isNaN(v)) ? '---' : Number(v).toFixed(d);

interface Trade {
  id: string;
  instrument: string;
  direction: string;
  strategy: string;
  strategy_variant?: string;
  entry_price: number;
  exit_price: number;
  pnl: number;
  status: string;
  opened_at: string;
  closed_at: string;
}

export default function ExamScreen() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportHtml, setReportHtml] = useState<string | null>(null);

  const fetchTrades = useCallback(async () => {
    try {
      setError(null);
      const res = await authFetch(`${API_URL}/api/v1/exam/trades`);
      if (!res.ok) throw new Error('Failed to fetch trades');
      setTrades(await res.json());
    } catch (err) {
      setError('Could not load trades');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTrades(); }, []);

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else if (next.size < 5) {
        next.add(id);
      }
      return next;
    });
  };

  const generateReport = async () => {
    if (selected.size !== 5) {
      Alert.alert('Select 5 Trades', 'You need exactly 5 trades for the exam.');
      return;
    }
    setGenerating(true);
    try {
      const res = await authFetch(`${API_URL}/api/v1/exam/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trade_ids: Array.from(selected) }),
      });
      if (!res.ok) throw new Error('Failed to generate report');
      const data = await res.json();
      setReportHtml(data.html);
    } catch (err) {
      Alert.alert('Error', 'Could not generate exam report');
    } finally {
      setGenerating(false);
    }
  };

  const openReport = () => {
    if (reportHtml && Platform.OS === 'web') {
      const blob = new Blob([reportHtml], { type: 'text/html' });
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    }
  };

  if (loading) return <LoadingState message="Loading trades..." />;
  if (error) return <ErrorState message={error} onRetry={fetchTrades} />;

  if (reportHtml) {
    return (
      <View style={styles.container}>
        <HUDHeader title="Exam Report" subtitle="TradingLab Final Exam" />
        <View style={styles.reportActions}>
          <TouchableOpacity style={styles.primaryBtn} onPress={openReport}>
            <Text style={styles.primaryBtnText}>Open Report</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={() => setReportHtml(null)}>
            <Text style={styles.secondaryBtnText}>Back</Text>
          </TouchableOpacity>
        </View>
        <HUDCard title="Preview">
          <Text style={styles.previewText}>Report generated with 5 trades. Open it in the browser to view the full analysis with charts.</Text>
        </HUDCard>
      </View>
    );
  }

  const renderTrade = ({ item }: { item: Trade }) => {
    const isSelected = selected.has(item.id);
    const pnl = item.pnl || 0;
    const pnlColor = pnl >= 0 ? theme.colors.profit : theme.colors.loss;
    const dirColor = item.direction === 'BUY' ? theme.colors.profit : theme.colors.loss;
    const status = (item.status || '').replace('closed_', '').toUpperCase();

    return (
      <TouchableOpacity
        onPress={() => toggleSelect(item.id)}
        activeOpacity={0.7}
      >
        <HUDCard
          style={isSelected ? styles.cardSelected : undefined}
          borderColor={isSelected ? theme.colors.cp2077Yellow : undefined}
        >
          <View style={styles.tradeRow}>
            <View style={styles.checkCircle}>
              {isSelected && <View style={styles.checkFill} />}
            </View>
            <View style={{ flex: 1 }}>
              <View style={styles.tradeHeader}>
                <Text style={styles.tradeInstrument}>{item.instrument}</Text>
                <Text style={[styles.tradePnl, { color: pnlColor }]}>
                  {pnl >= 0 ? '+' : ''}${safe(pnl)}
                </Text>
              </View>
              <View style={styles.tradeDetails}>
                <Text style={[styles.tradeDirection, { color: dirColor }]}>{item.direction}</Text>
                <Text style={styles.tradeMeta}>{item.strategy} {item.strategy_variant || ''}</Text>
                <HUDBadge label={status} color={pnlColor} size="sm" />
              </View>
              <Text style={styles.tradeDate}>{item.closed_at || item.opened_at}</Text>
            </View>
          </View>
        </HUDCard>
      </TouchableOpacity>
    );
  };

  return (
    <View style={styles.container}>
      <HUDHeader
        title="Exam"
        subtitle={`TradingLab Final · ${selected.size}/5 selected`}
      />

      <View style={styles.infoCard}>
        <Text style={styles.infoText}>
          Select exactly 5 trades to include in your TradingLab exam submission.
          Each trade will include a chart screenshot, strategy analysis, and risk assessment.
        </Text>
      </View>

      <FlatList
        data={trades}
        keyExtractor={item => item.id}
        renderItem={renderTrade}
        contentContainerStyle={styles.listContent}
        showsVerticalScrollIndicator={false}
      />

      {selected.size > 0 && (
        <View style={styles.bottomBar}>
          <TouchableOpacity
            style={[styles.generateBtn, selected.size === 5 && styles.generateBtnActive]}
            onPress={generateReport}
            disabled={generating || selected.size !== 5}
          >
            {generating ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.generateBtnText}>
                Generate Report ({selected.size}/5)
              </Text>
            )}
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f2f2f7',
  },
  listContent: {
    padding: 16,
  },
  infoCard: {
    backgroundColor: 'rgba(0,122,255,0.06)',
    marginHorizontal: 16,
    marginBottom: 8,
    borderRadius: 14,
    padding: 14,
  },
  infoText: {
    fontSize: 14,
    color: '#007AFF',
    lineHeight: 20,
  },
  cardSelected: {
    borderColor: '#007AFF',
    borderWidth: 2,
  },
  tradeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  checkCircle: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    borderColor: '#C7C7CC',
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkFill: {
    width: 14,
    height: 14,
    borderRadius: 7,
    backgroundColor: '#007AFF',
  },
  tradeHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  tradeInstrument: {
    fontSize: 17,
    fontWeight: '600',
    color: '#1d1d1f',
    letterSpacing: -0.2,
  },
  tradePnl: {
    fontSize: 17,
    fontWeight: '700',
  },
  tradeDetails: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 4,
  },
  tradeDirection: {
    fontSize: 13,
    fontWeight: '600',
  },
  tradeMeta: {
    fontSize: 13,
    color: '#86868b',
  },
  tradeDate: {
    fontSize: 12,
    color: '#aeaeb2',
    marginTop: 4,
  },
  bottomBar: {
    borderTopWidth: 1,
    borderTopColor: 'rgba(0,0,0,0.04)',
    backgroundColor: '#ffffff',
    padding: 16,
  },
  generateBtn: {
    backgroundColor: '#C7C7CC',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  generateBtnActive: {
    backgroundColor: '#007AFF',
    shadowColor: '#007AFF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 6,
  },
  generateBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
  },
  reportActions: {
    flexDirection: 'row',
    gap: 10,
    padding: 16,
  },
  primaryBtn: {
    flex: 1,
    backgroundColor: '#007AFF',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  primaryBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ffffff',
  },
  secondaryBtn: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.04)',
    borderRadius: 14,
    paddingVertical: 14,
    alignItems: 'center',
  },
  secondaryBtnText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#007AFF',
  },
  previewText: {
    fontSize: 15,
    color: '#86868b',
    lineHeight: 22,
  },
});
