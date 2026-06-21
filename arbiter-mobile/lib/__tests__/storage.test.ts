import { createCredentialStore, createMemoryStore } from '../storage';

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
});
