// Credential storage abstraction over expo-secure-store.
// The real implementation injects `expo-secure-store`; tests inject an
// in-memory map. The API key never touches AsyncStorage or logs.

import type { Credentials } from './api';

const KEY_HOST = 'arbiter.hostUrl';
const KEY_API = 'arbiter.apiKey';

export interface SecureStoreLike {
  getItemAsync(key: string): Promise<string | null>;
  setItemAsync(key: string, value: string): Promise<void>;
  deleteItemAsync(key: string): Promise<void>;
}

export interface CredentialStore {
  load(): Promise<Credentials | null>;
  save(creds: Credentials): Promise<void>;
  clear(): Promise<void>;
}

export function createCredentialStore(store: SecureStoreLike): CredentialStore {
  return {
    async load() {
      const [host, key] = await Promise.all([
        store.getItemAsync(KEY_HOST),
        store.getItemAsync(KEY_API),
      ]);
      if (!host || !key) return null;
      return { hostUrl: host, apiKey: key };
    },

    async save(creds) {
      if (!creds.hostUrl || !creds.apiKey) {
        throw new Error('hostUrl and apiKey are required');
      }
      await Promise.all([
        store.setItemAsync(KEY_HOST, creds.hostUrl),
        store.setItemAsync(KEY_API, creds.apiKey),
      ]);
    },

    async clear() {
      await Promise.all([
        store.deleteItemAsync(KEY_HOST),
        store.deleteItemAsync(KEY_API),
      ]);
    },
  };
}

// In-memory SecureStoreLike for tests.
export function createMemoryStore(initial: Record<string, string> = {}): SecureStoreLike {
  const map = new Map(Object.entries(initial));
  return {
    async getItemAsync(k) {
      return map.has(k) ? (map.get(k) as string) : null;
    },
    async setItemAsync(k, v) {
      map.set(k, v);
    },
    async deleteItemAsync(k) {
      map.delete(k);
    },
  };
}
