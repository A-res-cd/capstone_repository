import test from 'node:test';
import assert from 'node:assert/strict';
import { createSession } from '../src/session.js';

function fixture(transport, value = 'saved-refresh') {
  const storage = {
    get: async () => value,
    set: async (next) => { value = next; },
    remove: async () => { value = null; },
  };
  return { session: createSession({ transport, storage }), stored: () => value };
}

test('concurrent cold requests refresh once and use the rotated access token', async () => {
  let rotations = 0;
  const { session, stored } = fixture(async (path, options) => {
    if (path === '/auth/refresh') {
      rotations++;
      assert.equal(options.body.refresh_token, 'saved-refresh');
      await new Promise((resolve) => setTimeout(resolve, 10));
      return { access_token: 'new-access', refresh_token: 'new-refresh' };
    }
    assert.equal(options.token, 'new-access');
    return path;
  });
  assert.deepEqual(await Promise.all([session.request('/me'), session.request('/notifications')]), ['/me', '/notifications']);
  assert.equal(rotations, 1);
  assert.equal(stored(), 'new-refresh');
});

test('expired access is retried once; permission denial is not refreshed', async () => {
  let rotations = 0;
  const { session } = fixture(async (path, options) => {
    if (path === '/auth/refresh') return { access_token: `access-${++rotations}`, refresh_token: 'refresh' };
    if (path === '/denied') throw Object.assign(new Error('Forbidden'), { status: 403 });
    if (options.token === 'access-1') throw Object.assign(new Error('Expired'), { status: 401 });
    return 'ok';
  });
  assert.equal(await session.request('/me'), 'ok');
  assert.equal(rotations, 2);
  await assert.rejects(session.request('/denied'), { status: 403 });
  assert.equal(rotations, 2);
});

test('invalid refresh clears credentials; network failure preserves them', async () => {
  const invalid = fixture(async () => { throw Object.assign(new Error('Expired'), { status: 401 }); });
  await assert.rejects(invalid.session.request('/me'), { status: 401 });
  assert.equal(invalid.stored(), null);
  const offline = fixture(async () => { throw new Error('Offline'); });
  await assert.rejects(offline.session.request('/me'), /Offline/);
  assert.equal(offline.stored(), 'saved-refresh');
});

test('logout revokes before forgetting; failed logout can be retried', async () => {
  let offline = true;
  const { session, stored } = fixture(async (path, options) => {
    assert.equal(path, '/auth/logout');
    assert.equal(options.body.refresh_token, 'saved-refresh');
    if (offline) throw new Error('Offline');
  });
  await assert.rejects(session.logout(), /Offline/);
  assert.equal(stored(), 'saved-refresh');
  offline = false;
  await session.logout();
  assert.equal(stored(), null);
});
