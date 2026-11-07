import { clearSession, loadSession, saveSession } from './auth';
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
    mountLogin(root, signIn);
    return;
  }
  if (s.role === 'student') {
    document.title = 'Watt Wise · Student view';
    mountStudent(root);
  } else {
    document.title = 'Watt Wise · Manager view';
    mountManager(root);
  }
}

function signIn(session: Session): void {
  state.session = session;
  if (session.role === 'student') state.flatId = session.flatId;
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

const saved = loadSession();
if (saved) {
  state.session = saved;
  if (saved.role === 'student') state.flatId = saved.flatId;
}
render();
