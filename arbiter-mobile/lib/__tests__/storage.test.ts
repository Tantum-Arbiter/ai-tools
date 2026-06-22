import {
  KEYCHAIN_SERVICE,
  createCredentialStore,
  createMemoryStore,
  type SecureStoreLike,
} from '../storage';

describe('createCredentialStore', () => {
  it('returns null when nothing is stored', async () => {
    const store = createCredentialStore(createMemoryStore());
    await expect(store.load()).resolves.toBeNull();
  });

  it('returns null when only one half is stored', async () => {
    const mem = createMemoryStore({ 'arbiter.hostUrl': 'https://x' });
    const store = createCredentialStore(mem);
    await expect(store.load()).resolves.toBeNull();
  });

  it('round-trips host + key via save/load', async () => {
    const store = createCredentialStore(createMemoryStore());
    await store.save({ hostUrl: 'https://h.example', apiKey: 'sekret' });
    await expect(store.load()).resolves.toEqual({
      hostUrl: 'https://h.example',
      apiKey: 'sekret',
    });
  });

  it('rejects empty values on save', async () => {
    const store = createCredentialStore(createMemoryStore());
    await expect(
      store.save({ hostUrl: '', apiKey: 'x' }),
    ).rejects.toThrow('hostUrl and apiKey are required');
    await expect(
      store.save({ hostUrl: 'https://x', apiKey: '' }),
    ).rejects.toThrow('hostUrl and apiKey are required');
  });

  it('clear removes both items', async () => {
    const store = createCredentialStore(createMemoryStore());
    await store.save({ hostUrl: 'https://h', apiKey: 'k' });
    await store.clear();
    await expect(store.load()).resolves.toBeNull();
  });

  it('save overwrites previous values', async () => {
    const store = createCredentialStore(createMemoryStore());
    await store.save({ hostUrl: 'https://a', apiKey: 'k1' });
    await store.save({ hostUrl: 'https://b', apiKey: 'k2' });
    await expect(store.load()).resolves.toEqual({
      hostUrl: 'https://b',
      apiKey: 'k2',
    });
  });

  it('passes a stable keychainService to every secure-store call', async () => {
    // Spy on every call so we can assert the options are threaded
    // through to load / save / clear — without these, dev-client
    // rebuilds on the iOS Simulator can orphan keychain entries.
    const calls: Array<{ op: string; key: string; service: string | undefined }> = [];
    const spy: SecureStoreLike = {
      async getItemAsync(key, options) {
        calls.push({ op: 'get', key, service: options?.keychainService });
        return null;
      },
      async setItemAsync(key, _value, options) {
        calls.push({ op: 'set', key, service: options?.keychainService });
      },
      async deleteItemAsync(key, options) {
        calls.push({ op: 'del', key, service: options?.keychainService });
      },
    };
    const store = createCredentialStore(spy);
    await store.load();
    await store.save({ hostUrl: 'https://x', apiKey: 'k' });
    await store.clear();
    for (const c of calls) {
      expect(c.service).toBe(KEYCHAIN_SERVICE);
    }
    expect(calls.map((c) => c.op)).toEqual([
      'get',
      'get',
      'set',
      'set',
      'del',
      'del',
    ]);
  });

  it('honours a custom keychainService override', async () => {
    const calls: Array<string | undefined> = [];
    const spy: SecureStoreLike = {
      async getItemAsync(_k, o) { calls.push(o?.keychainService); return null; },
      async setItemAsync(_k, _v, o) { calls.push(o?.keychainService); },
      async deleteItemAsync(_k, o) { calls.push(o?.keychainService); },
    };
    const store = createCredentialStore(spy, { keychainService: 'custom' });
    await store.load();
    expect(calls.every((s) => s === 'custom')).toBe(true);
  });
});
