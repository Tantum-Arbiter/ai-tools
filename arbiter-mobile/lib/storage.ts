// Credential storage abstraction over expo-secure-store.
// The real implementation injects `expo-secure-store`; tests inject an
// in-memory map. The API key never touches AsyncStorage or logs.
//
// We pin an explicit `keychainService` so the entries are stable across
// rebuilds of the dev client (without this, the default service name
// can leave entries orphaned when the binary's code signature changes
// between `npx expo run:ios` rebuilds on the simulator). We also use
// AFTER_FIRST_UNLOCK so the values are reachable as soon as the user
// has unlocked the device once after boot.

import type { Credentials } from './api';

const KEY_HOST = 'arbiter.hostUrl';
const KEY_API = 'arbiter.apiKey';

// Stable service name → Keychain entries survive dev-client rebuilds.
export const KEYCHAIN_SERVICE = 'com.arbiter.mobile.credentials';

export interface SecureStoreOptions {
  keychainService?: string;
  keychainAccessible?: number;
}

export interface SecureStoreLike {
  getItemAsync(key: string, options?: SecureStoreOptions): Promise<string | null>;
  setItemAsync(key: string, value: string, options?: SecureStoreOptions): Promise<void>;
  deleteItemAsync(key: string, options?: SecureStoreOptions): Promise<void>;
}

export interface CredentialStore {
  load(): Promise<Credentials | null>;
  save(creds: Credentials): Promise<void>;
  clear(): Promise<void>;
}

export interface CreateCredentialStoreOptions {
  /** Override the keychainService (mainly for tests). */
  keychainService?: string;
  /**
   * iOS Keychain accessibility constant. Numeric so the storage layer
   * doesn't depend on expo-secure-store's enum at the type level.
   * Pass `SecureStore.AFTER_FIRST_UNLOCK` in production.
   */
  keychainAccessible?: number;
}

export function createCredentialStore(
  store: SecureStoreLike,
  options: CreateCredentialStoreOptions = {},
): CredentialStore {
  const opts: SecureStoreOptions = {
    keychainService: options.keychainService ?? KEYCHAIN_SERVICE,
    ...(options.keychainAccessible !== undefined
      ? { keychainAccessible: options.keychainAccessible }
      : {}),
  };
  return {
    async load() {
      const [host, key] = await Promise.all([
        store.getItemAsync(KEY_HOST, opts),
        store.getItemAsync(KEY_API, opts),
      ]);
      if (!host || !key) return null;
      return { hostUrl: host, apiKey: key };
    },

    async save(creds) {
      if (!creds.hostUrl || !creds.apiKey) {
        throw new Error('hostUrl and apiKey are required');
      }
      await Promise.all([
        store.setItemAsync(KEY_HOST, creds.hostUrl, opts),
        store.setItemAsync(KEY_API, creds.apiKey, opts),
      ]);
    },

    async clear() {
      await Promise.all([
        store.deleteItemAsync(KEY_HOST, opts),
        store.deleteItemAsync(KEY_API, opts),
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
