// Credentials configuration: host URL + API key. Verifies the pair by
// calling /api/auth/check before persisting so users can't save bad
// values and see only opaque errors later.

import React, { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useCredentials } from '../lib/credentials';
import { createApi } from '../lib/api';

export default function Settings() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { credentials, setCredentials, clearCredentials } = useCredentials();
  const [hostUrl, setHostUrl] = useState(credentials?.hostUrl ?? '');
  const [apiKey, setApiKey] = useState(credentials?.apiKey ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setError(null);
    const host = hostUrl.trim();
    const key = apiKey.trim();
    if (!host || !key) {
      setError('Host URL and API key are required');
      return;
    }
    setBusy(true);
    try {
      // Verify before persisting so we fail fast on typos.
      const probe = createApi({
        fetch: globalThis.fetch.bind(globalThis),
        getCredentials: async () => ({ hostUrl: host, apiKey: key }),
      });
      const res = await probe.checkAuth();
      if (!res.valid) {
        setError('Server rejected the API key');
        return;
      }
      await setCredentials({ hostUrl: host, apiKey: key });
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to verify credentials');
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setError(null);
    await clearCredentials();
    setHostUrl('');
    setApiKey('');
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.root}
    >
      <Stack.Screen
        options={{
          headerShown: true,
          title: 'Settings',
          headerStyle: { backgroundColor: '#080f1e' },
          headerTintColor: '#e8f4ff',
        }}
      />
      <ScrollView
        contentContainerStyle={[styles.content, { paddingBottom: insets.bottom + 24 }]}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={styles.label}>Host URL</Text>
        <TextInput
          style={styles.input}
          value={hostUrl}
          onChangeText={setHostUrl}
          placeholder="https://laptop.tailXXXX.ts.net"
          placeholderTextColor="#5a7a8a"
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          testID="settings-host-input"
        />

        <Text style={styles.label}>API Key</Text>
        <TextInput
          style={styles.input}
          value={apiKey}
          onChangeText={setApiKey}
          placeholder="ARBITER_API_KEY"
          placeholderTextColor="#5a7a8a"
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          testID="settings-key-input"
        />

        {error && <Text style={styles.error}>{error}</Text>}

        <Pressable
          style={[styles.btn, styles.btnPrimary, busy && styles.btnDisabled]}
          onPress={save}
          disabled={busy}
          accessibilityRole="button"
          testID="settings-save"
        >
          {busy ? (
            <ActivityIndicator color="#e8f4ff" />
          ) : (
            <Text style={styles.btnText}>Verify &amp; Save</Text>
          )}
        </Pressable>

        <Pressable
          style={[styles.btn, styles.btnGhost]}
          onPress={clear}
          accessibilityRole="button"
          testID="settings-clear"
        >
          <Text style={[styles.btnText, styles.btnGhostText]}>Clear</Text>
        </Pressable>

        <Text style={styles.hint}>
          Connect over Tailscale or a similar private network. The host URL
          must be reachable from this device.
        </Text>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#000814' },
  content: { padding: 20, gap: 12 },
  label: { color: '#9fc4dc', fontSize: 13, marginTop: 8 },
  input: {
    color: '#e8f4ff',
    fontSize: 15,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: 'rgba(120, 200, 255, 0.25)',
  },
  error: { color: '#ffb0b0', fontSize: 13, marginTop: 4 },
  btn: {
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  btnPrimary: { backgroundColor: 'rgba(80, 160, 220, 0.55)' },
  btnGhost: { backgroundColor: 'transparent' },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: '#e8f4ff', fontWeight: '600', fontSize: 15 },
  btnGhostText: { color: '#9fc4dc' },
  hint: {
    color: '#5a7a8a',
    fontSize: 12,
    marginTop: 16,
    lineHeight: 18,
  },
});
