// Refreshes are serialized so concurrent requests cannot rotate the same token.
export function createSession({ transport, storage }) {
  let access = null;
  let refresh = null;
  let rotating = null;

  async function remember(pair) {
    await storage.set(pair.refresh_token);
    access = pair.access_token;
    refresh = pair.refresh_token;
  }

  async function clear() {
    access = null;
    refresh = null;
    await storage.remove();
  }

  async function rotate() {
    if (!rotating) {
      rotating = (async () => {
        refresh ||= await storage.get();
        if (!refresh) throw Object.assign(new Error('Sign in to continue.'), { status: 401 });
        try {
          await remember(await transport('/auth/refresh', { body: { refresh_token: refresh } }));
        } catch (error) {
          if (error.status === 401) await clear();
          throw error;
        }
      })().finally(() => { rotating = null; });
    }
    return rotating;
  }

  return {
    async login(username, password) {
      await remember(await transport('/auth/login', { body: { username, password } }));
    },
    async request(path, options = {}) {
      if (!access) await rotate();
      const usedAccess = access;
      try {
        return await transport(path, { ...options, token: usedAccess });
      } catch (error) {
        if (error.status !== 401) throw error;
        if (access === usedAccess) await rotate();
        return transport(path, { ...options, token: access });
      }
    },
    async logout() {
      if (rotating) await rotating;
      refresh ||= await storage.get();
      // Keep credentials on a failed request so logout can be retried safely.
      if (refresh) await transport('/auth/logout', { body: { refresh_token: refresh } });
      await clear();
    },
  };
}
