// Orchestration view. Top segmented control toggles between the CEO
// roster (/api/ceo/agents) and the runtime Agent Orchestrator
// (/api/agents). Each tab shows a roll-up Panel with agent counts plus
// a per-agent card list with a coloured status accent. Read-only first
// pass; dispatch / template editing remains desktop-only.

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useApi, useCredentials } from '../lib/credentials';
import {
  HudScreen,
  Panel,
  Stat,
  StatGrid,
  StatusDot,
  HUD_COLORS,
  HUD_FONTS,
  statusColor,
} from '../components/HUD';

type Tab = 'ceo' | 'agents';

interface AgentRow {
  id?: string;
  agent_id?: string;
  name?: string;
  role?: string;
  status?: string;
  emoji?: string;
}

export default function Orchestration() {
  const router = useRouter();
  const api = useApi();
  const { status: credStatus } = useCredentials();
  const [tab, setTab] = useState<Tab>('ceo');
  const [ceo, setCeo] = useState<AgentRow[]>([]);
  const [agents, setAgents] = useState<AgentRow[]>([]);
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
      const [c, a] = await Promise.all([
        api.getCeoAgents() as Promise<unknown>,
        api.getAgents() as Promise<unknown>,
      ]);
      setCeo(extractList(c));
      setAgents(extractList(a));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load orchestration');
    } finally {
      setLoading(false);
    }
  }, [api, credStatus]);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(() => (tab === 'ceo' ? ceo : agents), [tab, ceo, agents]);

  const headerExtra = (
    <View style={styles.segmented}>
      <SegBtn label="CEO" active={tab === 'ceo'} onPress={() => setTab('ceo')} />
      <SegBtn
        label="Orchestrator"
        active={tab === 'agents'}
        onPress={() => setTab('agents')}
      />
    </View>
  );

  const counts = useMemo(() => {
    let active = 0;
    let idle = 0;
    let off = 0;
    for (const r of rows) {
      const s = (r.status ?? '').toLowerCase();
      if (s.includes('active') || s.includes('running') || s.includes('online')) active += 1;
      else if (s.includes('idle') || s.includes('pending') || s.includes('queued')) idle += 1;
      else if (s.includes('off') || s.includes('error') || s.includes('failed')) off += 1;
    }
    return { active, idle, off, total: rows.length };
  }, [rows]);

  return (
    <HudScreen
      title="Orchestration"
      onBack={() => router.back()}
      onRefresh={load}
      headerExtra={headerExtra}
    >
      {credStatus === 'unconfigured' && (
        <Panel title="Not configured" accent={HUD_COLORS.amber}>
          <Text style={styles.hint}>
            Host URL + API key are not set. Configure them to load this view.
          </Text>
          <Pressable
            style={styles.settingsBtn}
            onPress={() => router.push('/settings')}
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
      {credStatus === 'ready' && !loading && !error && (
        <Panel title="Roster">
          <StatGrid>
            <Stat label="Total" value={String(counts.total)} tone="cyan" />
            <Stat label="Active" value={String(counts.active)} tone="nominal" />
            <Stat label="Idle" value={String(counts.idle)} tone="caution" />
            <Stat label="Offline" value={String(counts.off)} tone="alert" />
          </StatGrid>
        </Panel>
      )}
      {!loading && !error && rows.length === 0 && (
        <Panel title={tab === 'ceo' ? 'CEO roster' : 'Agents'}>
          <Text style={styles.empty}>No {tab === 'ceo' ? 'CEO roster' : 'agents'} returned.</Text>
        </Panel>
      )}
      {rows.map((r, i) => (
        <Panel
          key={`${tab}-${r.id ?? r.agent_id ?? i}`}
          accent={r.status ? statusColor(r.status) : HUD_COLORS.cyan}
        >
          <View style={styles.agentRow}>
            {r.emoji ? <Text style={styles.emoji}>{r.emoji}</Text> : <StatusDot status={r.status} />}
            <View style={{ flex: 1 }}>
              <Text style={styles.agentName}>{r.name ?? r.id ?? r.agent_id ?? '—'}</Text>
              {r.role && <Text style={styles.agentRole}>{r.role}</Text>}
            </View>
            {r.status && <Text style={styles.agentStatus}>{r.status.toUpperCase()}</Text>}
          </View>
        </Panel>
      ))}
    </HudScreen>
  );
}

function extractList(raw: unknown): AgentRow[] {
  if (Array.isArray(raw)) return raw as AgentRow[];
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    for (const key of ['agents', 'roster', 'items', 'data']) {
      const v = obj[key];
      if (Array.isArray(v)) return v as AgentRow[];
    }
  }
  return [];
}

const SegBtn: React.FC<{ label: string; active: boolean; onPress: () => void }> = ({
  label,
  active,
  onPress,
}) => (
  <Pressable
    onPress={onPress}
    style={[styles.segBtn, active && styles.segBtnActive]}
    accessibilityRole="button"
  >
    <Text style={[styles.segText, active && styles.segTextActive]}>{label}</Text>
  </Pressable>
);

const styles = StyleSheet.create({
  segmented: {
    flexDirection: 'row',
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 8,
  },
  segBtn: {
    flex: 1,
    paddingVertical: 9,
    alignItems: 'center',
    borderRadius: 4,
    borderWidth: 1,
    borderColor: 'rgba(32, 244, 255, 0.22)',
    backgroundColor: 'rgba(8, 24, 40, 0.6)',
  },
  segBtnActive: {
    borderColor: 'rgba(32, 244, 255, 0.65)',
    backgroundColor: 'rgba(32, 244, 255, 0.14)',
  },
  segText: {
    color: HUD_COLORS.textDim,
    fontSize: 11,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  segTextActive: { color: HUD_COLORS.cyan },
  agentRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  emoji: { fontSize: 20 },
  agentName: { color: HUD_COLORS.textBright, fontSize: 14 },
  agentRole: {
    color: HUD_COLORS.textDim,
    fontSize: 11,
    marginTop: 2,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 0.5,
  },
  agentStatus: {
    color: HUD_COLORS.cyan,
    fontSize: 10,
    fontFamily: HUD_FONTS.mono,
    letterSpacing: 1.2,
  },
  empty: { color: HUD_COLORS.textMuted, fontSize: 13, textAlign: 'center' },
  errorText: { color: '#ffb0b0', fontSize: 13 },
  hint: { color: HUD_COLORS.textMuted, fontSize: 13, lineHeight: 18 },
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
    fontSize: 11,
    letterSpacing: 0.8,
  },
});
