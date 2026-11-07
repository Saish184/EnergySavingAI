import { createApi } from './api';
import type { MockApi } from './api/mock';
import { clearSession, loadSession, saveSession } from './auth';
import { resolveConfig } from './config';
import { $, esc } from './dom';
import { mountLogin } from './login';
import { mountManager } from './manager';
import { state } from './state';
import { mountStudent } from './student';
import type { Session } from './types';

function renderUserArea(): void {
  const area = $('#user-area');
  const s = state.session;
  if (!s) {
    area.innerHTML = '';
    return;
  }
  const who = s.role === 'student' ? `Student · ${s.flatId}` : `Manager · ${s.email}`;
  area.innerHTML = `<span class="who" title="${esc(who)}">${esc(who)}</span><button class="tab" id="signout" type="button">Sign out</button>`;
  $('#signout').addEventListener('click', signOut);
}

function render(): void {
  const root = $('#app');
  const s = state.session;
  renderUserArea();
  if (!s) {
    document.title = 'Watt Wise · Sign in';
    mountLogin(root, signIn, async () => (await state.api!.flats()).map((f) => f.flat_id));
    return;
  }
  if (s.role === 'student') {
    document.title = 'Watt Wise · Student view';
    mountStudent(root, s.flatId);
  } else {
    document.title = 'Watt Wise · Manager view';
    mountManager(root);
  }
}

function signIn(session: Session): void {
  state.session = session;
  saveSession(session);
  render();
  $('#app').focus();
  window.scrollTo(0, 0);
}

function signOut(): void {
  clearSession();
  state.session = null;
  render();
  window.scrollTo(0, 0);
}

state.config = resolveConfig(window.WATTWISE_CONFIG, window.location.search);
state.api = createApi(state.config, () => (state.session?.role === 'student' ? state.session.flatId : null));
const src = document.getElementById('data-source');
if (src) {
  src.textContent = `Data: ${state.api.describe}`;
  if (state.api.mode === 'mock') {
    void (state.api as MockApi).meta().then(
      (m) => (src.textContent = `Data: offline fixtures recorded from the real engine (references ${m.references_hash})`),
      () => (src.textContent = 'Data: offline fixtures could not be loaded'),
    );
  }
}
state.session = loadSession();
render();
