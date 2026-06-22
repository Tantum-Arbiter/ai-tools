// Uptime view. Combines /api/status (LLM + service health) with
// /api/gcp/summary (GCP region status + AWS status). Each tier renders
// in its own HUD Panel with a colour accent that reflects the worst
// status in the group, plus a roll-up stat strip so the operator gets
// a single-glance read of overall health.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { useApi, useCredentials } from '../lib/credentials';
import { useSettingsOverlay } from '../lib/settingsOverlay';
import {
  HudScreen,
  Panel,
  Stat,
  StatGrid,
  StatusRow,
  HUD_COLORS,
  statusColor,
} from '../components/HUD';

interface RegionEntry {
  region?: string;
  name?: string;
  status?: string;
  note?: string;
}

interface SystemStatus {
  llm_online?: boolean;
  llm_provider?: string;
  services?: Array<{ name: string; status?: string; note?: string }>;
  [k: string]: unknown;
}

interface GcpSummary {
  configured?: boolean;
  project_id?: string;
  region_status?: RegionEntry[];
  aws_status?: RegionEntry[];
  pods?: { running?: number; pending?: number; failed?: number };
}

function worstStatus(items: Array<{ status?: string }>): string {
  const order = ['red', 'error', 'alert', 'offline', 'amber', 'warning', 'caution', 'grey', 'unknown'];
  let worstIdx = Infinity;
  for (const it of items) {
    const s = (it.status ?? 'grey').toLowerCase();
    const idx = order.indexOf(s);
    if (idx !== -1 && idx < worstIdx) worstIdx = idx;
  }
  if (worstIdx === Infinity) return 'green';
  const v = order[worstIdx];
  return v ?? 'green';
}

export default function Uptime() {
  const router = useRouter();
  const api = useApi();
  const settings = useSettingsOverlay();
  const { status: credStatus } = useCredentials();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [gcp, setGcp] = useState<GcpSummary | null>(null);
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
      const [s, g] = await Promise.all([
        api.getSystemStatus() as Promise<SystemStatus>,
        api.getGcpSummary() as Promise<GcpSummary>,
      ]);
      setStatus(s);
      setGcp(g);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load uptime');
    } finally {
      setLoading(false);
    }
  }, [api, credStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const services = status?.services ?? [];
  const regions = gcp?.region_status ?? [];
  const aws = gcp?.aws_status ?? [];

  const counts = useMemo(() => {
    const all = [...services, ...regions, ...aws];
    let green = 0;
    let amber = 0;
    let red = 0;
    for (const it of all) {
      const s = (it.status ?? 'grey').toLowerCase();
      if (s === 'green' || s === 'ok' || s === 'online' || s === 'nominal') green += 1;
      else if (s === 'amber' || s === 'warning' || s === 'caution') amber += 1;
      else if (s === 'red' || s === 'error' || s === 'alert' || s === 'offline') red += 1;
    }
    return { green, amber, red };
  }, [services, regions, aws]);

  return (
    <HudScreen title="Uptime" onBack={() => router.back()} onRefresh={load}>
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
      {loading && <ActivityIndicator color={HUD_COLORS.cyan} />}
      {error && (
        <Panel title="Error">
          <Text style={styles.errorText}>{error}</Text>
        </Panel>
      )}

      {!loading && (
        <Panel title="Roll-up" accent={counts.red > 0 ? HUD_COLORS.red : counts.amber > 0 ? HUD_COLORS.amber : HUD_COLORS.green}>
          <StatGrid>
            <Stat label="Nominal" value={String(counts.green)} tone="nominal" />
            <Stat label="Caution" value={String(counts.amber)} tone="caution" />
            <Stat label="Alert" value={String(counts.red)} tone="alert" />
          </StatGrid>
        </Panel>
      )}

      {status && (
        <Panel
          title="LLM"
          accent={status.llm_online ? HUD_COLORS.green : HUD_COLORS.red}
        >
          <StatusRow
            status={status.llm_online ? 'green' : 'red'}
            label={status.llm_provider ?? 'unknown'}
            note={status.llm_online ? 'online' : 'offline'}
          />
        </Panel>
      )}

      {services.length > 0 && (
        <Panel title="Services" accent={statusColor(worstStatus(services))}>
          {services.map((s, i) => (
            <StatusRow
              key={`${s.name}-${i}`}
              status={s.status}
              label={s.name}
              {...(s.note ? { note: s.note } : {})}
            />
          ))}
        </Panel>
      )}

      {regions.length > 0 && (
        <Panel title="GCP regions" accent={statusColor(worstStatus(regions))}>
          {regions.map((r, i) => (
            <StatusRow
              key={`gcp-${i}`}
              status={r.status}
              label={r.region ?? r.name ?? '—'}
              {...(r.note ? { note: r.note } : {})}
            />
          ))}
        </Panel>
      )}

      {aws.length > 0 && (
        <Panel title="AWS regions" accent={statusColor(worstStatus(aws))}>
          {aws.map((r, i) => (
            <StatusRow
              key={`aws-${i}`}
              status={r.status}
              label={r.region ?? r.name ?? '—'}
              {...(r.note ? { note: r.note } : {})}
            />
          ))}
        </Panel>
      )}

      {gcp?.pods && (
        <Panel title="Pods">
          <StatGrid>
            <Stat label="Running" value={String(gcp.pods.running ?? 0)} tone="nominal" />
            <Stat label="Pending" value={String(gcp.pods.pending ?? 0)} tone="caution" />
            <Stat label="Failed" value={String(gcp.pods.failed ?? 0)} tone="alert" />
          </StatGrid>
        </Panel>
      )}
    </HudScreen>
  );
}

const styles = StyleSheet.create({
  errorText: { color: '#ffb0b0', fontSize: 14 },
  hint: { color: HUD_COLORS.textMuted, fontSize: 14, lineHeight: 20 },
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
    fontSize: 12,
    letterSpacing: 0.8,
  },
});
