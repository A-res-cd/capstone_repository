import { Capacitor } from '@capacitor/core';
import { App } from '@capacitor/app';
import { api } from './api.js';
import './style.css';

const root = document.querySelector('#app');
const nav = document.querySelector('#navigation');
const message = document.querySelector('#message');
let renderId = 0;
let disposeReader = () => {};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function report(error) {
  message.textContent = error.message || 'Connection failed. Please try again.';
  message.hidden = false;
}

function button(text, action) {
  const node = element('button', text);
  node.type = 'button';
  node.addEventListener('click', async () => {
    node.disabled = true;
    message.hidden = true;
    try { await action(); } catch (error) { report(error); }
    finally { node.disabled = false; }
  });
  return node;
}

function login() {
  nav.hidden = true;
  root.replaceChildren(element('h1', 'Your research starts here.'), element('p', 'Sign in with your CAPRE account.'));
  const form = element('form');
  for (const [name, label, type] of [['username', 'Username', 'text'], ['password', 'Password', 'password']]) {
    const wrapper = element('label', label);
    const input = element('input');
    Object.assign(input, { name, type, required: true, autocomplete: name === 'password' ? 'current-password' : 'username' });
    input.autocapitalize = 'none';
    wrapper.append(input);
    form.append(wrapper);
  }
  const submit = element('button', 'Sign in');
  submit.type = 'submit';
  form.append(submit);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    message.hidden = true;
    try {
      const values = new FormData(form);
      await api.login(values.get('username'), values.get('password'));
      form.reset();
      if (location.hash === '#repository') await render();
      else location.hash = 'repository';
    } catch (error) { report(error); }
    finally { submit.disabled = false; }
  });
  root.append(form);
}

async function repository(id, params) {
  const search = params.get('search') || '';
  const page = Math.max(1, Number(params.get('page')) || 1);
  const query = new URLSearchParams({ search, page: String(page) });
  const data = await api.request(`/capstones?${query}`);
  if (id !== renderId) return;
  root.replaceChildren(element('h1', 'Explore the repository'));
  const form = element('form', undefined, 'search');
  const input = element('input');
  Object.assign(input, { type: 'search', value: search, placeholder: 'Title, author, or keyword', maxLength: 200 });
  input.setAttribute('aria-label', 'Search repository');
  const submit = element('button', 'Search');
  form.append(input, submit);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    location.hash = `repository?${new URLSearchParams({ search: input.value })}`;
  });
  root.append(form, element('p', `${data.total} research projects`, 'muted'));
  if (!data.items.length) root.append(element('p', 'No projects found. Try another search.'));
  for (const item of data.items) {
    const card = element('article');
    const link = element('a', item.capstone_title);
    link.href = `#capstone/${item.capstone_id}`;
    const heading = element('h2');
    heading.append(link);
    card.append(element('p', `${item.capstone_year} · ${item.program_name || ''}`, 'muted'), heading,
      element('p', item.capstone_keywords || ''));
    root.append(card);
  }
  const pager = element('div', undefined, 'actions');
  function jump(target) {
    location.hash = `repository?${new URLSearchParams({ search, page: String(target) })}`;
  }
  if (page > 1) pager.append(button('Previous', () => jump(page - 1)));
  pager.append(element('span', `Page ${page} of ${Math.max(1, Math.ceil(data.total / data.page_size))}`));
  if (page * data.page_size < data.total) pager.append(button('Next', () => jump(page + 1)));
  root.append(pager);
}

async function detail(id, capstoneId) {
  const data = await api.request(`/capstones/${capstoneId}`);
  if (id !== renderId) return;
  root.replaceChildren(element('h1', data.item.capstone_title),
    element('p', `${data.item.capstone_year} · ${data.item.program_name || ''}`, 'muted'),
    element('p', data.item.capstone_keywords || ''),
    button('Back to repository', () => { location.hash = 'repository'; }));
  if (data.can_view) root.append(button('Read manuscript', () => { location.hash = `read/${capstoneId}`; }));
  else root.append(element('p', 'Full manuscript access requires approval. Request access through the CAPRE website.'));
}

