import { Capacitor, CapacitorHttp } from '@capacitor/core';
import { SecureStorage, KeychainAccess } from '@aparajita/capacitor-secure-storage';
import { createSession } from './session.js';

const native = Capacitor.isNativePlatform();
const origin = (import.meta.env.VITE_API_ORIGIN || '').replace(/\/$/, '');
let volatileRefresh = null;

function apiOrigin() {
  if (!native && import.meta.env.DEV) return '';
  let url;
  try { url = new URL(origin); } catch { throw new Error('App server is not configured. Contact support.'); }
  if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('App server must use an HTTPS origin. Contact support.');
  }
  return url.origin;
}

async function transport(path, { body, token, binary = false } = {}) {
  const url = `${apiOrigin()}/api/v1${path}`;
  const headers = { Accept: binary ? 'application/pdf' : 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body) headers['Content-Type'] = 'application/json';
  let status, data;
  if (native) {
    const response = await CapacitorHttp.request({
      url, method: body ? 'POST' : 'GET', headers, data: body,
      responseType: binary ? 'arraybuffer' : 'json',
      connectTimeout: 15000, readTimeout: 30000, disableRedirects: true,
    });
    status = response.status;
    data = response.data;
    if (binary && status >= 200 && status < 300) {
      data = Uint8Array.from(atob(data), (char) => char.charCodeAt(0));
    }
  } else {
    const response = await fetch(url, {
      method: body ? 'POST' : 'GET', headers, body: body ? JSON.stringify(body) : undefined,
      credentials: 'omit', cache: 'no-store', redirect: 'error', signal: AbortSignal.timeout(30000),
    });
    status = response.status;
    data = status === 204 ? null : binary && response.ok
      ? new Uint8Array(await response.arrayBuffer()) : await response.json().catch(() => null);
  }
  if (status < 200 || status >= 300) {
    throw Object.assign(new Error(data?.error || `Request failed (${status}). Please try again.`), { status });
  }
  return data;
}

const key = `capre.refresh:${origin}`;
const storage = {
  async get() { return native ? SecureStorage.get(key, false, false) : volatileRefresh; },
  async set(value) {
    if (native) {
      await SecureStorage.setDefaultKeychainAccess(KeychainAccess.whenUnlockedThisDeviceOnly);
      await SecureStorage.set(key, value, false, false);
    } else volatileRefresh = value;
  },
  async remove() {
    if (native) await SecureStorage.remove(key, false);
    volatileRefresh = null;
  },
};

export const api = createSession({ transport, storage });
