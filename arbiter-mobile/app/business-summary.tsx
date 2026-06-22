// Business Summary view. Pulls /api/revenue/summary and renders the
// RevenueCat overview as HUD panels: a hero recurring-revenue block,
// the customer-base stat grid, and a risk-indicator strip whose tone
// reflects the refund rate. Trend chart deferred until the API exposes
// a time series.

import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useApi, useCredentials } from '../lib/credentials';
import { useSettingsOverlay } from '../lib/settingsOverlay';
import {
  HudScreen,
  Panel,
  Stat,
  StatGrid,
  HUD_COLORS,
  HUD_FONTS,
  type StatTone,
} from '../components/HUD';

interface Overview {
  active_subscribers?: number;
  active_trials?: number;
  mrr?: number;
  revenue?: number;
  new_customers?: number;
  churned_subscribers?: number;
  refund_rate?: number;
}

interface RevenueSummary {
  configured?: boolean;
  overview?: Overview;
}

const fmtCurrency = (n: number | undefined) =>
  typeof n === 'number' ? `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}` : '—';
const fmtNum = (n: number | undefined) =>
  typeof n === 'number' ? n.toLocaleString('en-US') : '—';
const fmtPct = (n: number | undefined) =>
  typeof n === 'number' ? `${(n * 100).toFixed(1)}%` : '—';

function refundTone(rate: number | undefined): StatTone {
  if (typeof rate !== 'number') return 'cyan';
  if (rate > 0.05) return 'alert';
  if (rate > 0.02) return 'caution';
  return 'nominal';
}

export default function BusinessSummary() {
  const router = useRouter();
  const api = useApi();
  const settings = useSettingsOverlay();
  const { status: credStatus } = useCredentials();
  const [data, setData] = useState<RevenueSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (credStatus !== 'ready') {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = (await api.getRevenueSummary()) as RevenueSummary;
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load summary');
    } finally {
      setLoading(false);
    }
  }, [api, credStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const overview = data?.overview ?? {};

  return (
    <HudScreen title="Business Summary" onBack={() => router.back()} onRefresh={load}>
      <Panel title="Arbiter" accent={HUD_COLORS.cyan}>
        <Text style={styles.askText}>
          Sir, would you like a briefing on the current state of your portfolio?
        </Text>
      </Panel>

      {credStatus === 'unconfigured' && (
        <Panel title="Not configured" accent={HUD_COLORS.amber}>
          <Text style={styles.hint}>
            Host URL + API key are not set. Configure them to load this view.
          </Text>
          <Pressable
            style={styles.settingsBtn}
            onPress={settings.open}
            accessibilityRole="button"
          >
            <Text style={styles.settingsBtnText}>Open Settings</Text>
          </Pressable>
        </Panel>
      )}

      {loading && <ActivityIndicator color={HUD_COLORS.cyan} style={{ marginTop: 8 }} />}

      {error && (
        <Panel title="Error">
          <Text style={styles.errorText}>{error}</Text>
        </Panel>
      )}

      {data && data.configured === false && (
        <Panel title="Not configured">
          <Text style={styles.hint}>
            RevenueCat is not configured on the server. Set REVENUECAT_API_KEY and
            REVENUECAT_PROJECT_ID in the server `.env` to enable this panel.
          </Text>
        </Panel>
      )}

      {data && data.configured !== false && (
        <>
          <Panel title="Recurring revenue" accent={HUD_COLORS.cyan}>
            <View style={styles.heroRow}>
              <View style={styles.heroBlock}>
                <Text style={styles.heroValue}>{fmtCurrency(overview.mrr)}</Text>
                <Text style={styles.heroLabel}>Monthly recurring</Text>
              </View>
              <View style={styles.heroDivider} />
              <View style={styles.heroBlock}>
                <Text style={styles.heroValueSecondary}>{fmtCurrency(overview.revenue)}</Text>
                <Text style={styles.heroLabel}>Period revenue</Text>
              </View>
            </View>
          </Panel>

          <Panel title="Customer base">
            <StatGrid>
              <Stat label="Subscribers" value={fmtNum(overview.active_subscribers)} tone="cyan" />
              <Stat label="Trials" value={fmtNum(overview.active_trials)} tone="accent" />
              <Stat label="New" value={fmtNum(overview.new_customers)} tone="nominal" />
              <Stat label="Churned" value={fmtNum(overview.churned_subscribers)} tone="caution" />
            </StatGrid>
          </Panel>

          <Panel title="Risk indicators">
            <StatGrid>
              <Stat
                label="Refund rate"
                value={fmtPct(overview.refund_rate)}
                tone={refundTone(overview.refund_rate)}
              />
            </StatGrid>
          </Panel>
        </>
      )}
    </HudScreen>
  );
}

const styles = StyleSheet.create({
  askText: { color: HUD_COLORS.textBright, fontSize: 15, lineHeight: 22 },
  errorText: { color: '#ffb0b0', fontSize: 14 },
  hint: { color: HUD_COLORS.textMuted, fontSize: 14, lineHeight: 20 },
  heroRow: { flexDirection: 'row', alignItems: 'stretch', gap: 14, paddingVertical: 4 },
  heroBlock: { flex: 1, gap: 4 },
  heroDivider: { width: StyleSheet.hairlineWidth, backgroundColor: HUD_COLORS.divider },
  heroValue: {
    color: HUD_COLORS.cyan,
    fontFamily: HUD_FONTS.mono,
    fontSize: 33,
    fontWeight: '300',
    letterSpacing: 0.5,
  },
  heroValueSecondary: {
    color: HUD_COLORS.cyanSoft,
    fontFamily: HUD_FONTS.mono,
    fontSize: 24,
    fontWeight: '300',
    letterSpacing: 0.5,
  },
  heroLabel: {
    color: HUD_COLORS.textDim,
    fontSize: 11,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 1.2,
    textTransform: 'uppercase',
  },
  settingsBtn: {
    marginTop: 12,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(32, 244, 255, 0.45)',
    backgroundColor: 'rgba(32, 244, 255, 0.10)',
    alignSelf: 'flex-start',
  },
  settingsBtnText: {
    color: HUD_COLORS.cyan,
    fontFamily: HUD_FONTS.mono,
    fontSize: 12,
    letterSpacing: 0.8,
  },
});