async function read(id, capstoneId) {
  const [bytes, pdfjs] = await Promise.all([
    api.request(`/capstones/${capstoneId}/file`, { binary: true }),
    import('pdfjs-dist/legacy/build/pdf.mjs'),
  ]);
  if (id !== renderId) return;
  pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/legacy/build/pdf.worker.min.mjs', import.meta.url).href;
  const loading = pdfjs.getDocument({
    data: bytes, isEvalSupported: false,
    cMapUrl: '/pdfjs/cmaps/', cMapPacked: true,
    standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/', iccUrl: '/pdfjs/iccs/',
  });
  disposeReader = () => { void loading.destroy(); };
  const pdf = await loading.promise;
  if (id !== renderId) { await loading.destroy(); return; }
  let page = 1;
  const canvas = element('canvas');
  canvas.setAttribute('aria-label', 'Manuscript page');
  const label = element('span');
  let rendering = false;
  const draw = async () => {
    if (rendering || id !== renderId) return;
    rendering = true;
    previous.disabled = next.disabled = true;
    try {
      const sheet = await pdf.getPage(page);
      const base = sheet.getViewport({ scale: 1 });
      const viewport = sheet.getViewport({ scale: Math.min((root.clientWidth - 16) / base.width, 2) * Math.min(devicePixelRatio, 2) });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await sheet.render({ canvasContext: canvas.getContext('2d'), viewport }).promise;
      label.textContent = `Page ${page} of ${pdf.numPages}`;
    } finally {
      rendering = false;
      previous.disabled = page <= 1;
      next.disabled = page >= pdf.numPages;
    }
  };
  // Reader buttons manage their own disabled states during page rendering.
  const previous = element('button', 'Previous');
  const next = element('button', 'Next');
  previous.onclick = () => { page--; void draw().catch(report); };
  next.onclick = () => { page++; void draw().catch(report); };
  const controls = element('div', undefined, 'actions');
  controls.append(previous, label, next);
  root.replaceChildren(button('Close manuscript', () => { location.hash = `capstone/${capstoneId}`; }), controls, canvas);
  await draw();
}

async function notifications(id) {
  const data = await api.request('/notifications');
  if (id !== renderId) return;
  root.replaceChildren(element('h1', 'Notifications'), element('p', `${data.unread_count} unread`));
  root.append(button('Refresh', render), button('Mark all read', async () => {
    await api.request('/notifications/read', { body: {} });
    await render();
  }));
  if (!data.items.length) root.append(element('p', 'You are all caught up.'));
  for (const item of data.items) {
    const card = element('article');
    card.append(element('h2', item.notification_title || item.capstone_title || 'Account update'),
      element('p', item.notification_message || item.status_reason || item.request_status),
      element('p', item.decision_date ? new Date(item.decision_date).toLocaleString() : '', 'muted'));
    root.append(card);
  }
}

async function profile(id) {
  const { user } = await api.request('/me');
  if (id !== renderId) return;
  root.replaceChildren(element('h1', 'Your profile'),
    element('h2', [user.user_first_name, user.user_middle_name, user.user_last_name].filter(Boolean).join(' ')),
    element('p', user.role_name), button('Sign out', async () => {
      await api.logout();
      ++renderId;
      login();
    }));
}

async function render() {
  const id = ++renderId;
  disposeReader();
  disposeReader = () => {};
  message.hidden = true;
  root.replaceChildren(element('p', 'Loading…', 'muted'));
  const [path, query] = location.hash.slice(1).split('?');
  const [screen = 'repository', capstoneId] = (path || 'repository').split('/');
  try {
    if (screen === 'profile') await profile(id);
    else if (screen === 'notifications') await notifications(id);
    else if (['capstone', 'read'].includes(screen) && /^\d+$/.test(capstoneId || '')) {
      await (screen === 'read' ? read : detail)(id, capstoneId);
    } else await repository(id, new URLSearchParams(query));
    if (id === renderId) {
      nav.hidden = false;
      nav.querySelectorAll('a').forEach((link) => {
        const active = link.hash === `#${screen}` || (link.hash === '#repository' && ['read', 'capstone'].includes(screen));
        if (active) link.setAttribute('aria-current', 'page');
        else link.removeAttribute('aria-current');
      });
      root.focus();
    }
  } catch (error) {
    if (id !== renderId) return;
    if (error.status === 401) login();
    else root.replaceChildren(element('h1', 'Unable to load'), button('Try again', render));
    report(error);
  }
}

function connection() { document.querySelector('#connection').hidden = navigator.onLine; }
window.addEventListener('online', connection);
window.addEventListener('offline', connection);
window.addEventListener('hashchange', render);
  if (Capacitor.isNativePlatform()) {
  App.addListener('backButton', () => {
    if (location.hash && location.hash !== '#repository') location.hash = 'repository';
    else App.minimizeApp();
  }).catch(report);
}
connection();
void render();
