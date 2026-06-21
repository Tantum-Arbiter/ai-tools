// React-side credential bootstrap: loads from SecureStore on mount,
// exposes save/clear + a singleton ArbiterApi instance whose
// getCredentials closure always returns the latest in-memory copy.

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import * as SecureStore from 'expo-secure-store';
import { createApi, type ArbiterApi, type Credentials } from './api';
import { createCredentialStore } from './storage';

export type CredentialStatus = 'loading' | 'ready' | 'unconfigured';

interface CredentialsContextValue {
  status: CredentialStatus;
  credentials: Credentials | null;
  setCredentials: (c: Credentials) => Promise<void>;
  clearCredentials: () => Promise<void>;
  api: ArbiterApi;
}

const Ctx = createContext<CredentialsContextValue | null>(null);

export const CredentialsProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const store = useMemo(() => createCredentialStore(SecureStore), []);
  const credsRef = useRef<Credentials | null>(null);
  const [credentials, setCredentialsState] = useState<Credentials | null>(null);
  const [status, setStatus] = useState<CredentialStatus>('loading');

  // Stable API instance — its getCredentials closure reads from the ref
  // so updates take effect immediately without rebuilding the client.
  const api = useMemo<ArbiterApi>(
    () => createApi({
      fetch: globalThis.fetch.bind(globalThis),
      getCredentials: async () => credsRef.current,
    }),
    [],
  );

  // Initial load from SecureStore.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await store.load();
        if (cancelled) return;
        credsRef.current = loaded;
        setCredentialsState(loaded);
        setStatus(loaded ? 'ready' : 'unconfigured');
      } catch {
        if (cancelled) return;
        setStatus('unconfigured');
      }
    })();
    return () => { cancelled = true; };
  }, [store]);

  const setCredentials = useCallback(
    async (c: Credentials) => {
      await store.save(c);
      credsRef.current = c;
      setCredentialsState(c);
      setStatus('ready');
    },
    [store],
  );

  const clearCredentials = useCallback(async () => {
    await store.clear();
    credsRef.current = null;
    setCredentialsState(null);
    setStatus('unconfigured');
  }, [store]);

  const value = useMemo<CredentialsContextValue>(
    () => ({ status, credentials, setCredentials, clearCredentials, api }),
    [status, credentials, setCredentials, clearCredentials, api],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export function useCredentials(): CredentialsContextValue {
  const v = useContext(Ctx);
  if (!v) throw new Error('useCredentials must be used inside CredentialsProvider');
  return v;
}

export function useApi(): ArbiterApi {
  return useCredentials().api;
}
