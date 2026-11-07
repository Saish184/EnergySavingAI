import { DEMO_MODE, loginManager, loginStudent, MIN_PASSWORD_LENGTH } from './auth';
import { $ } from './dom';
import { errorMessage } from './ui';
import type { Session } from './types';

type Role = 'student' | 'manager';

function setError(input: HTMLInputElement, box: HTMLElement, message: string): void {
  box.textContent = message;
  if (message) input.setAttribute('aria-invalid', 'true');
  else input.removeAttribute('aria-invalid');
}

/** `flatIds` loads the valid flats from the backend (GET /flats); students are checked against it. */
export function mountLogin(root: HTMLElement, onLogin: (session: Session) => void, flatIds: () => Promise<string[]>): void {
  let known: string[] | null = null;

  root.innerHTML = `
  <div class="login-wrap">
    <section class="login-card" aria-labelledby="l-title">
      <div class="eyebrow">Welcome</div>
      <h1 id="l-title">Sign in to Watt Wise</h1>

      <div class="seg" role="group" aria-label="I am a">
        <button type="button" class="tab" data-role="student" aria-pressed="true">I’m a student</button>
        <button type="button" class="tab" data-role="manager" aria-pressed="false">I’m a manager</button>
      </div>

      <form id="l-student" novalidate>
        <p class="lead">Type your flat number to see your flat. No password needed.</p>
        <div class="field">
          <label for="l-flat">Flat number</label>
          <input id="l-flat" name="flat" type="text" inputmode="text" autocomplete="off" autocapitalize="characters" placeholder="e.g. 3 or F003" aria-describedby="l-flat-hint l-flat-err">
          <div class="hint" id="l-flat-hint">Loading the list of flats…</div>
          <div class="error" id="l-flat-err" role="alert"></div>
        </div>
        <button class="btn" type="submit">Continue</button>
      </form>

      <form id="l-manager" hidden novalidate>
        <p class="lead">Managers sign in with their work email and password.</p>
        <div class="field">
          <label for="l-email">Email</label>
          <input id="l-email" name="email" type="email" autocomplete="username" placeholder="name@company.se" aria-describedby="l-email-err">
          <div class="error" id="l-email-err" role="alert"></div>
        </div>
        <div class="field">
          <label for="l-pass">Password</label>
          <div class="pw-row">
            <input id="l-pass" name="password" type="password" autocomplete="current-password" aria-describedby="l-pass-err">
            <button type="button" class="pw-toggle" id="l-pw-toggle" aria-pressed="false" aria-controls="l-pass">Show</button>
          </div>
          <div class="error" id="l-pass-err" role="alert"></div>
        </div>
        <button class="btn" type="submit" id="l-manager-btn">Sign in</button>
      </form>

      ${
        DEMO_MODE
          ? `<p class="demo-note"><strong>Demo sign-in, not security.</strong> There are no real accounts. Any well-formed email and a password of ${MIN_PASSWORD_LENGTH}+ characters opens the manager view, and a flat number is not a secret. The backend only checks an X-Flat-Id header, which is not authentication.</p>`
          : ''
      }
    </section>
  </div>`;

  const studentForm = $<HTMLFormElement>('#l-student');
  const managerForm = $<HTMLFormElement>('#l-manager');
  const flatInput = $<HTMLInputElement>('#l-flat');
  const flatErr = $('#l-flat-err');
  const emailInput = $<HTMLInputElement>('#l-email');
  const emailErr = $('#l-email-err');
  const passInput = $<HTMLInputElement>('#l-pass');
  const passErr = $('#l-pass-err');
  const managerBtn = $<HTMLButtonElement>('#l-manager-btn');

  function showRole(role: Role): void {
    studentForm.hidden = role !== 'student';
    managerForm.hidden = role !== 'manager';
    document.querySelectorAll<HTMLButtonElement>('.seg [data-role]').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.role === role));
    });
    (role === 'student' ? flatInput : emailInput).focus();
  }

  document.querySelectorAll<HTMLButtonElement>('.seg [data-role]').forEach((b) => {
    b.addEventListener('click', () => showRole(b.dataset.role === 'manager' ? 'manager' : 'student'));
  });

  const hint = $('#l-flat-hint');
  const studentBtn = $<HTMLButtonElement>('#l-student button[type=submit]');
  const loadFlats = async (): Promise<string[] | null> => {
    if (known) return known;
    try {
      known = await flatIds();
      hint.textContent = known.length ? `Flats run from ${known[0]} to ${known[known.length - 1]}.` : 'No flats are available.';
      return known;
    } catch (e) {
      hint.textContent = 'The list of flats could not be loaded.';
      setError(flatInput, flatErr, `${errorMessage(e)} Try again when the data service is running.`);
      return null;
    }
  };
  void loadFlats();

  studentForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    studentBtn.disabled = true;
    const list = await loadFlats();
    studentBtn.disabled = false;
    if (!list) return;
    const result = loginStudent(flatInput.value, list);
    if (!result.ok) {
      setError(flatInput, flatErr, result.message);
      flatInput.focus();
      return;
    }
    setError(flatInput, flatErr, '');
    onLogin(result.session);
  });
  flatInput.addEventListener('input', () => setError(flatInput, flatErr, ''));

  managerForm.addEventListener('submit', (e) => {
    e.preventDefault();
    setError(emailInput, emailErr, '');
    setError(passInput, passErr, '');
    managerBtn.disabled = true;
    managerBtn.textContent = 'Signing in…';
    loginManager(emailInput.value, passInput.value).then(
      (result) => {
        managerBtn.disabled = false;
        managerBtn.textContent = 'Sign in';
        if (result.ok) {
          onLogin(result.session);
          return;
        }
        if (result.field === 'email') {
          setError(emailInput, emailErr, result.message);
          emailInput.focus();
        } else {
          setError(passInput, passErr, result.message);
          passInput.focus();
        }
      },
      () => {
        managerBtn.disabled = false;
        managerBtn.textContent = 'Sign in';
        setError(passInput, passErr, 'Something went wrong. Please try again.');
      },
    );
  });
  emailInput.addEventListener('input', () => setError(emailInput, emailErr, ''));
  passInput.addEventListener('input', () => setError(passInput, passErr, ''));

  const toggle = $<HTMLButtonElement>('#l-pw-toggle');
  toggle.addEventListener('click', () => {
    const show = passInput.type === 'password';
    passInput.type = show ? 'text' : 'password';
    toggle.textContent = show ? 'Hide' : 'Show';
    toggle.setAttribute('aria-pressed', String(show));
  });

  flatInput.focus();
}
