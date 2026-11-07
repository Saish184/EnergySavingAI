"use strict";
(() => {
  // src/api/client.ts
  var ApiError = class extends Error {
    constructor(kind, message, status, detail) {
      super(message);
      this.kind = kind;
      this.status = status;
      this.detail = detail;
      this.name = "ApiError";
    }
  };
  var LiveApi = class {
    constructor(opts) {
      this.opts = opts;
      this.mode = "live";
      this.base = opts.baseUrl.replace(/\/+$/, "");
      this.describe = `live backend at ${this.base}`;
      this.fetchImpl = opts.fetchImpl ?? ((i, init) => fetch(i, init));
    }
    async call(method, path, body, studentFlat) {
      const headers = { Accept: "application/json" };
      if (body !== void 0) headers["Content-Type"] = "application/json";
      const flat = studentFlat ?? null;
      if (flat) headers["X-Flat-Id"] = flat;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), this.opts.timeoutMs);
      let res;
      try {
        res = await this.fetchImpl(this.base + path, {
          method,
          headers,
          body: body === void 0 ? void 0 : JSON.stringify(body),
          signal: ctrl.signal
        });
      } catch (e) {
        if (ctrl.signal.aborted) throw new ApiError("timeout", `The data service did not answer within ${Math.round(this.opts.timeoutMs / 1e3)} s.`);
        throw new ApiError("network", `Cannot reach the data service at ${this.base}.`, void 0, String(e));
      } finally {
        clearTimeout(timer);
      }
      let data;
      try {
        data = await res.json();
      } catch {
        throw new ApiError("bad_response", `The data service sent an unreadable response (HTTP ${res.status}).`, res.status);
      }
      if (!res.ok) {
        const detail = typeof data === "object" && data && "detail" in data ? String(data.detail) : "";
        throw new ApiError("http", httpMessage(res.status, detail), res.status, detail);
      }
      return data;
    }
    student(flatId, path, method = "GET", body) {
      const flat = this.opts.flatHeader?.() ?? null;
      return this.call(method, `/flats/${encodeURIComponent(flatId)}${path}`, body, flat ?? void 0);
    }
    health() {
      return this.call("GET", "/health");
    }
    flats() {
      return this.call("GET", "/flats");
    }
    references() {
      return this.call("GET", "/references");
    }
    interventions() {
      return this.call("GET", "/interventions");
    }
    scores(f) {
      return this.student(f, "/scores");
    }
    breakdown(f) {
      return this.student(f, "/breakdown");
    }
    profile(f) {
      return this.student(f, "/profile");
    }
    findings(f) {
      return this.student(f, "/findings");
    }
    tips(f) {
      return this.student(f, "/tips");
    }
    flatNotifications(f) {
      return this.student(f, "/notifications");
    }
    scenario(f, req) {
      return this.student(f, "/scenarios", "POST", req);
    }
    report(f, findingId, message) {
      return this.student(f, `/findings/${encodeURIComponent(findingId)}/report`, "POST", { message });
    }
    portfolio() {
      return this.call("GET", "/portfolio");
    }
    portfolioFindings(filter = {}) {
      const q = new URLSearchParams();
      if (filter.responsibility) q.set("responsibility", filter.responsibility);
      if (filter.status) q.set("status", filter.status);
      const s = q.toString();
      return this.call("GET", `/portfolio/findings${s ? `?${s}` : ""}`);
    }
    workorders() {
      return this.call("GET", "/workorders");
    }
    createWorkorder(findingId, note) {
      return this.call("POST", "/workorders", { finding_id: findingId, note });
    }
    patchWorkorder(id, status) {
      return this.call("PATCH", `/workorders/${encodeURIComponent(id)}`, { status });
    }
    verifyWorkorder(id, simulate) {
      return this.call("POST", `/workorders/${encodeURIComponent(id)}/verify`, { simulate });
    }
    reports() {
      return this.call("GET", "/reports");
    }
    managerNotifications() {
      return this.call("GET", "/notifications");
    }
  };
  function httpMessage(status, detail) {
    if (status === 403) return "This flat is not available for your sign-in.";
    if (status === 404) return detail ? `Not found: ${detail}.` : "Not found.";
    if (status === 400) return detail ? `The request was not accepted: ${detail}` : "The request was not accepted.";
    if (status === 422) return "The request had an invalid format.";
    return `The data service returned an error (HTTP ${status}).`;
  }

  // src/api/scenarioRequest.ts
  function nonDefault(chosen, defaults) {
    const out = {};
    for (const [k, v] of Object.entries(chosen)) {
      if (k === "adoption") {
        if (v !== 1 && v !== void 0) out[k] = v;
        continue;
      }
      if (!(k in defaults)) throw new Error(`unknown parameter ${k}`);
      if (v !== defaults[k].default) out[k] = v;
    }
    return out;
  }
  function returnToBaseline(anomalyId, tariff, params = {}) {
    const p = { anomaly_id: anomalyId, tariff };
    if (Object.keys(params).length) p.params = params;
    return { scenario: "return_to_baseline", params: p };
  }
  function applyInterventions(anomalyIds, tariff) {
    return { scenario: "apply_interventions", params: { items: anomalyIds.map((id) => ({ anomaly_id: id })), tariff } };
  }
  function shiftFlexibleLoad(channel, tariff) {
    return { scenario: "shift_flexible_load", params: { channel, tariff } };
  }
  function reduceAwayUsage(fraction, tariff) {
    return { scenario: "reduce_away_usage", params: { fraction, tariff } };
  }
  function sortDeep(o) {
    if (Array.isArray(o)) return o.map(sortDeep);
    if (o && typeof o === "object") {
      const out = {};
      for (const k of Object.keys(o).sort()) out[k] = sortDeep(o[k]);
      return out;
    }
    return o;
  }
  function scenarioKey(flatId, req) {
    return JSON.stringify(sortDeep({ flat_id: flatId, scenario: req.scenario, params: req.params }));
  }

  // src/api/mock.ts
  function browserLoader(baseUrl) {
    const base = baseUrl.replace(/\/+$/, "");
    return async (rel) => {
      let res;
      try {
        res = await fetch(`${base}/${rel}`);
      } catch (e) {
        throw new ApiError("network", "Offline fixtures could not be loaded. Serve the app over http (npm run serve).", void 0, String(e));
      }
      if (!res.ok) throw new ApiError("http", `Fixture file missing: ${rel}`, res.status);
      return res.json();
    };
  }
  var OFFLINE_ACTION = "This action changes data on the backend and is not available in offline (mock) mode. Start the backend and use live mode.";
  var MockApi = class {
    constructor(load) {
      this.load = load;
      this.mode = "mock";
      this.describe = "offline fixtures recorded from the real backend";
      this.index = null;
    }
    idx() {
      this.index ?? (this.index = this.load("index.json"));
      return this.index;
    }
    async meta() {
      return (await this.idx()).meta;
    }
    async get(path) {
      const i = await this.idx();
      const rel = i.get[path];
      if (!rel) {
        if (/^\/flats\/[^/]+\//.test(path)) throw new ApiError("http", "Not found: unknown flat.", 404);
        throw new ApiError("offline_unsupported", `No recorded response for ${path} in offline mode.`);
      }
      return await this.load(rel);
    }
    health() {
      return this.get("/health");
    }
    flats() {
      return this.get("/flats");
    }
    references() {
      return this.get("/references");
    }
    interventions() {
      return this.get("/interventions");
    }
    scores(f) {
      return this.get(`/flats/${f}/scores`);
    }
    breakdown(f) {
      return this.get(`/flats/${f}/breakdown`);
    }
    profile(f) {
      return this.get(`/flats/${f}/profile`);
    }
    findings(f) {
      return this.get(`/flats/${f}/findings`);
    }
    tips(f) {
      return this.get(`/flats/${f}/tips`);
    }
    flatNotifications(f) {
      return this.get(`/flats/${f}/notifications`);
    }
    async scenario(f, req) {
      const i = await this.idx();
      const rel = i.scenarios[scenarioKey(f, req)];
      if (!rel) {
        throw new ApiError(
          "offline_unsupported",
          "This combination was not recorded for offline mode. Start the backend (live mode) to calculate it."
        );
      }
      return await this.load(rel);
    }
    portfolio() {
      return this.get("/portfolio");
    }
    portfolioFindings(filter = {}) {
      if (filter.status) return Promise.reject(new ApiError("offline_unsupported", "Status filters need live mode."));
      return this.get(filter.responsibility ? `/portfolio/findings?responsibility=${filter.responsibility}` : "/portfolio/findings");
    }
    workorders() {
      return this.get("/workorders");
    }
    reports() {
      return this.get("/reports");
    }
    managerNotifications() {
      return this.get("/notifications");
    }
    report() {
      return Promise.reject(new ApiError("offline_unsupported", OFFLINE_ACTION));
    }
    createWorkorder() {
      return Promise.reject(new ApiError("offline_unsupported", OFFLINE_ACTION));
    }
    patchWorkorder() {
      return Promise.reject(new ApiError("offline_unsupported", OFFLINE_ACTION));
    }
    verifyWorkorder() {
      return Promise.reject(new ApiError("offline_unsupported", OFFLINE_ACTION));
    }
  };

  // src/api/index.ts
  function createApi(config, flatHeader) {
    if (config.mode === "mock") return new MockApi(browserLoader(config.fixturesBase));
    return new LiveApi({ baseUrl: config.apiBase, timeoutMs: config.timeoutMs, flatHeader });
  }

  // src/auth.ts
  var DEMO_MODE = true;
  var STORAGE_KEY = "wattwise.session";
  var MIN_PASSWORD_LENGTH = 8;
  function parseFlatNumber(input, known) {
    const m = /^\s*f?\s*0*(\d{1,3})\s*$/i.exec(input);
    if (!m) return null;
    const id = `F${m[1].padStart(3, "0")}`;
    return known.includes(id) ? id : null;
  }
  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
  function loginStudent(input, known) {
    if (input.trim() === "") return { ok: false, message: "Enter your flat number." };
    const flatId = parseFlatNumber(input, known);
    if (!flatId) {
      const range2 = known.length ? ` (${known[0]} to ${known[known.length - 1]})` : "";
      return { ok: false, message: `We could not find that flat. Try a number like 3 or F003${range2}.` };
    }
    return { ok: true, session: { role: "student", flatId } };
  }
  async function loginManager(email, password) {
    const cleanEmail = email.trim().toLowerCase();
    if (cleanEmail === "") return { ok: false, field: "email", message: "Enter your email address." };
    if (!isValidEmail(cleanEmail)) {
      return { ok: false, field: "email", message: "That does not look like an email address." };
    }
    if (password === "") return { ok: false, field: "password", message: "Enter your password." };
    if (password.length < MIN_PASSWORD_LENGTH) {
      return {
        ok: false,
        field: "password",
        message: `Passwords have at least ${MIN_PASSWORD_LENGTH} characters.`
      };
    }
    return { ok: true, session: { role: "manager", email: cleanEmail } };
  }
  function saveSession(session) {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    } catch {
    }
  }
  function clearSession() {
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
    }
  }
  function loadSession() {
    try {
      const raw = sessionStorage.getItem(STORAGE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (typeof data !== "object" || data === null) return null;
      const d = data;
      if (d.role === "student" && typeof d.flatId === "string" && /^F\d{3}$/.test(d.flatId)) {
        return { role: "student", flatId: d.flatId };
      }
      if (d.role === "manager" && typeof d.email === "string" && isValidEmail(d.email)) {
        return { role: "manager", email: d.email };
      }
      return null;
    } catch {
      return null;
    }
  }

  // src/config.ts
  var DEFAULT_CONFIG = {
    mode: "live",
    apiBase: "http://localhost:8000",
    fixturesBase: "fixtures",
    timeoutMs: 2e4
  };
  function resolveConfig(fromWindow, search) {
    const c = { ...DEFAULT_CONFIG, ...fromWindow ?? {} };
    const q = new URLSearchParams(search);
    const mode = q.get("mode");
    if (mode === "live" || mode === "mock") c.mode = mode;
    const api2 = q.get("api");
    if (api2 && /^https?:\/\/[^\s]+$/.test(api2)) c.apiBase = api2;
    if (c.mode !== "live" && c.mode !== "mock") c.mode = "live";
    return c;
  }

  // src/dom.ts
  var ESCAPES = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  };
  function esc(s) {
    return s.replace(/[&<>"']/g, (c) => ESCAPES[c] ?? c);
  }
  function $(selector, root = document) {
    const el = root.querySelector(selector);
    if (!el) throw new Error(`Missing element: ${selector}`);
    return el;
  }

  // src/ui.ts
  function badge(kind, text) {
    return `<span class="badge ${kind}">${esc(text)}</span>`;
  }
  function plainList(items) {
    return `<ul class="plain">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
  }
  function details(summary, bodyHtml, open = false) {
    return `<details class="more"${open ? " open" : ""}><summary>${esc(summary)}</summary><div class="more-body">${bodyHtml}</div></details>`;
  }
  function loadingHtml(what) {
    return `<p class="loading" role="status"><span class="spinner" aria-hidden="true"></span>Loading ${esc(what)}\u2026</p>`;
  }
  function errorMessage(e) {
    if (e instanceof ApiError) return e.message;
    return "Something went wrong while showing this part of the page.";
  }
  function errorHtml(e, what) {
    const offline = e instanceof ApiError && e.kind === "offline_unsupported";
    return `<div class="error-box" role="alert"><strong>${esc(offline ? `${what}: not available offline.` : `Could not load ${what}.`)}</strong> ${esc(
      errorMessage(e)
    )} <span class="note">No numbers are shown instead.</span></div>`;
  }
  function emptyHtml(text) {
    return `<p class="empty">${esc(text)}</p>`;
  }
  async function loadInto(el, what, load, render2) {
    el.setAttribute("aria-busy", "true");
    el.innerHTML = loadingHtml(what);
    try {
      const data = await load();
      el.innerHTML = render2(data);
      return data;
    } catch (e) {
      el.innerHTML = errorHtml(e, what);
      return null;
    } finally {
      el.removeAttribute("aria-busy");
    }
  }
  function kv(rows) {
    return `<dl class="kv">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`;
  }
  function statusBadge(status, wording) {
    const kind = status === "VERIFIED" ? "verified" : status === "DETECTED" || status === "PLAUSIBLE" ? "hypothesis" : "owner";
    return `<span class="badge ${kind}" title="Status ${esc(status)}">${esc(wording)}</span>`;
  }

  // src/login.ts
  function setError(input, box, message) {
    box.textContent = message;
    if (message) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  }
  function mountLogin(root, onLogin, flatIds) {
    let known = null;
    root.innerHTML = `
  <div class="login-wrap">
    <section class="login-card" aria-labelledby="l-title">
      <div class="eyebrow">Welcome</div>
      <h1 id="l-title">Sign in to Watt Wise</h1>

      <div class="seg" role="group" aria-label="I am a">
        <button type="button" class="tab" data-role="student" aria-pressed="true">I\u2019m a student</button>
        <button type="button" class="tab" data-role="manager" aria-pressed="false">I\u2019m a manager</button>
      </div>

      <form id="l-student" novalidate>
        <p class="lead">Type your flat number to see your flat. No password needed.</p>
        <div class="field">
          <label for="l-flat">Flat number</label>
          <input id="l-flat" name="flat" type="text" inputmode="text" autocomplete="off" autocapitalize="characters" placeholder="e.g. 3 or F003" aria-describedby="l-flat-hint l-flat-err">
          <div class="hint" id="l-flat-hint">Loading the list of flats\u2026</div>
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

      ${DEMO_MODE ? `<p class="demo-note"><strong>Demo sign-in, not security.</strong> There are no real accounts. Any well-formed email and a password of ${MIN_PASSWORD_LENGTH}+ characters opens the manager view, and a flat number is not a secret. The backend only checks an X-Flat-Id header, which is not authentication.</p>` : ""}
    </section>
  </div>`;
    const studentForm = $("#l-student");
    const managerForm = $("#l-manager");
    const flatInput = $("#l-flat");
    const flatErr = $("#l-flat-err");
    const emailInput = $("#l-email");
    const emailErr = $("#l-email-err");
    const passInput = $("#l-pass");
    const passErr = $("#l-pass-err");
    const managerBtn = $("#l-manager-btn");
    function showRole(role) {
      studentForm.hidden = role !== "student";
      managerForm.hidden = role !== "manager";
      document.querySelectorAll(".seg [data-role]").forEach((b) => {
        b.setAttribute("aria-pressed", String(b.dataset.role === role));
      });
      (role === "student" ? flatInput : emailInput).focus();
    }
    document.querySelectorAll(".seg [data-role]").forEach((b) => {
      b.addEventListener("click", () => showRole(b.dataset.role === "manager" ? "manager" : "student"));
    });
    const hint = $("#l-flat-hint");
    const studentBtn = $("#l-student button[type=submit]");
    const loadFlats = async () => {
      if (known) return known;
      try {
        known = await flatIds();
        hint.textContent = known.length ? `Flats run from ${known[0]} to ${known[known.length - 1]}.` : "No flats are available.";
        return known;
      } catch (e) {
        hint.textContent = "The list of flats could not be loaded.";
        setError(flatInput, flatErr, `${errorMessage(e)} Try again when the data service is running.`);
        return null;
      }
    };
    void loadFlats();
    studentForm.addEventListener("submit", async (e) => {
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
      setError(flatInput, flatErr, "");
      onLogin(result.session);
    });
    flatInput.addEventListener("input", () => setError(flatInput, flatErr, ""));
    managerForm.addEventListener("submit", (e) => {
      e.preventDefault();
      setError(emailInput, emailErr, "");
      setError(passInput, passErr, "");
      managerBtn.disabled = true;
      managerBtn.textContent = "Signing in\u2026";
      loginManager(emailInput.value, passInput.value).then(
        (result) => {
          managerBtn.disabled = false;
          managerBtn.textContent = "Sign in";
          if (result.ok) {
            onLogin(result.session);
            return;
          }
          if (result.field === "email") {
            setError(emailInput, emailErr, result.message);
            emailInput.focus();
          } else {
            setError(passInput, passErr, result.message);
            passInput.focus();
          }
        },
        () => {
          managerBtn.disabled = false;
          managerBtn.textContent = "Sign in";
          setError(passInput, passErr, "Something went wrong. Please try again.");
        }
      );
    });
    emailInput.addEventListener("input", () => setError(emailInput, emailErr, ""));
    passInput.addEventListener("input", () => setError(passInput, passErr, ""));
    const toggle = $("#l-pw-toggle");
    toggle.addEventListener("click", () => {
      const show = passInput.type === "password";
      passInput.type = show ? "text" : "password";
      toggle.textContent = show ? "Hide" : "Show";
      toggle.setAttribute("aria-pressed", String(show));
    });
    flatInput.focus();
  }

  // src/api/workorders.ts
  var LABEL = {
    open: "Open",
    sent: "Sent to technician",
    repaired: "Repaired, waiting for post-repair data"
  };
  var ACTIONS = {
    open: [{ kind: "patch", status: "sent", label: "Mark as sent to technician" }],
    sent: [{ kind: "patch", status: "repaired", label: "Mark as repaired" }],
    repaired: [{ kind: "verify_simulated", label: "Run verification with SIMULATED post-repair data (demo)" }]
  };
  function toView(w) {
    const verified = w.verification != null;
    const simulated = Boolean(w.verification?.simulated);
    return {
      id: w.id,
      findingId: w.finding_id,
      flatId: w.flat_id,
      status: w.status,
      statusLabel: verified ? `${LABEL[w.status] ?? w.status} \xB7 verification ${w.verification?.status ?? ""}`.trim() : LABEL[w.status] ?? w.status,
      actions: verified ? [] : ACTIONS[w.status] ?? [],
      verification: w.verification,
      simulated
    };
  }
  function byFinding(list) {
    return new Map(list.map((w) => [w.finding_id, toView(w)]));
  }

  // src/format.ts
  var TZ = "Europe/Stockholm";
  var NA = "not available";
  function ok(n) {
    return typeof n === "number" && Number.isFinite(n);
  }
  function num(n, digits = 0) {
    if (!ok(n)) return NA;
    const r = Number(n.toFixed(digits));
    return (Object.is(r, -0) ? 0 : r).toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }
  function signed(n, digits = 1) {
    if (!ok(n)) return NA;
    const r = Number(n.toFixed(digits));
    if (r === 0) return num(0, digits);
    return (r > 0 ? "+" : "\u2212") + num(Math.abs(r), digits);
  }
  var kwh = (n, d = 1) => ok(n) ? `${num(n, d)} kWh` : NA;
  var sek = (n, d = 2) => ok(n) ? `${num(n, d)} SEK` : NA;
  var co2 = (n, d = 2) => ok(n) ? `${num(n, d)} kg CO\u2082e` : NA;
  var pct = (fraction, d = 0) => ok(fraction) ? `${num(fraction * 100, d)} %` : NA;
  var score = (n) => ok(n) ? num(n, 1) : NA;
  function range(lo, hi, unit, d = 1) {
    if (!ok(lo) || !ok(hi)) return NA;
    return `${num(lo, d)}\u2013${num(hi, d)} ${unit}`;
  }
  function parseUtc(s) {
    const t = s.includes("T") ? s : s.replace(" ", "T");
    const d = new Date(t);
    if (Number.isNaN(d.getTime())) throw new Error(`bad timestamp ${s}`);
    return d;
  }
  function localDate(isoUtc) {
    return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" }).format(parseUtc(isoUtc));
  }
  function calendarDate(ymd) {
    const [y, m, d] = ymd.split("-").map(Number);
    return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", weekday: "short", day: "numeric", month: "short" }).format(
      new Date(Date.UTC(y, m - 1, d))
    );
  }
  var hour = (h) => `${String(h).padStart(2, "0")}:00`;
  function hourRanges(hours) {
    const s = [...hours].sort((a, b) => a - b);
    const runs = [];
    for (const h of s) {
      const last = runs[runs.length - 1];
      if (last && h === last[1] + 1) last[1] = h;
      else runs.push([h, h]);
    }
    const parts = runs.map(([a, b]) => `${hour(a)}\u2013${hour((b + 1) % 24)}`);
    return parts.length <= 1 ? parts[0] ?? "none" : `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
  }
  var TARIFF_LABEL = {
    hourly_spot: "Hourly spot price",
    monthly_average_spot: "Monthly average spot price",
    fixed_price: "Fixed price",
    included_in_rent: "Electricity included in rent",
    unknown: "I don\u2019t know my contract"
  };
  var MONEY_NOTE = "Spot-energy component only (excl. VAT, network fee, energy tax, markup and fixed fees). Not a bill.";
  function appliance(assumedType) {
    return assumedType.endsWith("-like") ? `${assumedType} appliance` : assumedType;
  }
  function days(n) {
    if (!ok(n)) return NA;
    return `${num(n, Number.isInteger(n) ? 0 : 1)} day${n === 1 ? "" : "s"}`;
  }

  // src/components/tariff.ts
  var TARIFFS = ["unknown", "hourly_spot", "monthly_average_spot", "fixed_price", "included_in_rent"];
  function tariffSelectorHtml(prefix, current) {
    const radios = TARIFFS.map(
      (t) => `<label class="radio"><input type="radio" name="${prefix}-tariff" value="${t}" ${current.type === t ? "checked" : ""}> ${esc(TARIFF_LABEL[t])}</label>`
    ).join("");
    const price = current.fixed_price_sek_per_kwh ?? "";
    return `<fieldset class="scenario" id="${prefix}-tariff-box">
      <legend>Your electricity contract</legend>
      ${radios}
      <div class="fixed-price" ${current.type === "fixed_price" ? "" : "hidden"}>
        <label for="${prefix}-fixed" class="range-label">Your fixed energy price (SEK per kWh, excl. VAT)</label>
        <input id="${prefix}-fixed" type="number" inputmode="decimal" min="0" max="20" step="0.01" value="${esc(String(price))}">
        <p class="note">Fixed-price values are calculated by the backend when you run a simulation with your price.</p>
      </div>
      <p class="note">${esc(MONEY_NOTE)}</p>
    </fieldset>`;
  }
  function bindTariffSelector(prefix, root, onChange) {
    const box = root.querySelector(`#${prefix}-tariff-box`);
    if (!box) return;
    const fixedWrap = box.querySelector(".fixed-price");
    const fixed = box.querySelector(`#${prefix}-fixed`);
    const emit = () => {
      const t = box.querySelector(`input[name="${prefix}-tariff"]:checked`)?.value ?? "unknown";
      if (fixedWrap) fixedWrap.hidden = t !== "fixed_price";
      const spec = { type: t };
      if (t === "fixed_price") {
        const v = fixed?.value.trim() ? Number(fixed.value) : NaN;
        if (Number.isFinite(v) && v >= 0) spec.fixed_price_sek_per_kwh = v;
      }
      onChange(spec);
    };
    box.addEventListener("change", emit);
    fixed?.addEventListener("input", emit);
  }
  function tariffForRequest(t) {
    if (t.type === "fixed_price") {
      return t.fixed_price_sek_per_kwh != null ? { type: "fixed_price", fixed_price_sek_per_kwh: t.fixed_price_sek_per_kwh } : { type: "unknown" };
    }
    return { type: t.type };
  }
  function moneyFor(v, t, kind) {
    const spot = `${sek(v.sek_if_hourly_spot)} if you pay hourly spot prices`;
    if (t.type === "unknown") {
      return { text: spot, note: "Choose your contract above to see what applies to you." };
    }
    if (t.type === "fixed_price") {
      if (v.tariff === "fixed_price" && v.sek != null) return { text: sek(v.sek), note: "At your fixed price, calculated by the backend." };
      const zero = v.sek_by_tariff.fixed_price;
      if (zero === 0 && kind === "shift") return { text: sek(0), note: "Moving use to other hours does not change a fixed-price bill." };
      return { text: "run the simulation with your price", note: "The backend values a fixed price once you enter it and run the simulation." };
    }
    const val = v.tariff === t.type && v.sek != null ? v.sek : v.sek_by_tariff[t.type];
    const note = t.type === "included_in_rent" ? "Electricity is included in your rent, so you save 0 SEK; the landlord\u2019s saving depends on its own contract." : t.type === "monthly_average_spot" && kind === "shift" ? "With a monthly average price, moving use to other hours does not change your cost." : t.type === "monthly_average_spot" ? "Valued at the period\u2019s average spot price." : "Valued at each hour\u2019s spot price.";
    return { text: val == null ? NA : sek(val), note };
  }

  // src/components/textCard.ts
  var TITLE = {
    finding: "In plain words",
    finding_summary: "Summary for the manager",
    digest: "Your week in brief",
    score_explanation: "What your score means"
  };
  function textCard(t) {
    if (t.state === "unavailable") {
      return `<div class="textcard unavailable"><div class="textcard-head"><strong>${esc(TITLE[t.kind])}</strong>${badge("placeholder", "Not connected yet")}</div><p class="note">${esc(t.note)}</p></div>`;
    }
    const b = t.source === "llm" ? badge("data", "AI-worded \xB7 numbers from the engine") : badge("placeholder", "Standard wording");
    return `<div class="textcard"><div class="textcard-head"><strong>${esc(TITLE[t.kind])}</strong>${b}</div><p>${esc(t.text)}</p><p class="note">${esc(t.note)}</p></div>`;
  }

  // src/components/findings.ts
  var NEXT_STEP = {
    fault_step_change: "Report it to your building manager. It looks like an equipment change (for example a fridge door seal or thermostat); residents are not scored on it.",
    base_load_outlier: "Walk round the flat for things that stay on day and night (standby electronics, chargers, extra lighting) and switch off what is not needed.",
    scheduled_block: "Check what runs at the same hours every day, also when nobody is home (a timer, a computer or a screen left on), and turn it off when it is not used.",
    heater_pattern: "Check whether a portable heater is left on while nobody is home. Keep rooms safely warm: do not switch heating off completely, and tell the manager if rooms feel cold.",
    peak_usage: "Start the machine after the evening peak instead of during it. Avoid unattended night runs; a later evening start is enough."
  };
  var TYPE_PILL = {
    fault_step_change: { cls: "check", label: "Possible equipment issue" },
    base_load_outlier: { cls: "waste", label: "Always-on use" },
    scheduled_block: { cls: "waste", label: "Fixed-hour use" },
    heater_pattern: { cls: "waste", label: "Heating while away" },
    peak_usage: { cls: "shift", label: "Timing (shift, same kWh)" }
  };
  function statsTable(stats) {
    const rows = Object.entries(stats).filter(([, v]) => v !== null && typeof v !== "object").map(([k, v]) => `<tr><th scope="row">${esc(k.replace(/_/g, " "))}</th><td>${esc(typeof v === "number" ? String(v) : String(v))}</td></tr>`).join("");
    return `<div class="table-wrap"><table class="data compact"><tbody>${rows}</tbody></table></div>`;
  }
  function savingsBlock(f, tariff) {
    const a = f.avoidable_28d;
    const q = f.quantities;
    const shift = a.kind === "shift";
    const money = moneyFor(f.valuation, tariff, a.kind);
    const energyLine = shift ? `<div class="kpi"><span class="kpi-label">Electricity moved to other hours</span><span class="kpi-val">${esc(kwh(q.kwh_moved))}</span><span class="note">Same total use: 0 kWh saved. Only the timing changes.</span></div>` : `<div class="kpi"><span class="kpi-label">Energy that could be avoided</span><span class="kpi-val">${esc(kwh(a.kwh))}</span><span class="note">Simulated, if acted on fully.</span></div>`;
    return `<div class="kpis small">
      ${energyLine}
      <div class="kpi"><span class="kpi-label">Money (conditional on your contract)</span><span class="kpi-val">${esc(money.text)}</span><span class="note">${esc(money.note)}</span></div>
      <div class="kpi"><span class="kpi-label">Emissions avoided</span><span class="kpi-val">${esc(co2(a.co2_kg))}</span><span class="note">Synthetic average hourly factors.</span></div>
    </div>
    <p class="note">${badge("simulated", "Simulated")} Over ${esc(days(a.window_days))} of observed data (${esc(a.horizon)}). ${esc(a.method)}.</p>`;
  }
  function uncertaintyBlock(f) {
    const u = f.uncertainty;
    const ci = u.sampling_ci95;
    const sr = u.scenario_range;
    return kv([
      ["Sampling range (95 %)", `${esc(range(ci.kwh[0], ci.kwh[1], "kWh"))}; ${esc(range(ci.sek_spot_hourly[0], ci.sek_spot_hourly[1], "SEK if hourly spot", 2))}<br><span class="note">${esc(ci.method)}</span>`],
      [
        "Assumption range",
        sr ? `${esc(range(sr.kwh[0], sr.kwh[1], "kWh"))}; ${esc(range(sr.sek_spot_hourly[0], sr.sek_spot_hourly[1], "SEK if hourly spot", 2))}<br><span class="note">${esc(u.scenario_method)}</span>` : esc(NA)
      ],
      ["Evidence strength", `${esc(f.evidence.confidence_note)}`]
    ]);
  }
  function projectionBlock(f) {
    const p = f.projection_annual;
    if (p.sek.value == null) {
      return `<p class="note">${badge("placeholder", "No yearly figure")} ${esc(p.sek.reason ?? "Not extrapolated.")}</p>`;
    }
    return `<p class="note">${badge("projected", "Projection, not a promise")} If the pattern continued unchanged for a year: ${esc(kwh(p.kwh.value, 0))} (${esc(
      range(p.kwh.low, p.kwh.high, "kWh", 0)
    )}), ${esc(sek(p.sek.value, 0))} if hourly spot (${esc(range(p.sek.low, p.sek.high, "SEK", 0))}). ${esc(p.sek.range_method ?? "")}. ${esc(p.sek.assumptions.join("; "))}.</p>`;
  }
  function tiersBlock(f) {
    const t = f.tiers;
    const verified = t.verified != null ? `${esc(kwh(t.verified))} measured after the change${f.simulated ? ` ${badge("simulated", "SIMULATED post-repair data")}` : ""}` : esc(t.verified_reason);
    return kv([
      ["Potential (simulated)", `${esc(kwh(t.potential.kwh))} \xB7 ${esc(sek(t.potential.sek_if_hourly_spot))} if hourly spot`],
      ["Estimated realised", esc(t.estimated_realized_reason)],
      ["Verified", verified]
    ]);
  }
  function ladderBlock(f) {
    const q = f.quantities;
    const rows = [
      ["Observed use in the pattern\u2019s hours", q.observed_kwh, q.labels.observed_kwh],
      ["Expected without the pattern", q.expected_baseline_kwh, q.labels.expected_baseline_kwh],
      ["Unexplained excess", q.unexplained_excess_kwh, q.labels.unexplained_excess_kwh],
      ["Avoidable estimate", q.avoidable_estimate_kwh, q.labels.avoidable_estimate_kwh],
      ["Use after the change", q.counterfactual_kwh, q.labels.counterfactual_kwh]
    ];
    if (q.kind === "shift") rows.push(["Moved to later hours", q.kwh_moved, "simulated (same kWh)"]);
    return `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Quantity</th><th scope="col">kWh</th><th scope="col">Kind</th></tr></thead><tbody>${rows.map(([l, v, k]) => `<tr><th scope="row">${esc(l)}</th><td>${esc(num(v, 2))}</td><td>${esc(k)}</td></tr>`).join("")}</tbody></table></div><p class="note">${esc(String(q.observed_hours))} of ${esc(String(q.window_hours))} pattern hours observed.</p>`;
  }
  function evidenceBlock(f) {
    const e = f.evidence;
    return `<p>${esc(e.text)}</p>
    ${kv([
      ["Reference level", e.baseline_kwh_per_h == null ? NA : `${esc(num(e.baseline_kwh_per_h, 4))} kWh per hour`],
      ["Observed level", e.observed_kwh_per_h == null ? NA : `${esc(num(e.observed_kwh_per_h, 4))} kWh per hour`],
      ["Excess vs reference", esc(kwh(e.reported_excess_kwh, 2))]
    ])}
    <div class="subhead">Test statistics</div>${statsTable(e.statistics)}
    <p class="note">${esc(e.confidence_note)}.</p>`;
  }
  function scoreIfFixed(f, lenses) {
    return lenses.map((l) => {
      const s = f.score_if_fixed[l];
      return `${l === "resident" ? "Resident score" : "Apartment score"}: ${esc(score(s.before))} \u2192 ${esc(score(s.after))}`;
    }).join(" \xB7 ");
  }
  function windowText(f) {
    return `${localDate(f.window.start)} \u2013 ${localDate(new Date(parseUtc(f.window.end).getTime() - 1).toISOString())} (${days(f.window.days)})`;
  }
  function findingCard(f, o) {
    const pill = TYPE_PILL[f.type] ?? { cls: "check", label: f.type };
    const lenses = o.audience === "student" ? ["resident", "apartment"] : ["apartment", "resident"];
    return `<article class="card finding" id="finding-${esc(f.id)}" data-finding="${esc(f.id)}">
    <div class="alert-head"><span class="pill ${pill.cls}">${esc(pill.label)}</span>${statusBadge(f.status, f.wording)}</div>
    <h3>${esc(f.title)}</h3>
    <p class="meta">${esc(o.audience === "manager" ? `${f.flat_id} \xB7 ` : "")}${esc(f.channel)} \xB7 ${esc(appliance(f.assumed_type))}${f.assumed_type_is_assumption ? ' <span class="note">(type inferred from the load shape)</span>' : ""}<br>${esc(windowText(f))}</p>
    <p class="owner">${badge("owner", f.responsibility_note)}</p>
    ${o.text ? textCard(o.text) : ""}
    <div class="subhead">What you can do</div><p>${esc(NEXT_STEP[f.type] ?? "")}</p>
    ${savingsBlock(f, o.tariff)}
    ${projectionBlock(f)}
    <p class="note">Score if fixed: ${scoreIfFixed(f, lenses)}. Counts as: ${esc(f.counts_as)}.</p>
    ${details("Evidence", evidenceBlock(f))}
    ${details("Uncertainty", uncertaintyBlock(f))}
    ${details("How the saving is built", ladderBlock(f) + tiersBlock(f))}
    ${details("Assumptions", plainList(f.assumptions))}
    ${o.actionsHtml ?? ""}
  </article>`;
  }

  // src/api/texts.ts
  function fromTip(t) {
    const src2 = t.source === "llm" ? "llm" : "template";
    return {
      kind: "finding",
      audience: "student",
      state: "ok",
      source: src2,
      text: t.text,
      note: src2 === "llm" ? "AI-worded text. Every number in it comes from the engine." : "Standard wording filled with engine numbers."
    };
  }
  function unavailable(kind, audience) {
    return {
      kind,
      audience,
      state: "unavailable",
      source: "none",
      text: "",
      note: "AI explanations for this view are not connected yet. The figures below come directly from the engine."
    };
  }
  async function studentFindingTexts(api2, flatId) {
    const tips = await api2.tips(flatId);
    return new Map(tips.map((t) => [t.finding_id, fromTip(t)]));
  }

  // src/state.ts
  var TARIFF_KEY = "wattwise.tariff";
  var state = {
    session: null,
    config: null,
    api: null,
    tariff: loadTariff()
  };
  function loadTariff() {
    try {
      const raw = typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(TARIFF_KEY);
      const t = raw ? JSON.parse(raw) : null;
      if (t && typeof t.type === "string") return t;
    } catch {
    }
    return { type: "unknown" };
  }
  function setTariff(t) {
    state.tariff = t;
    try {
      sessionStorage.setItem(TARIFF_KEY, JSON.stringify(t));
    } catch {
    }
  }
  function api() {
    if (!state.api) throw new Error("API not initialised");
    return state.api;
  }

  // src/manager.ts
  function kpi(label, value, note = "") {
    return `<div class="kpi"><span class="kpi-label">${esc(label)}</span><span class="kpi-val">${esc(value)}</span>${note ? `<span class="note">${esc(note)}</span>` : ""}</div>`;
  }
  function overview(p) {
    const t = p.totals;
    const pot = p.potential;
    return `<div class="kpis">
      ${kpi("Electricity, 8 flats", kwh(t.kwh, 1), "1\u201328 Oct 2026, measured")}
      ${kpi("Spot-price cost", sek(t.sek, 2), "Energy part only, not a bill")}
      ${kpi("Emissions", co2(t.co2_kg, 2), "Synthetic average factors")}
      ${kpi("Combined potential", kwh(pot.kwh, 1), `${sek(pot.sek_if_hourly_spot, 2)} if hourly spot \xB7 ${co2(pot.co2_kg, 2)}`)}
    </div>
    <p class="note">${badge("simulated", "Simulated")} ${esc(pot.label)}. Each flat's findings are applied together on its hourly data, so nothing is counted twice.</p>`;
  }
  function flatTable(p) {
    const max = Math.max(...p.flats.map((f) => f.kwh_28d), 1e-9);
    const rows = p.flats.map(
      (f) => `<tr>
      <th scope="row">${esc(f.flat_id)}</th>
      <td>${esc(String(f.residents))} \xB7 ${esc(String(f.floor_area_m2))} m\xB2</td>
      <td><div class="inline-bar"><span style="width:${Math.round(f.kwh_28d / max * 100)}%"></span></div>${esc(num(f.kwh_28d, 1))}</td>
      <td>${esc(num(f.sek_28d, 2))}</td>
      <td>${esc(num(f.co2_kg_28d, 2))}</td>
      <td>${esc(num(f.comparison.kwh_per_m2, 2))}</td>
      <td>${esc(num(f.comparison.explained_kwh_per_eq_resident_day, 2))}</td>
      <td><strong>${esc(score(f.apartment_score))}</strong> ${esc(f.apartment_band)} <span class="unit">#${esc(num(f.apartment_rank, 0))}</span></td>
      <td>${esc(score(f.resident_score))} ${esc(f.resident_band)}</td>
      <td>${esc(score(f.health))}</td>
      <td>${esc(num(f.comparison.possible_fault_kwh, 1))} / ${esc(num(f.comparison.possible_avoidable_kwh, 1))}</td>
      <td>${esc(String(f.open_manager_findings))} / ${esc(String(f.open_findings))}</td>
      <td>${esc(pct(f.coverage, 1))}</td>
    </tr>`
    ).join("");
    return `<div class="table-wrap"><table class="data">
    <caption>Measured 1\u201328 Oct 2026. Context-adjusted: explained use per equivalent resident (\u221Aresidents) per day.</caption>
    <thead><tr><th scope="col">Flat</th><th scope="col">Size</th><th scope="col">kWh</th><th scope="col">SEK spot</th><th scope="col">kg CO\u2082e</th><th scope="col">kWh/m\xB2</th><th scope="col">kWh/eq. res./day</th><th scope="col">Apartment score</th><th scope="col">Resident score</th><th scope="col">Health</th><th scope="col">Possible fault / avoidable kWh</th><th scope="col">Open (manager / all)</th><th scope="col">Readings</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
  }
  function potentialTable(p) {
    const rows = p.flats.map((f) => {
      const c = f.combined_potential;
      if (!c) return `<tr><th scope="row">${esc(f.flat_id)}</th><td colspan="5" class="dash">no findings</td></tr>`;
      return `<tr><th scope="row">${esc(f.flat_id)}</th><td>${esc(num(c.kwh, 2))}</td><td>${esc(num(c.sek_if_hourly_spot, 2))}</td><td>${esc(num(c.co2_kg, 3))}</td><td>${esc(
        score(f.apartment_score)
      )} \u2192 ${esc(score(c.score_after.apartment.score))}</td><td class="note">${esc(c.findings.join(", "))}</td></tr>`;
    }).join("");
    return `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Flat</th><th scope="col">kWh avoided</th><th scope="col">SEK if hourly spot</th><th scope="col">kg CO\u2082e</th><th scope="col">Apartment score</th><th scope="col">Findings applied</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function dataQuality(p) {
    const q = p.data_quality;
    const ev = p.evidence_quality;
    return kv([
      ["Data source", esc(String(q.data_source))],
      ["Readings", `${esc(num(q.readings_rows ?? null, 0))} rows, ${esc(num(q.readings_missing_kwh ?? null, 0))} missing (kept missing, never 0)`],
      ["Hours without a spot price", esc(num(q.prices_missing_spot_hours ?? null, 0))],
      ["Occupancy / outdoor gaps", `${esc(num(q.context_occupancy_missing ?? null, 0))} / ${esc(num(q.context_outdoor_missing ?? null, 0))} hours`],
      ["Coverage by flat", Object.entries(q.coverage_by_flat).map(([k, v]) => `${esc(k)} ${esc(pct(v, 1))}`).join(" \xB7 ")],
      ["Findings by evidence level", Object.entries(ev.findings_by_status).map(([k, v]) => `${esc(k)}: ${esc(String(v))}`).join(" \xB7 ") + `<br><span class="note">${esc(ev.note)}</span>`],
      ["Peak hours (local)", esc(hourRanges(p.references.peak_hours_local))],
      ["Frozen references", `hash ${esc(p.references.hash)}`]
    ]);
  }
  function workOrderPanel(f, w, live) {
    if (!live) return `<div class="wo"><div class="subhead">Work order</div><p class="note">Work orders change data on the backend and need live mode.</p></div>`;
    if (!w) {
      return `<div class="wo"><div class="subhead">Work order</div><p class="note">Opening a work order records the manager's confirmation of this finding.</p>
      <button class="btn inline" type="button" data-wo-create="${esc(f.id)}">Open work order</button><p class="form-status" role="status" aria-live="polite"></p></div>`;
    }
    const v = w.verification;
    return `<div class="wo"><div class="subhead">Work order ${esc(w.id)}</div><p><strong>${esc(w.statusLabel)}</strong>${w.simulated ? ` ${badge("simulated", "SIMULATED post-repair data")}` : ""}</p>
    ${v ? `<p class="note">Verification: ${esc(v.status)}${v.saving_kwh != null ? `, saving ${esc(kwh(v.saving_kwh, 2))}` : ""}${v.reason ? ` (${esc(String(v.reason))})` : ""}</p>` : ""}
    <div class="row">${w.actions.map(
      (a) => a.kind === "patch" ? `<button class="btn inline secondary" type="button" data-wo="${esc(w.id)}" data-wo-status="${esc(a.status)}">${esc(a.label)}</button>` : `<button class="btn inline secondary" type="button" data-wo-verify="${esc(w.id)}">${esc(a.label)}</button>`
    ).join("")}</div><p class="form-status" role="status" aria-live="polite"></p></div>`;
  }
  function mountManager(root) {
    root.innerHTML = `
  <section class="hero">
    <div class="hero-text">
      <div class="eyebrow">Manager view</div>
      <h1>The whole portfolio, with its caveats.</h1>
      <p>Compare flats, follow up possible equipment issues and see what acting on the findings could change, without mistaking a simulation for a result.</p>
    </div>
  </section>
  <nav class="jump" aria-label="On this page"><a href="#m-h-over">Overview</a><a href="#m-h-flats">Flats</a><a href="#m-h-maint">Maintenance</a><a href="#m-h-res">Resident actions</a><a href="#m-h-dq">Data quality</a></nav>

  <section class="panel" aria-labelledby="m-h-over">
    <div class="panel-head"><h2 id="m-h-over">Portfolio</h2>${badge("measured", "Measured")}</div>
    <div id="m-over"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-flats">
    <div class="panel-head"><h2 id="m-h-flats">Eight flats compared</h2>${badge("measured", "From the engine")}</div>
    <div id="m-flats"></div>
    ${details("Combined potential per flat (simulated)", '<div id="m-pot"></div>')}
  </section>

  <h2 class="section-title" id="m-h-maint">Possible equipment issues</h2>
  <p class="lead">Findings the building manager is responsible for. \u201CPossible fault\u201D means a statistical test was met; it becomes confirmed only when someone checks it.</p>
  ${textCard(unavailable("finding_summary", "manager"))}
  <section class="cards" id="m-maint" aria-labelledby="m-h-maint"></section>

  <section class="panel" aria-labelledby="m-h-res">
    <div class="panel-head"><h2 id="m-h-res">Resident-controlled opportunities</h2>${badge("owner", "Residents act")}</div>
    <p class="lead">Behaviour patterns. Residents see these in their own view; no technician is needed.</p>
    <div id="m-res"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-rep">
    <div class="panel-head"><h2 id="m-h-rep">Resident reports and notifications</h2></div>
    <div id="m-rep"></div>
  </section>

  <section class="panel" aria-labelledby="m-h-dq">
    <div class="panel-head"><h2 id="m-h-dq">Data quality and evidence</h2></div>
    <div id="m-dq"></div>
  </section>`;
    const A = api();
    const live = A.mode === "live";
    void (async () => {
      const els = ["#m-over", "#m-flats", "#m-pot", "#m-dq"].map((s) => $(s));
      els.forEach((e) => e.innerHTML = loadingHtml("portfolio"));
      try {
        const p = await A.portfolio();
        $("#m-over").innerHTML = overview(p);
        $("#m-flats").innerHTML = flatTable(p);
        $("#m-pot").innerHTML = potentialTable(p);
        $("#m-dq").innerHTML = dataQuality(p) + details("Assumptions", plainList(p.assumptions));
      } catch (e) {
        els.forEach((el) => el.innerHTML = errorHtml(e, "the portfolio"));
      }
    })();
    const maint = $("#m-maint");
    const renderMaint = async () => {
      maint.innerHTML = loadingHtml("maintenance findings");
      try {
        const [fs, wos] = await Promise.all([A.portfolioFindings({ responsibility: "manager" }), A.workorders()]);
        const map = byFinding(wos);
        maint.innerHTML = fs.length ? fs.map((f) => findingCard(f, { audience: "manager", tariff: { type: "hourly_spot" }, actionsHtml: workOrderPanel(f, map.get(f.id), live) })).join("") : emptyHtml("No possible equipment issues were found.");
      } catch (e) {
        maint.innerHTML = errorHtml(e, "maintenance findings");
      }
    };
    void renderMaint();
    void loadInto(
      $("#m-res"),
      "resident findings",
      async () => {
        const [r, u] = await Promise.all([A.portfolioFindings({ responsibility: "resident" }), A.portfolioFindings({ responsibility: "unknown" })]);
        return [...u, ...r];
      },
      (fs) => fs.length ? `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Flat</th><th scope="col">Finding</th><th scope="col">Status</th><th scope="col">kWh avoided</th><th scope="col">kWh moved</th><th scope="col">SEK if hourly spot</th><th scope="col">Window</th></tr></thead><tbody>${fs.map(
        (f) => `<tr><th scope="row">${esc(f.flat_id)}</th><td>${esc(f.title)}<br><span class="note">${esc(f.channel)} ${esc(f.assumed_type)}</span></td><td>${statusBadge(f.status, f.wording)}</td><td>${esc(
          f.avoidable_28d.kind === "shift" ? "0 (shift)" : num(f.avoidable_28d.kwh, 2)
        )}</td><td>${esc(f.avoidable_28d.kind === "shift" ? num(f.quantities.kwh_moved, 2) : "\u2013")}</td><td>${esc(num(f.valuation.sek_if_hourly_spot, 2))}</td><td>${esc(days(f.avoidable_28d.window_days))}</td></tr>`
      ).join("")}</tbody></table></div><p class="note">${badge("simulated", "Simulated")} Potential if acted on fully. Shifts move electricity to other hours and save 0 kWh; their money value exists only on an hourly spot contract.</p>` : emptyHtml("No resident-controlled patterns.")
    );
    void loadInto(
      $("#m-rep"),
      "reports",
      async () => ({ reports: await A.reports(), notes: await A.managerNotifications() }),
      ({ reports, notes }) => (reports.length ? `<ul class="plain">${reports.map((r) => `<li>${esc(`${r.id} from ${r.flat_id} on ${r.finding_id}: ${r.message ?? "(no message)"}`)}</li>`).join("")}</ul>` : emptyHtml("No resident reports yet.")) + (notes.length ? `<div class="subhead">Notifications</div><ul class="plain">${notes.map((n) => `<li>${esc(n.text)}</li>`).join("")}</ul>` : "")
    );
    root.addEventListener("click", async (e) => {
      const t = e.target.closest("[data-wo-create],[data-wo],[data-wo-verify]");
      if (!t) return;
      const status = t.closest(".wo")?.querySelector(".form-status");
      t.disabled = true;
      if (status) status.textContent = "Saving\u2026";
      try {
        if (t.dataset.woCreate) await A.createWorkorder(t.dataset.woCreate, null);
        else if (t.dataset.wo) await A.patchWorkorder(t.dataset.wo, t.dataset.woStatus ?? "");
        else if (t.dataset.woVerify) await A.verifyWorkorder(t.dataset.woVerify, true);
        await renderMaint();
      } catch (err) {
        t.disabled = false;
        if (status) status.textContent = `Not saved: ${errorMessage(err)}`;
      }
    });
    void state;
  }

  // src/components/charts.ts
  function hourOfDayChart(p) {
    const vals = p.hour_of_day.map((h) => h.mean_kwh ?? 0);
    const max = Math.max(...vals, 1e-9);
    const bars = p.hour_of_day.map((h) => {
      const cls = h.mean_kwh == null ? "nodata" : h.is_peak ? "peak" : "offpeak";
      const height = h.mean_kwh == null ? 190 : Math.max(2, Math.round(h.mean_kwh / max * 190));
      const tip = `${hour(h.local_hour)} local: ${h.mean_kwh == null ? "no complete reading" : kwh(h.mean_kwh, 3)} on average \xB7 mean spot ${h.mean_spot_sek_per_kwh == null ? NA : `${num(h.mean_spot_sek_per_kwh, 2)} SEK/kWh`}${h.is_peak ? " \xB7 peak-price hour" : ""} \xB7 ${h.hours_in_period} hours in period`;
      return `<div class="bar ${cls}" style="height:${height}px" title="${esc(tip)}"><span class="sr-only">${esc(tip)}</span></div>`;
    }).join("");
    const labels = p.hour_of_day.map((h) => `<span>${h.local_hour % 3 === 0 ? String(h.local_hour).padStart(2, "0") : ""}</span>`).join("");
    return `
    <div class="legend">
      <span><i class="swatch" style="background:var(--orange)"></i>Peak-price hour (${esc(hourRanges(p.peak_hours_local))})</span>
      <span><i class="swatch" style="background:var(--mint)"></i>Other hours</span>
    </div>
    <div class="bars" role="img" aria-label="Average electricity use per local hour of the day">${bars}</div>
    <div class="bar-labels" aria-hidden="true">${labels}</div>
    <p class="note">Average of observed readings per Stockholm clock hour, 1\u201328 Oct 2026. Peak hours are the local hours whose mean spot price is above the period average (${esc(
      num(p.time_avg_price_sek_per_kwh, 3)
    )} SEK/kWh). Hover a bar for the exact value.</p>`;
  }
  function dailyChart(p) {
    const max = Math.max(...p.daily.map((d) => d.kwh), 1e-9);
    const bars = p.daily.map((d) => {
      const flag = !d.complete_day ? ` (partial day: ${d.hours_in_period} h)` : d.hours_in_period === 25 ? " (25-hour day: clocks went back)" : "";
      const tip = `${calendarDate(d.local_date)}: ${kwh(d.kwh, 2)}, ${sek(d.sek)}, ${co2(d.co2_kg)}${flag}; ${pct(d.observed_share)} of readings observed`;
      return `<div class="bar day ${d.complete_day ? "" : "partial"}" style="height:${Math.max(2, Math.round(d.kwh / max * 160))}px" title="${esc(tip)}"><span class="sr-only">${esc(tip)}</span></div>`;
    }).join("");
    const labels = p.daily.map((d, i) => `<span>${i % 7 === 0 || d.local_date.endsWith("-25") ? esc(d.local_date.slice(8)) : ""}</span>`).join("");
    return `
    <div class="bars short" role="img" aria-label="Electricity use per day, Stockholm dates">${bars}</div>
    <div class="bar-labels" aria-hidden="true">${labels}</div>
    <p class="note">Measured kWh per Stockholm date (day of month shown). 1 Oct starts at 02:00 and 29 Oct has one hour because the dataset is defined in UTC (shown lighter). 25 Oct has 25 hours because the clocks went back. Missing readings are left out, not counted as zero.</p>`;
  }
  function channelBars(channels) {
    const max = Math.max(...channels.map((c) => c.share_of_flat ?? 0), 1e-9);
    return channels.map((c) => {
      const missing = c.coverage < 1 ? `<span class="miss" title="${esc(`${c.hours_observed} of 672 hours observed`)}">${esc(pct(1 - c.coverage, 1))} missing</span>` : "";
      return `<div class="chrow">
        <span class="chname"><strong>${esc(c.channel)}</strong> ${esc(c.assumed_type)}${c.assumed_type_is_assumption ? '<sup title="Inferred from the load shape: the data has no appliance labels">*</sup>' : ""}</span>
        <div class="chtrack" aria-hidden="true"><div class="chfill" style="width:${Math.round((c.share_of_flat ?? 0) / max * 100)}%"></div></div>
        <span class="chval">${esc(kwh(c.kwh, 1))}<br><span class="unit">${esc(pct(c.share_of_flat, 0))} \xB7 ${esc(sek(c.sek, 1))}</span>${missing ? `<br>${missing}` : ""}</span>
      </div>`;
    }).join("");
  }

  // src/components/score.ts
  var PILLAR_TEXT = {
    use: {
      name: "Use",
      text: "Explained electricity per equivalent resident per day, compared with a frozen benchmark (the 20th percentile of the 8 flats at baseline). 100 = at or below the benchmark."
    },
    waste: {
      name: "Waste",
      text: "Possible avoidable use found by the detectors (always-on load, fixed-hour use while nobody is home, heating while away). 100 = none found; 50 = as much as a typical flat uses in total."
    },
    timing: {
      name: "Timing",
      text: "Washing-machine-like and dishwasher-like runs in peak-price hours. Moving them later raises this pillar without changing kWh."
    },
    health: {
      name: "Health",
      text: "Possible equipment faults (apartment score only). Residents are not scored on it."
    }
  };
  function pillarRows(v) {
    return Object.entries(v.pillars).map(([k, val]) => {
      const p = PILLAR_TEXT[k] ?? { name: k, text: "" };
      const w = v.weights[k];
      return `<div class="score-row">
        <div><strong>${esc(p.name)}</strong> <span class="unit">weight ${esc(num((w ?? 0) * 100, 0))} %</span><div class="note">${esc(p.text)}</div></div>
        <div class="meter" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${esc(num(val, 1))}" aria-label="${esc(p.name)} pillar"><span style="width:${Math.max(0, Math.min(100, val))}%"></span></div>
        <div class="score-val">${esc(score(val))}</div>
      </div>`;
    }).join("");
  }
  function lensPanel(v, lens) {
    const s = v.sensitivity;
    return `<div class="score-head">
      <div class="big-score"><span class="score-num">${esc(score(v.score))}</span><span class="band band-${esc(v.band)}">${esc(v.band)}</span></div>
      <div>
        <strong>${esc(v.label)}</strong>
        <p class="note">Rank ${esc(num(v.rank, 0))} of ${esc(String(v.of))}. With other reasonable weights: score ${esc(range(s.score_p5, s.score_p95, "", 1))}, rank ${esc(num(s.rank_p5, 0))}\u2013${esc(num(s.rank_p95, 0))}.</p>
        <p class="note">${lens === "resident" ? "Counts only what residents control." : "How the flat performs, including possible equipment faults."}${v.excludes.length ? ` Excludes: ${esc(v.excludes.join("; "))}.` : ""}</p>
      </div>
    </div>
    <div class="score-list">${pillarRows(v)}</div>`;
  }
  function scoreDetails(s) {
    const b = s.benchmark;
    const d = s.pillar_detail;
    return details(
      "What the score is built from",
      kv([
        ["Your explained use", `${esc(num(b.flat_value_resident_lens, 3))} kWh per equivalent resident per day (resident score)`],
        ["Benchmark", `${esc(num(b.benchmark_value_resident_lens, 3))} kWh (frozen ${esc(String(b.percentile))}th percentile of the 8 flats)`],
        ["Possible avoidable use", esc(kwh(d.possible_avoidable_kwh, 1))],
        ["Possible equipment fault", `${esc(kwh(d.possible_fault_kwh, 1))} (apartment score only)`],
        ["Flexible runs in peak hours", esc(kwh(d.peak_flexible_kwh, 1))],
        ["Data coverage", esc(pct(s.uncertainty.data_coverage, 1))]
      ]) + `<p class="note">${esc(s.uncertainty.method)}. References hash ${esc(b.references_hash)}.</p>`
    ) + details("Score assumptions", plainList(s.assumptions));
  }

  // src/components/simulator.ts
  var PARAM_LABEL = {
    fix_fraction: "Share of the extra use that the repair removes",
    repair_after_days: "Repair happens after (days)",
    post_level: "Level after the repair",
    avoidable_fraction: "Share of the extra use that is avoidable",
    only_when_unoccupied: "Only in hours with nobody home",
    min_absence_hours: "Count absences of at least (hours)",
    rebound: "Extra heating needed on return (rebound)",
    share_moved: "Share of peak-hour runs moved",
    max_delay_hours: "Latest start (hours after the original)"
  };
  function valueLabel(v) {
    if (v === true) return "yes";
    if (v === false) return "no";
    if (v === "pre_step_mean") return "level before the step";
    if (v === "peer_mean") return "other flats\u2019 level";
    if (typeof v === "number" && v > 0 && v < 1) return `${Math.round(v * 100)} %`;
    return String(v);
  }
  function simulatorHtml(d) {
    const flexChannels = [...new Set(d.findings.filter((f) => f.type === "peak_usage").map((f) => f.channel))];
    const away = d.findings.some((f) => f.type === "scheduled_block" || f.type === "heater_pattern");
    const adoption = d.api.mode === "mock" ? [1, 0.5] : [1, 0.75, 0.5, 0.25];
    const findingOpts = d.findings.map((f) => `<option value="${esc(f.id)}">${esc(`${f.title} \xB7 ${f.channel} ${f.assumed_type}`)}</option>`).join("");
    const modeRadio = (m, label, disabled = false) => `<label class="radio"><input type="radio" name="sim-mode" value="${m}" ${m === "one" ? "checked" : ""} ${disabled ? "disabled" : ""}> ${esc(label)}${disabled ? ' <span class="note">(no such pattern in this flat)</span>' : ""}</label>`;
    if (!d.findings.length) return `<p class="empty">No patterns were detected for this flat, so there is nothing to simulate.</p>`;
    return `<form id="sim-form" class="sim" novalidate>
      <fieldset class="scenario"><legend>What do you want to try?</legend>
        ${modeRadio("one", "Act on one finding")}
        ${modeRadio("all", "Act on all findings together (no double counting)")}
        ${modeRadio("shift", "Run a flexible appliance after the peak", !flexChannels.length)}
        ${modeRadio("away", "Use less while nobody is home", !away)}
      </fieldset>
      <div data-show="one">
        <label class="range-label" for="sim-finding">Finding</label>
        <select id="sim-finding">${findingOpts}</select>
        <div id="sim-params"></div>
        <label class="range-label" for="sim-adoption">How much of it you would actually do</label>
        <select id="sim-adoption">${adoption.map((a) => `<option value="${a}">${a === 1 ? "All of it" : valueLabel(a)}</option>`).join("")}</select>
      </div>
      <div data-show="shift" hidden>
        <label class="range-label" for="sim-channel">Appliance</label>
        <select id="sim-channel">${flexChannels.map((c) => `<option value="${esc(c)}">${esc(`${c} ${d.findings.find((f) => f.channel === c)?.assumed_type ?? ""}`)}</option>`).join("")}</select>
      </div>
      <div data-show="away" hidden>
        <label class="range-label" for="sim-fraction">Share of that use you would cut</label>
        <select id="sim-fraction"><option value="0.5">50 %</option><option value="1">100 %</option></select>
      </div>
      <button class="btn inline" type="submit" id="sim-run">Run simulation</button>
      ${d.api.mode === "mock" ? '<p class="note">Offline mode: only recorded combinations are available. Start the backend for any combination and for your own fixed price.</p>' : ""}
    </form>
    <div id="sim-result" aria-live="polite"></div>`;
  }
  function paramsHtml(f, o) {
    const spec = o.parameters[f.type] ?? {};
    return Object.entries(spec).map(
      ([k, s]) => `<label class="range-label" for="sim-p-${esc(k)}">${esc(PARAM_LABEL[k] ?? k)}</label>
      <select id="sim-p-${esc(k)}" data-param="${esc(k)}">${s.grid.map(
        (v, i) => `<option value="${i}" ${JSON.stringify(v) === JSON.stringify(s.default) ? "selected" : ""}>${esc(valueLabel(v))}${JSON.stringify(v) === JSON.stringify(s.default) ? " (default)" : ""}</option>`
      ).join("")}</select>`
    ).join("");
  }
  function buildRequest(mode, form, d, tariff) {
    const t = tariffForRequest(tariff);
    if (mode === "all") return applyInterventions(d.findings.map((f2) => f2.id), t);
    if (mode === "shift") return shiftFlexibleLoad(form.querySelector("#sim-channel")?.value ?? "A04", t);
    if (mode === "away") return reduceAwayUsage(Number(form.querySelector("#sim-fraction")?.value ?? 0.5), t);
    const id = form.querySelector("#sim-finding")?.value ?? "";
    const f = d.findings.find((x) => x.id === id);
    if (!f) throw new Error("choose a finding");
    const spec = d.options.parameters[f.type] ?? {};
    const chosen = {};
    form.querySelectorAll("select[data-param]").forEach((s) => {
      const k = s.dataset.param ?? "";
      chosen[k] = spec[k]?.grid[Number(s.value)];
    });
    chosen.adoption = Number(form.querySelector("#sim-adoption")?.value ?? 1);
    return returnToBaseline(f.id, t, nonDefault(chosen, spec));
  }
  function scoreTable(r) {
    const lenses = ["resident", "apartment"];
    const rows = lenses.map((l) => {
      const b = r.before[l];
      const a = r.after[l];
      const pillars = Object.keys(a.pillars).map((k) => `${k} ${score(b.pillars[k])} \u2192 ${score(a.pillars[k])}`).join(", ");
      return `<tr><th scope="row">${l === "resident" ? "Resident score" : "Apartment score"}</th><td>${esc(score(b.score))} (${esc(b.band)}, rank ${esc(num(b.rank, 0))})</td><td>${esc(
        score(a.score)
      )} (${esc(a.band)}, rank ${esc(num(a.rank, 0))})</td><td>${esc(signed(r.score_change[l], 1))}</td><td class="note">${esc(pillars)}</td></tr>`;
    }).join("");
    return `<div class="table-wrap"><table class="data"><caption>Scores before and after (frozen references: other flats unchanged)</caption><thead><tr><th scope="col">Score</th><th scope="col">Before</th><th scope="col">After</th><th scope="col">Change</th><th scope="col">Pillars</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function resultHtml(r, tariff) {
    if (!r.kind || !r.valuation || !r.uncertainty || !r.window) {
      return `<div class="sim-out"><p>${badge("placeholder", "Nothing to simulate")} ${esc(r.assumptions.join("; "))}</p></div>`;
    }
    const money = moneyFor(r.valuation, tariff, r.kind);
    const moved = (r.ladder ?? []).filter((l) => l.kind === "shift");
    const kindLabel = r.kind === "shift" ? "Timing shift (same kWh)" : r.kind === "reduction" ? "Energy reduction" : "Reduction + timing shift";
    const u = r.uncertainty;
    const ci = u.sampling_ci95;
    const sr = u.scenario_range;
    const p = r.projection_annual;
    const ladderRows = (r.ladder ?? []).map(
      (l) => `<tr><th scope="row">${esc(l.anomaly_id)}</th><td>${esc(l.kind)}</td><td>${esc(num(l.observed_kwh, 2))}</td><td>${esc(num(l.avoidable_estimate_kwh, 2))}</td><td>${esc(
        num(l.kwh_moved, 2)
      )}</td><td>${esc(num(l.counterfactual_kwh, 2))}</td></tr>`
    ).join("");
    return `<div class="sim-out">
    <div class="panel-head"><h3>Result</h3><span>${badge("simulated", "Simulated, not measured")} ${badge("data", kindLabel)}</span></div>
    <p class="note">Window: ${esc(localDate(r.window.start_utc))} \u2013 ${esc(localDate(new Date(parseUtc(r.window.end_utc_exclusive).getTime() - 1).toISOString()))} (${esc(days(r.window.days))} of observed data).</p>
    <div class="kpis small">
      <div class="kpi"><span class="kpi-label">Change in electricity use</span><span class="kpi-val">${esc(signed(r.delta_28d.kwh, 2))} kWh</span><span class="note">${r.kind === "shift" ? "A shift keeps the same kWh." : "Negative = less electricity used."}</span></div>
      ${moved.length ? `<div class="kpi"><span class="kpi-label">Electricity moved to later hours</span><span class="kpi-val">${moved.map((m) => esc(kwh(m.kwh_moved, 2))).join(" + ")}</span><span class="note">Moved, not saved.</span></div>` : ""}
      <div class="kpi"><span class="kpi-label">Money (your contract)</span><span class="kpi-val">${esc(money.text)}</span><span class="note">${esc(money.note)}</span></div>
      <div class="kpi"><span class="kpi-label">Change in emissions</span><span class="kpi-val">${esc(signed(r.delta_28d.co2_kg, 3))} kg CO\u2082e</span><span class="note">Synthetic average hourly factors.</span></div>
    </div>
    ${scoreTable(r)}
    ${kv([
      ["Sampling range (95 %) of the saving", `${esc(range(ci.kwh[0], ci.kwh[1], "kWh", 2))}; ${esc(range(ci.sek_spot_hourly[0], ci.sek_spot_hourly[1], "SEK if hourly spot", 2))}`],
      ["Assumption range of the saving", sr ? `${esc(range(sr.kwh[0], sr.kwh[1], "kWh", 2))}; ${esc(range(sr.sek_spot_hourly[0], sr.sek_spot_hourly[1], "SEK if hourly spot", 2))}` : esc(NA)],
      [
        "Yearly",
        p.sek.value == null ? esc(p.sek.reason ?? "not extrapolated") : `${badge("projected", "Projection")} ${esc(sek(p.sek.value, 0))} if hourly spot (${esc(range(p.sek.low, p.sek.high, "SEK", 0))}), ${esc(kwh(p.kwh.value, 0))}`
      ],
      ["Counted twice across items", `${esc(kwh(r.overlap?.kwh ?? null, 2))} (combined effects are calculated together)`],
      ["Shifts into hours with no reading", esc(String(r.missing_hour_moves ?? 0))]
    ])}
    ${details(
      "Per finding",
      `<div class="table-wrap"><table class="data compact"><thead><tr><th scope="col">Finding</th><th scope="col">Kind</th><th scope="col">Observed kWh</th><th scope="col">Avoided kWh</th><th scope="col">Moved kWh</th><th scope="col">kWh after</th></tr></thead><tbody>${ladderRows}</tbody></table></div>`
    )}
    ${details("Assumptions of this simulation", plainList([...r.assumptions, ...u.not_included.map((n) => `not included: ${n}`)]))}
  </div>`;
  }
  function bindSimulator(root, d) {
    const form = root.querySelector("#sim-form");
    const out = root.querySelector("#sim-result");
    if (!form || !out) return { select: () => void 0 };
    const mode = () => form.querySelector('input[name="sim-mode"]:checked')?.value ?? "one";
    const refreshParams = () => {
      const f = d.findings.find((x) => x.id === form.querySelector("#sim-finding")?.value);
      const box = form.querySelector("#sim-params");
      if (box && f) box.innerHTML = paramsHtml(f, d.options);
    };
    const showMode = () => {
      form.querySelectorAll("[data-show]").forEach((el) => {
        el.hidden = el.dataset.show !== mode();
      });
    };
    form.addEventListener("change", (e) => {
      const t = e.target;
      if (t.id === "sim-finding") refreshParams();
      if (t.name === "sim-mode") showMode();
    });
    const run = form.querySelector("#sim-run");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!run || run.disabled) return;
      run.disabled = true;
      run.textContent = "Calculating\u2026";
      out.innerHTML = loadingHtml("the simulation");
      try {
        const tariff = d.tariff();
        const req = buildRequest(mode(), form, d, tariff);
        const r = await d.api.scenario(d.flatId, req);
        out.innerHTML = resultHtml(r, tariff);
      } catch (err) {
        out.innerHTML = errorHtml(err, "the simulation");
      } finally {
        run.disabled = false;
        run.textContent = "Run simulation";
      }
    });
    refreshParams();
    showMode();
    return {
      select(findingId) {
        const one = form.querySelector('input[name="sim-mode"][value="one"]');
        if (one) one.checked = true;
        const sel = form.querySelector("#sim-finding");
        if (sel) sel.value = findingId;
        refreshParams();
        showMode();
        form.scrollIntoView({ behavior: "smooth", block: "start" });
        form.querySelector("#sim-run")?.focus({ preventScroll: true });
      }
    };
  }

  // src/data.ts
  var LIMITATIONS = [
    {
      title: "Spot price only, not a bill",
      body: "Costs use the hourly spot price excluding VAT. Retailer markup, network fees, energy tax, VAT and fixed fees are not in the data, so these figures are not what you pay."
    },
    {
      title: "Your contract decides the money",
      body: "Savings in SEK depend on your electricity contract. Moving use to other hours only saves money on an hourly spot contract; with electricity included in rent you save 0 SEK."
    },
    {
      title: "Appliance types are inferred",
      body: "The data has seven unlabelled channels per flat. Names like \u201Cfridge-like\u201D are inferred from the load shape and are assumptions."
    },
    {
      title: "Four synthetic weeks",
      body: "Synthetic data for 1\u201328 Oct 2026. Yearly figures are shown only for persistent equipment or always-on patterns, always as projections with a range. Heating and timing are not extrapolated."
    },
    {
      title: "Simulated, not verified",
      body: "Savings are simulations of what would change if a pattern were acted on. A saving counts as measured only after at least 7 days of new data show it."
    },
    {
      title: "Missing readings stay missing",
      body: "Hours without a reading are left out of sums (never counted as zero) and reported as coverage."
    },
    {
      title: "Occupancy is simulated",
      body: "Whether someone is home comes from a simulated sensor estimate. It is used as context only, not as tracking of people."
    },
    {
      title: "Times are Stockholm local time",
      body: "Clocks went back on 25 October (that day has 25 hours). The data is stored in UTC and shown in local time."
    }
  ];

  // src/student.ts
  function kpi2(label, value, note = "") {
    return `<div class="kpi"><span class="kpi-label">${esc(label)}</span><span class="kpi-val">${esc(value)}</span>${note ? `<span class="note">${esc(note)}</span>` : ""}</div>`;
  }
  function overviewHtml(b) {
    const t = b.totals;
    return `<div class="kpis">
      ${kpi2("Electricity used", kwh(t.kwh, 1), `${kwh(t.kwh_per_m2, 2)} per m\xB2`)}
      ${kpi2("Spot-price cost", sek(t.sek, 2), "Energy part only, not your bill")}
      ${kpi2("Emissions", co2(t.co2_kg, 2), "Synthetic average factors")}
      ${kpi2("Readings observed", pct(t.coverage, 1), `${pct(t.price_coverage, 1)} of kWh has a spot price`)}
    </div>
    <p class="note">Measured over 1\u201328 Oct 2026 (28 days). Per resident: ${esc(kwh(t.kwh_per_resident, 1))}, ${esc(sek(t.sek_per_resident, 2))}, ${esc(
      co2(t.co2_kg_per_resident, 2)
    )} (${esc(b.per_resident_label)}). ${esc(pct(t.peak_share, 0))} of your electricity was used in peak-price hours.</p>
    ${details("How these numbers are measured", `<ul class="plain">${b.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}<li>${esc(b.uncertainty.note)}</li></ul>`)}`;
  }
  function reportForm(f) {
    return `<form class="report" data-report="${esc(f.id)}" novalidate>
      <label for="rep-${esc(f.id)}">Tell the building manager (optional message)</label>
      <textarea id="rep-${esc(f.id)}" maxlength="500" rows="2" placeholder="e.g. the fridge door does not close properly"></textarea>
      <div class="row"><button class="btn inline secondary" type="submit">Report to the building manager</button>
      <button class="btn inline" type="button" data-sim="${esc(f.id)}">Simulate this</button></div>
      <p class="form-status" role="status" aria-live="polite"></p>
    </form>`;
  }
  function mountStudent(root, flatId) {
    root.innerHTML = `
  <section class="hero">
    <div class="hero-text">
      <div class="eyebrow">Student view</div>
      <h1>Your flat, in plain numbers.</h1>
      <p>See when your flat uses electricity, what the data says could change, and how much to trust each number.</p>
    </div>
    <div class="picker"><span class="picker-label">Signed in for</span><strong class="flat-chip">${esc(flatId)}</strong></div>
  </section>
  <div class="viewing" id="s-meta"></div>
  <nav class="jump" aria-label="On this page"><a href="#s-h-over">Overview</a><a href="#s-h-find">Findings</a><a href="#s-h-sim">What if</a><a href="#s-h-score">Score</a><a href="#s-h-lim">Limits</a></nav>

  <section class="panel" aria-labelledby="s-h-over">
    <div class="panel-head"><h2 id="s-h-over">Your flat in numbers</h2>${badge("measured", "Measured")}</div>
    <div id="s-over"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-hist">
    <div class="panel-head"><h2 id="s-h-hist">When your flat uses electricity</h2>${badge("measured", "Measured")}</div>
    <p class="lead">Average use per hour of the day (Stockholm time), with the expensive peak hours marked.</p>
    <div id="s-hours"></div>
    <div class="subhead big">Day by day</div>
    <div id="s-days"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-ch">
    <div class="panel-head"><h2 id="s-h-ch">By appliance channel</h2>${badge("measured", "Measured")}</div>
    <p class="lead">Seven channels per flat. The appliance names are inferred from how each channel uses power (*).</p>
    <div id="s-channels"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-tariff">
    <div class="panel-head"><h2 id="s-h-tariff">Your electricity contract</h2></div>
    <p class="lead">The contract changes what a saving is worth in SEK. It never changes kWh or emissions.</p>
    ${tariffSelectorHtml("s", state.tariff)}
  </section>

  <h2 class="section-title" id="s-h-find">What the data found</h2>
  <p class="lead">Each finding states its evidence, who can act on it, and what acting on it could change. \u201CPossible\u201D and \u201Cconsistent pattern\u201D mean a statistical test was met. Nothing here is confirmed until a person checks it.</p>
  <div id="s-digest"></div>
  <section class="cards" id="s-findings" aria-labelledby="s-h-find"></section>

  <section class="panel" aria-labelledby="s-h-sim">
    <div class="panel-head"><h2 id="s-h-sim">What if\u2026</h2>${badge("simulated", "Simulated by the engine")}</div>
    <p class="lead">Pick a change. The engine recalculates your flat hour by hour and returns the result, including your score.</p>
    <div id="s-sim"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-score">
    <div class="panel-head"><h2 id="s-h-score">Your sustainability score</h2>${badge("measured", "From the engine")}</div>
    <div id="s-score"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-notes">
    <div class="panel-head"><h2 id="s-h-notes">Notifications</h2></div>
    <div id="s-notes"></div>
  </section>

  <section class="panel" aria-labelledby="s-h-lim">
    <div class="panel-head"><h2 id="s-h-lim">Before you rely on a number</h2></div>
    <div class="limits">${LIMITATIONS.map((l) => `<div class="limit"><h3>${esc(l.title)}</h3><p>${esc(l.body)}</p></div>`).join("")}</div>
  </section>`;
    const A = api();
    let findings = [];
    let texts = /* @__PURE__ */ new Map();
    let sim = null;
    void loadInto($("#s-meta"), "flat details", () => A.flats(), (fl) => {
      const f = fl.find((x) => x.flat_id === flatId);
      return f ? `Viewing <b>${esc(f.flat_id)}</b> \xB7 ${esc(String(f.residents))} residents \xB7 ${esc(String(f.floor_area_m2))} m\xB2 \xB7 price area ${esc(f.price_area)} \xB7 1\u201328 Oct 2026 (synthetic data)` : errorHtml(new Error("unknown flat"), "this flat");
    });
    void loadInto($("#s-over"), "consumption", () => A.breakdown(flatId), overviewHtml);
    void loadInto($("#s-channels"), "the channel breakdown", () => A.breakdown(flatId), (b) => channelBars(b.channels) + '<p class="note">* Inferred, not measured: the dataset has no appliance labels. Missing readings are shown per channel.</p>');
    void loadInto($("#s-hours"), "the hourly profile", () => A.profile(flatId), (p) => hourOfDayChart(p));
    void loadInto($("#s-days"), "daily use", () => A.profile(flatId), (p) => dailyChart(p));
    void loadInto($("#s-score"), "your score", () => A.scores(flatId), (s) => scoreHtml(s));
    void loadInto(
      $("#s-notes"),
      "notifications",
      () => A.flatNotifications(flatId),
      (n) => n.length ? `<ul class="plain">${n.map((x) => `<li>${esc(x.text)}</li>`).join("")}</ul>` : emptyHtml("No notifications.")
    );
    $("#s-digest").innerHTML = "";
    const findingsEl = $("#s-findings");
    const renderFindings = () => {
      findingsEl.innerHTML = findings.length ? findings.map((f) => findingCard(f, { audience: "student", tariff: state.tariff, text: texts.get(f.id), actionsHtml: reportForm(f) })).join("") : emptyHtml("No patterns were detected for your flat. That is good news.");
    };
    void (async () => {
      findingsEl.innerHTML = loadingHtml("findings");
      const simEl = $("#s-sim");
      simEl.innerHTML = loadingHtml("the simulator");
      try {
        findings = await A.findings(flatId);
      } catch (e) {
        findingsEl.innerHTML = errorHtml(e, "findings");
        simEl.innerHTML = errorHtml(e, "the simulator");
        return;
      }
      try {
        texts = await studentFindingTexts(A, flatId);
      } catch {
        texts = /* @__PURE__ */ new Map();
      }
      renderFindings();
      let options;
      try {
        options = await A.interventions();
      } catch (e) {
        simEl.innerHTML = errorHtml(e, "the simulator");
        return;
      }
      const deps = { api: A, flatId, findings, options, tariff: () => state.tariff };
      simEl.innerHTML = simulatorHtml(deps);
      sim = bindSimulator(simEl, deps);
    })();
    bindTariffSelector("s", root, (t) => {
      setTariff(t);
      if (findings.length) renderFindings();
    });
    root.addEventListener("click", (e) => {
      const b = e.target.closest("[data-sim]");
      if (b && sim) sim.select(b.dataset.sim ?? "");
    });
    root.addEventListener("submit", async (e) => {
      const form = e.target.closest("form[data-report]");
      if (!form) return;
      e.preventDefault();
      const id = form.dataset.report ?? "";
      const status = form.querySelector(".form-status");
      const btn = form.querySelector("button[type=submit]");
      const msg = form.querySelector("textarea")?.value.trim() || null;
      if (btn) btn.disabled = true;
      if (status) status.textContent = "Sending\u2026";
      try {
        const r = await A.report(flatId, id, msg);
        if (status) status.textContent = `Sent to the building manager (report ${r.id}).`;
      } catch (err) {
        if (status) status.textContent = `Not sent: ${errorMessage(err)}`;
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  }
  function scoreHtml(s) {
    return `${lensPanel(s.lenses.resident, "resident")}
    <div id="s-score-text">${textCard({ kind: "score_explanation", audience: "student", state: "unavailable", source: "none", text: "", note: "AI explanations of the score are not connected yet. The pillar notes above describe how each part is calculated." })}</div>
    ${details("Apartment score (includes possible equipment faults you are not scored on)", lensPanel(s.lenses.apartment, "apartment"))}
    ${scoreDetails(s)}
    ${kv([["Measured over", esc(s.horizon)]])}`;
  }

  // src/main.ts
  function renderUserArea() {
    const area = $("#user-area");
    const s = state.session;
    if (!s) {
      area.innerHTML = "";
      return;
    }
    const who = s.role === "student" ? `Student \xB7 ${s.flatId}` : `Manager \xB7 ${s.email}`;
    area.innerHTML = `<span class="who" title="${esc(who)}">${esc(who)}</span><button class="tab" id="signout" type="button">Sign out</button>`;
    $("#signout").addEventListener("click", signOut);
  }
  function render() {
    const root = $("#app");
    const s = state.session;
    renderUserArea();
    if (!s) {
      document.title = "Watt Wise \xB7 Sign in";
      mountLogin(root, signIn, async () => (await state.api.flats()).map((f) => f.flat_id));
      return;
    }
    if (s.role === "student") {
      document.title = "Watt Wise \xB7 Student view";
      mountStudent(root, s.flatId);
    } else {
      document.title = "Watt Wise \xB7 Manager view";
      mountManager(root);
    }
  }
  function signIn(session) {
    state.session = session;
    saveSession(session);
    render();
    $("#app").focus();
    window.scrollTo(0, 0);
  }
  function signOut() {
    clearSession();
    state.session = null;
    render();
    window.scrollTo(0, 0);
  }
  state.config = resolveConfig(window.WATTWISE_CONFIG, window.location.search);
  state.api = createApi(state.config, () => state.session?.role === "student" ? state.session.flatId : null);
  var src = document.getElementById("data-source");
  if (src) {
    src.textContent = `Data: ${state.api.describe}`;
    if (state.api.mode === "mock") {
      void state.api.meta().then(
        (m) => src.textContent = `Data: offline fixtures recorded from the real engine (references ${m.references_hash})`,
        () => src.textContent = "Data: offline fixtures could not be loaded"
      );
    }
  }
  state.session = loadSession();
  render();
})();
