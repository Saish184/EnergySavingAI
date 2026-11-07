"use strict";
(() => {
  // src/data.ts
  var FLATS = [
    { id: "F001", residents: 2, areaM2: 56 },
    { id: "F002", residents: 3, areaM2: 69 },
    { id: "F003", residents: 4, areaM2: 82 },
    { id: "F004", residents: 2, areaM2: 56 },
    { id: "F005", residents: 5, areaM2: 95 },
    { id: "F006", residents: 3, areaM2: 69 },
    { id: "F007", residents: 4, areaM2: 82 },
    { id: "F008", residents: 2, areaM2: 56 }
  ];

  // src/auth.ts
  var DEMO_MODE = true;
  var STORAGE_KEY = "wattwise.session";
  var MIN_PASSWORD_LENGTH = 8;
  function parseFlatNumber(input) {
    const m = /^\s*f?\s*0*(\d{1,3})\s*$/i.exec(input);
    if (!m) return null;
    const id = `F${m[1].padStart(3, "0")}`;
    return FLATS.some((f) => f.id === id) ? id : null;
  }
  function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  }
  function loginStudent(input) {
    if (input.trim() === "") return { ok: false, message: "Enter your flat number." };
    const flatId = parseFlatNumber(input);
    if (!flatId) {
      const first = FLATS[0].id;
      const last = FLATS[FLATS.length - 1].id;
      return { ok: false, message: `We could not find that flat. Try a number like 3 or F003 (${first} to ${last}).` };
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
      if (d.role === "student" && typeof d.flatId === "string" && FLATS.some((f) => f.id === d.flatId)) {
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
  var fmt = {
    num(n, digits = 0) {
      return n.toLocaleString("en-GB", { minimumFractionDigits: digits, maximumFractionDigits: digits });
    },
    /** Signed number with a real minus sign. Rounds -0.0 to 0.0. */
    signed(n, digits = 1) {
      const r = Number(n.toFixed(digits));
      if (r === 0) return fmt.num(0, digits);
      return (r > 0 ? "+" : "\u2212") + fmt.num(Math.abs(r), digits);
    },
    hour(h) {
      return String(h).padStart(2, "0");
    }
  };

  // src/login.ts
  function setError(input, box, message) {
    box.textContent = message;
    if (message) input.setAttribute("aria-invalid", "true");
    else input.removeAttribute("aria-invalid");
  }
  function mountLogin(root, onLogin) {
    const first = FLATS[0].id;
    const last = FLATS[FLATS.length - 1].id;
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
          <div class="hint" id="l-flat-hint">Flats run from ${first} to ${last}.</div>
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

      ${DEMO_MODE ? `<p class="demo-note"><strong>Demo mode.</strong> There are no real accounts. Any well-formed email and a password of ${MIN_PASSWORD_LENGTH}+ characters will sign you in as a manager. A real version needs a server to check passwords.</p>` : ""}
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
    studentForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const result = loginStudent(flatInput.value);
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

  // src/api.ts
  var API_BASE = window.WATT_API ?? (location.protocol.startsWith("http") && location.port === "8000" ? location.origin : "http://localhost:8000");
  async function req(path, init = {}, flatId) {
    const headers = { "Content-Type": "application/json" };
    if (flatId) headers["X-Flat-Id"] = flatId;
    const r = await fetch(API_BASE + path, { ...init, headers });
    if (!r.ok) {
      let detail = r.statusText;
      try {
        detail = (await r.json()).detail ?? detail;
      } catch {
      }
      throw new Error(`${r.status}: ${detail}`);
    }
    return r.json();
  }
  var api = {
    health: () => req("/health"),
    llmStatus: () => req("/llm/status"),
    scores: (f) => req(`/flats/${f}/scores`, {}, f),
    breakdown: (f) => req(`/flats/${f}/breakdown`, {}, f),
    findings: (f) => req(`/flats/${f}/findings`, {}, f),
    digest: (f) => req(`/flats/${f}/digest`, {}, f),
    report: (f, fid) => req(`/flats/${f}/findings/${fid}/report`, { method: "POST", body: JSON.stringify({ message: "Reported from Watt Wise" }) }, f),
    scenario: (f, anomalyId, adoption, tariff) => req(`/flats/${f}/scenarios`, {
      method: "POST",
      body: JSON.stringify({
        scenario: "apply_interventions",
        params: { items: [{ anomaly_id: anomalyId, params: { adoption } }], tariff: { type: tariff } }
      })
    }, f),
    portfolio: () => req("/portfolio"),
    portfolioFindings: () => req("/portfolio/findings"),
    portfolioSummary: () => req("/portfolio/summary"),
    workorders: () => req("/workorders"),
    openWorkorder: (fid) => req("/workorders", { method: "POST", body: JSON.stringify({ finding_id: fid }) }),
    patchWorkorder: (id, body) => req(`/workorders/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
    verify: (id) => req(`/workorders/${id}/verify`, { method: "POST", body: JSON.stringify({ simulate: true }) })
  };

  // src/ui.ts
  function badge(kind, text, title = "") {
    return `<span class="badge ${kind}"${title ? ` title="${esc(title)}"` : ""}>${esc(text)}</span>`;
  }
  var TARIFF_LABEL = {
    hourly_spot: "Hourly spot price",
    monthly_average_spot: "Monthly average price",
    included_in_rent: "Included in rent"
  };
  function statusChip(f) {
    const cls = f.status === "VERIFIED" ? "ok" : f.status === "DISMISSED" ? "muted" : f.responsibility === "manager" ? "hypothesis" : "projected";
    return badge(cls, f.wording, `status ${f.status}`);
  }
  var RESP_LABEL = {
    manager: "Building manager",
    resident: "Residents",
    unknown: "Needs confirmation"
  };
  function textMeta(t) {
    if (!t) return "";
    const src = t.source === "llm" ? badge("ai", `AI \xB7 ${t.provider ?? ""}`) : t.source === "template" ? badge("muted", "Watt Wise wording") : t.source === "safe" ? badge("provisional", "Short version") : badge("placeholder", "Text unavailable");
    const ok = t.validation?.passed ? badge("data", "\u2713 Numbers checked against the engine") : "";
    return `<div class="meta">${src}${ok}</div>`;
  }
  function claimsDetails(t) {
    if (!t?.claims?.length) return "";
    const rows = t.claims.map((c) => {
      const v = Array.isArray(c.value) ? c.value.map((x) => fmt.num(Number(x), 2)).join(" \u2013 ") : typeof c.value === "number" ? fmt.num(c.value, 2) : esc(String(c.value));
      return `<tr><td class="num">${v} <span class="unit">${esc(c.unit)}</span></td><td>${esc(c.category.replace(/_/g, " "))}</td><td>${esc(c.period ?? "")}</td><td><code>${esc(c.source)}</code></td></tr>`;
    }).join("");
    return `<details class="claims"><summary>Where these numbers come from</summary>
    <div class="table-wrap"><table class="data mini"><thead><tr><th>Value</th><th>Kind</th><th>Period</th><th>Engine field</th></tr></thead><tbody>${rows}</tbody></table></div></details>`;
  }
  function scoreRing(score, band, size = 148) {
    const r = 58, c = 2 * Math.PI * r, p = Math.max(0, Math.min(100, score)) / 100;
    return `<div class="ring" style="width:${size}px;height:${size}px" role="img" aria-label="Score ${fmt.num(score)} of 100, band ${esc(band)}">
    <svg viewBox="0 0 140 140" width="${size}" height="${size}">
      <circle cx="70" cy="70" r="${r}" class="ring-bg"/>
      <circle cx="70" cy="70" r="${r}" class="ring-fg" stroke-dasharray="${(c * p).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 70 70)"/>
    </svg>
    <div class="ring-txt"><b>${fmt.num(score)}</b><span class="band band-${esc(band)}">${esc(band)}</span></div></div>`;
  }
  var PILLAR_LABEL = { use: "Use", waste: "Waste", timing: "Timing", health: "Health" };
  var PILLAR_HINT = {
    use: "electricity compared with the most efficient flats",
    waste: "possible avoidable use the engine found",
    timing: "flexible appliances in peak-price hours",
    health: "possible equipment faults (not your score)"
  };
  function pillarRows(p) {
    return Object.entries(p).map(([k, v]) => `<div class="pillar">
      <div class="pillar-name">${esc(PILLAR_LABEL[k] ?? k)}<span>${esc(PILLAR_HINT[k] ?? "")}</span></div>
      <div class="track"><i style="width:${Math.max(2, v)}%" class="${v >= 80 ? "hi" : v >= 55 ? "mid" : "lo"}"></i></div>
      <div class="pillar-val">${fmt.num(v)}</div></div>`).join("");
  }
  function kpi(label, value, sub = "", tone = "") {
    return `<div class="kpi ${tone}"><div class="kpi-label">${esc(label)}</div><div class="kpi-val">${value}</div>${sub ? `<div class="kpi-sub">${sub}</div>` : ""}</div>`;
  }
  function dailyBars(daily) {
    const max = Math.max(...daily.map((d) => d.kwh), 1e-9);
    const bars = daily.map((d) => {
      const dt = /* @__PURE__ */ new Date(d.day + "T12:00:00Z");
      const we = dt.getUTCDay() === 0 || dt.getUTCDay() === 6;
      return `<div class="dbar${we ? " we" : ""}" style="height:${Math.max(3, d.kwh / max * 100)}%" title="${esc(d.day)}: ${fmt.num(d.kwh, 1)} kWh"></div>`;
    }).join("");
    return `<div class="dbars" role="img" aria-label="Electricity per day">${bars}</div>
    <div class="dlabels"><span>${esc(daily[0]?.day ?? "")}</span><span>${esc(daily[daily.length - 1]?.day ?? "")}</span></div>`;
  }
  function moneyFor(f, tariff) {
    const v = f.valuation.sek_by_tariff[tariff];
    if (v == null) return "\u2013";
    return `${fmt.num(v, 1)} SEK`;
  }
  function skeleton() {
    return `<div class="skel"><div></div><div></div><div></div></div>`;
  }
  function errorBox(e) {
    return `<div class="panel errbox"><h2>Can\u2019t reach the Watt Wise engine</h2><p>${esc(String(e?.message ?? e))}</p>
    <p class="note">Start it with <code>cd backend &amp;&amp; uvicorn app.api.main:app --port 8000</code>, then reload.</p></div>`;
  }

  // src/manager.ts
  var filter = "maintenance";
  function bandPill(score, band) {
    return `<span class="sc"><b>${fmt.num(score)}</b><span class="band band-${esc(band)}">${esc(band)}</span></span>`;
  }
  function flatsTable(p) {
    const max = Math.max(...p.flats.map((r) => r.kwh_28d));
    const row = (r) => `<tr>
    <th scope="row">${esc(r.flat_id)}<span class="unit"> \xB7 ${r.residents} res \xB7 ${r.floor_area_m2} m\xB2</span></th>
    <td>${bandPill(r.apartment_score, r.apartment_band)}</td>
    <td>${bandPill(r.resident_score, r.resident_band)}</td>
    <td><div class="inline-bar"><span style="width:${Math.max(2, r.health)}%" class="${r.health < 90 ? "warnbar" : ""}"></span></div>${fmt.num(r.health)}</td>
    <td><div class="inline-bar"><span style="width:${r.kwh_28d / max * 100}%"></span></div>${fmt.num(r.kwh_28d)} kWh</td>
    <td>${fmt.num(r.comparison.kwh_per_m2, 2)}</td>
    <td>${r.open_findings}${r.open_manager_findings ? ` <span class="badge hypothesis">${r.open_manager_findings} equipment</span>` : ""}</td>
    <td>${r.combined_potential ? `${fmt.num(r.combined_potential.kwh, 1)} kWh` : "\u2013"}</td></tr>`;
    return `<div class="table-wrap"><table class="data">
    <caption>Apartment Performance includes possible equipment faults; Resident Actions does not. Bands A\u2013G.</caption>
    <thead><tr><th>Flat</th><th>Apartment</th><th>Resident</th><th>Health</th><th>Use \xB7 28 d</th><th>kWh / m\xB2</th><th>Open findings</th><th>Combined potential</th></tr></thead>
    <tbody>${[...p.flats].sort((a, b) => a.apartment_rank - b.apartment_rank).map(row).join("")}</tbody></table></div>`;
  }
  function woControls(f, w) {
    if (!f.triage?.maintenance) return `<span class="note">No technician needed: ${esc(f.triage?.reason ?? "")}</span>`;
    if (!w) return `<button class="btn-sm primary" data-open="${esc(f.id)}">Open work order</button>`;
    const steps = ["open", "sent", "repaired"];
    const prog = `<ol class="steps">${steps.map((s) => `<li class="${steps.indexOf(w.status) >= steps.indexOf(s) ? "done" : ""}">${s}</li>`).join("")}</ol>`;
    const btn = (label, body, cls = "") => `<button class="btn-sm ${cls}" data-wo="${esc(w.id)}" data-body='${esc(JSON.stringify(body))}'>${label}</button>`;
    let b = "";
    if (w.status === "closed_no_fault") return `${badge("muted", "Closed: no fault found")}`;
    if (w.status === "open") b += btn("Mark sent", { status: "sent" });
    if ((w.status === "open" || w.status === "sent") && w.fault_found == null)
      b += btn("Technician: fault found", { fault_found: true }, "primary") + btn("No fault", { fault_found: false });
    if (w.status === "sent") b += btn("Mark repaired", { status: "repaired" });
    if (w.status === "repaired") b += `<button class="btn-sm primary" data-verify="${esc(w.id)}">Verify (simulated data)</button>`;
    return `<div class="wo"><span class="badge owner">${esc(w.id)}</span>${prog}${b}</div>`;
  }
  function mCard(f, w) {
    const t = f.manager_text, o = t?.output;
    const a = f.avoidable_28d;
    return `<article class="fcard resp-${f.responsibility}">
    <div class="fcard-top"><div><h3>${esc(o?.headline ?? `${f.flat_id} \xB7 ${f.title}`)}</h3>
      <div class="chips">${statusChip(f)}${badge("owner", RESP_LABEL[f.responsibility])}
      ${f.triage?.maintenance ? badge("hypothesis", `maintenance \xB7 ${f.triage.priority}`) : badge("muted", "not maintenance")}</div></div>
      <div class="fig-mini">${a.kind === "shift" ? `${fmt.num(f.quantities.kwh_moved, 1)} kWh moved` : `${fmt.num(a.kwh, 1)} kWh`}<span>${fmt.num(a.sek, 1)} SEK if hourly \xB7 ${fmt.num(a.window_days)} d</span></div></div>
    <p class="fbody">${esc(o?.summary ?? "")}</p>
    ${o?.evidence_points?.length ? `<ul class="evidence">${o.evidence_points.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
    ${o?.suggested_check ? `<p class="faction"><b>Check:</b> ${esc(o.suggested_check)}</p>` : ""}
    <div class="factions">${woControls(f, w)}${textMeta(t)}</div>
    ${claimsDetails(t)}
  </article>`;
  }
  function summaryPanel(p, s) {
    const o = s.output, st = p.evidence_quality.findings_by_status;
    return `<section class="hero-grid">
    <div class="panel"><div class="eyebrow">Portfolio \xB7 28 days</div><h2>${esc(o?.headline ?? "Portfolio")}</h2>
      <ul class="digest-list">${(o?.bullets ?? []).map((b) => `<li>${esc(b)}</li>`).join("")}</ul>
      <p class="encourage">${esc(o?.maintenance_note ?? "")}</p>${textMeta(s)}</div>
    <div class="panel"><div class="kpis col2">
      ${kpi("Measured use", `${fmt.num(p.totals.kwh)} kWh`, `${fmt.num(p.totals.sek)} SEK spot \xB7 ${fmt.num(p.totals.co2_kg)} kg CO\u2082e`)}
      ${kpi("Simulated potential", `${fmt.num(p.potential.kwh, 1)} kWh`, `${fmt.num(p.potential.sek_if_hourly_spot)} SEK if hourly spot \xB7 not verified`, "good")}
      ${Object.entries(st).map(([k, v]) => kpi(k.toLowerCase(), String(v), "findings")).join("")}
    </div><p class="note">${esc(p.evidence_quality.note)}</p></div></section>`;
  }
  async function mountManager(root) {
    root.innerHTML = `<section class="hero"><div class="hero-text"><div class="eyebrow">Manager view</div>
    <h1>The whole portfolio, with its caveats.</h1><p>Which flats perform, which equipment needs a technician, and what is only a behaviour pattern for residents.</p></div></section>
    <div id="m-body">${skeleton()}</div>`;
    await refresh();
  }
  async function refresh() {
    const body = $("#m-body");
    try {
      const [p, fs, s, wo] = await Promise.all([api.portfolio(), api.portfolioFindings(), api.portfolioSummary(), api.workorders()]);
      const shown = fs.filter((f) => filter === "all" || (filter === "maintenance" ? f.triage?.maintenance : !f.triage?.maintenance));
      const tab = (id, label, n) => `<button class="tab" data-filter="${id}" aria-pressed="${filter === id}">${label} <span class="count">${n}</span></button>`;
      body.innerHTML = `${summaryPanel(p, s)}
      <section class="panel"><div class="panel-head"><h2>Flats</h2>${badge("data", "Engine scores \xB7 frozen references")}</div>${flatsTable(p)}</section>
      <div class="section-head"><h2 class="section-title">Findings</h2><div class="seg">
        ${tab("maintenance", "Maintenance", fs.filter((f) => f.triage?.maintenance).length)}
        ${tab("behaviour", "Residents", fs.filter((f) => !f.triage?.maintenance).length)}${tab("all", "All", fs.length)}</div></div>
      <section class="fcards">${shown.map((f) => mCard(f, wo.find((w) => w.finding_id === f.id))).join("") || '<div class="panel">None.</div>'}</section>
      <p class="disclaimer">${esc(fs[0]?.manager_text?.disclaimer ?? "")}</p>`;
      body.querySelectorAll("[data-filter]").forEach((b) => b.addEventListener("click", () => {
        filter = b.dataset.filter;
        void refresh();
      }));
      body.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => act(b, () => api.openWorkorder(b.dataset.open))));
      body.querySelectorAll("[data-wo]").forEach((b) => b.addEventListener("click", () => act(b, () => api.patchWorkorder(b.dataset.wo, JSON.parse(b.dataset.body)))));
      body.querySelectorAll("[data-verify]").forEach((b) => b.addEventListener("click", () => act(b, async () => {
        const r = await api.verify(b.dataset.verify);
        alert(`Verification with SIMULATED data: ${r.verification.status}
${r.verification.reason}`);
      })));
    } catch (e) {
      body.innerHTML = errorBox(e);
    }
  }
  async function act(b, fn) {
    b.disabled = true;
    try {
      await fn();
      await refresh();
    } catch (e) {
      alert(String(e.message));
      b.disabled = false;
    }
  }

  // src/state.ts
  var state = {
    session: null,
    flatId: "F001",
    tariff: "hourly_spot"
  };

  // src/student.ts
  var TYPE_ICON = {
    fault_step_change: "\u2744",
    base_load_outlier: "\u23FB",
    scheduled_block: "\u23F1",
    heater_pattern: "\u2668",
    peak_usage: "\u21E5"
  };
  function findingCard(f) {
    const t = f.student_text, o = t?.output;
    const a = f.avoidable_28d, shift = a.kind === "shift";
    const proj = f.projection_annual.sek;
    const cta = o?.cta === "report" ? `<button class="btn-sm primary" data-report="${esc(f.id)}">Report to manager</button>` : o?.cta === "confirm" ? `<button class="btn-sm" data-confirm="${esc(f.id)}">Confirm what it is</button>` : o?.cta === "try" ? `<button class="btn-sm" data-try="${esc(f.id)}">Try it in the calculator</button>` : "";
    return `<article class="fcard resp-${f.responsibility}">
    <div class="fcard-top"><span class="ficon" aria-hidden="true">${TYPE_ICON[f.type] ?? "\u2022"}</span>
      <div><h3>${esc(o?.headline ?? f.title)}</h3>
      <div class="chips">${statusChip(f)}${badge("placeholder", `${f.assumed_type} (assumed)`)}${badge("owner", RESP_LABEL[f.responsibility])}</div></div></div>
    <p class="fbody">${esc(o?.explanation ?? "")}</p>
    ${o?.action ? `<p class="faction"><b>Try this:</b> ${esc(o.action)}</p>` : ""}
    ${o?.question ? `<p class="fq">${esc(o.question)}</p>` : ""}
    <div class="figures">
      ${shift ? kpi("Moved to cheaper hours", `${fmt.num(f.quantities.kwh_moved, 1)} kWh`, "same energy, other time") : kpi("Could be saved", `${fmt.num(a.kwh, 1)} kWh`, `over ${fmt.num(a.window_days)} days \xB7 if followed fully`)}
      ${kpi(TARIFF_LABEL[state.tariff], moneyFor(f, state.tariff), "spot-energy part only")}
      ${kpi("CO\u2082e", `${fmt.num(a.co2_kg, 2)} kg`, "synthetic factor")}
      ${kpi(
      "Yearly",
      proj.value != null ? `${fmt.num(proj.low ?? 0)}\u2013${fmt.num(proj.high ?? 0)} SEK` : "not projected",
      proj.value != null ? "projection, if hourly spot" : "depends on weather / prices"
    )}
    </div>
    <div class="factions">${cta}${textMeta(t)}</div>
    ${claimsDetails(t)}
    <details class="claims"><summary>Evidence</summary><p class="note">${esc(f.evidence.text)}</p><p class="note">${esc(f.counts_as)} \xB7 ${esc(f.valuation.label)}</p></details>
  </article>`;
  }
  function hero(sc, ex, dg) {
    const r = sc.lenses.resident, a = sc.lenses.apartment;
    const e = ex?.output, d = dg.output;
    return `<section class="hero-grid">
    <div class="panel score-panel">
      <div class="eyebrow">Resident Actions score</div>
      <div class="score-row-top">${scoreRing(r.score, r.band)}
        <div class="score-side"><p class="score-sum">${esc(e?.summary ?? "")}</p>
        ${e?.next_step ? `<p class="next"><b>Next step:</b> ${esc(e.next_step)}</p>` : ""}
        <p class="note">Rank ${fmt.num(r.rank)} of ${r.of} \xB7 ${fmt.num(r.sensitivity.score_p5)}\u2013${fmt.num(r.sensitivity.score_p95)} with other weightings</p></div></div>
      <div class="pillars">${pillarRows(r.pillars)}</div>
      <p class="note">Not counted for you: ${esc(r.excludes.join("; "))}. Whole-flat score incl. equipment: <b>${fmt.num(a.score)} ${esc(a.band)}</b>.</p>
      ${textMeta(ex)}
    </div>
    <div class="panel digest">
      <div class="eyebrow">Your 28 days</div>
      <h2>${esc(d?.headline ?? "Overview")}</h2>
      <ol class="digest-list">${(d?.bullets ?? []).map((b) => `<li>${esc(b)}</li>`).join("")}</ol>
      <p class="encourage">${esc(d?.encouragement ?? "")}</p>
      ${textMeta(dg)}
    </div>
  </section>`;
  }
  function usage(b) {
    const max = Math.max(...b.channels.map((c) => c.kwh));
    return `<section class="panel">
    <div class="panel-head"><h2>Where your electricity went</h2>${badge("data", "Measured \xB7 1\u201328 Oct")}</div>
    <div class="kpis">${kpi("Electricity", `${fmt.num(b.totals.kwh)} kWh`, "28 days")}${kpi("Spot cost", `${fmt.num(b.totals.sek)} SEK`, "excl. VAT and fees")}
      ${kpi("CO\u2082e", `${fmt.num(b.totals.co2_kg, 1)} kg`)}${kpi("In peak hours", `${fmt.num(b.totals.peak_share * 100)} %`, "share of kWh")}
      ${kpi("Per resident", `${fmt.num(b.totals.kwh_per_resident)} kWh`, "flat average")}</div>
    <div class="two-col">
      <div><div class="subhead">Per day</div>${dailyBars(b.daily)}<p class="note">Darker bars are weekends.</p></div>
      <div><div class="subhead">By appliance (types are assumptions)</div>
        ${b.channels.map((c) => `<div class="chrow"><span>${esc(c.assumed_type)}</span><div class="chtrack"><div class="chfill" style="width:${c.kwh / max * 100}%"></div></div><span class="chval">${fmt.num(c.kwh, 1)} kWh</span></div>`).join("")}</div>
    </div></section>`;
  }
  function calculator(fs) {
    if (!fs.length) return "";
    return `<section class="panel calc" id="calc">
    <div class="panel-head"><h2>What if?</h2>${badge("projected", "Simulated by the engine \xB7 not verified")}</div>
    <p class="lead">Pick a finding and how much of the change you would really do. The engine re-runs the numbers; nothing here is calculated in the browser.</p>
    <div class="calc-row">
      <label class="field-inline">Finding<select id="c-f">${fs.map((f) => `<option value="${esc(f.id)}">${esc(f.title)} \xB7 ${esc(f.assumed_type)}</option>`).join("")}</select></label>
      <label class="field-inline">How much you\u2019d do: <b id="c-a-l">100 %</b><input id="c-a" type="range" min="10" max="100" step="10" value="100"></label>
    </div>
    <div id="c-out" class="calc-out">${skeleton()}</div></section>`;
  }
  async function runCalc() {
    const out = $("#c-out");
    const fid = $("#c-f").value, adoption = Number($("#c-a").value) / 100;
    out.classList.add("busy");
    try {
      const r = await api.scenario(state.flatId, fid, adoption, state.tariff);
      const d = r.delta_28d, sek = r.valuation.sek_by_tariff[state.tariff];
      const b = r.before.resident.score, a = r.after.resident.score;
      out.innerHTML = `<div class="kpis">
      ${r.kind === "shift" ? kpi("Energy", "unchanged", "a shift moves use, it does not cut it") : kpi("Energy", `${fmt.num(-d.kwh, 1)} kWh less`, `over ${fmt.num(r.window.days)} days`, "good")}
      ${kpi(TARIFF_LABEL[state.tariff], sek == null ? "\u2013" : `${fmt.num(sek, 1)} SEK`, "spot-energy part only", "good")}
      ${kpi("CO\u2082e", `${fmt.num(-d.co2_kg, 2)} kg less`)}
      ${kpi("Your score", `${fmt.num(b)} \u2192 <b>${fmt.num(a)}</b>`, `${esc(r.before.resident.band)} \u2192 ${esc(r.after.resident.band)}`, a > b ? "good" : "")}
    </div><p class="note">Potential if you do ${fmt.num(adoption * 100)} % of it. A real saving needs measured data afterwards.</p>`;
    } catch (e) {
      out.innerHTML = `<p class="error">${esc(String(e.message))}</p>`;
    } finally {
      out.classList.remove("busy");
    }
  }
  async function mountStudent(root) {
    const f = state.flatId;
    root.innerHTML = `<section class="hero"><div class="hero-text"><div class="eyebrow">Student view \xB7 ${esc(f)}</div>
    <h1>Your flat, in plain numbers.</h1><p>What your flat used, what the engine noticed, and what a small change could do. Every number is checked.</p></div>
    <div class="picker"><label class="picker-label" for="s-tariff">Your electricity contract</label>
    <select id="s-tariff">${Object.keys(TARIFF_LABEL).map((t) => `<option value="${t}" ${t === state.tariff ? "selected" : ""}>${TARIFF_LABEL[t]}</option>`).join("")}</select></div></section>
    <div id="s-body">${skeleton()}</div>`;
    $("#s-tariff").addEventListener("change", (e) => {
      state.tariff = e.target.value;
      void mountStudent(root);
    });
    try {
      const [sc, fs, dg, bd] = await Promise.all([api.scores(f), api.findings(f), api.digest(f), api.breakdown(f)]);
      $("#s-body").innerHTML = `${hero(sc, sc.explainer, dg)}
      <h2 class="section-title">What the engine noticed <span class="count">${fs.length}</span></h2>
      <p class="lead">Each card says how sure we are, who can act, and what it could be worth on <b>your</b> contract.</p>
      <section class="fcards">${fs.length ? fs.map(findingCard).join("") : '<div class="panel">Nothing unusual found for your flat. Nice.</div>'}</section>
      ${calculator(fs)}${usage(bd)}
      <p class="disclaimer">${esc(fs[0]?.student_text?.disclaimer ?? "")}</p>`;
      root.querySelectorAll("[data-report]").forEach((b) => b.addEventListener("click", async () => {
        b.disabled = true;
        try {
          await api.report(f, b.dataset.report);
          b.textContent = "Reported \u2713";
        } catch {
          b.textContent = "Could not report";
        }
      }));
      root.querySelectorAll("[data-confirm]").forEach((b) => b.addEventListener("click", () => {
        b.textContent = "Thanks, noted";
        b.disabled = true;
      }));
      root.querySelectorAll("[data-try]").forEach((b) => b.addEventListener("click", () => {
        $("#c-f").value = b.dataset.try;
        void runCalc();
        $("#calc").scrollIntoView({ behavior: "smooth" });
      }));
      if (fs.length) {
        $("#c-f").addEventListener("change", () => void runCalc());
        let t = 0;
        $("#c-a").addEventListener("input", (e) => {
          $("#c-a-l").textContent = `${e.target.value} %`;
          clearTimeout(t);
          t = window.setTimeout(() => void runCalc(), 250);
        });
        void runCalc();
      }
    } catch (e) {
      $("#s-body").innerHTML = errorBox(e);
    }
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
      mountLogin(root, signIn);
      return;
    }
    if (s.role === "student") {
      document.title = "Watt Wise \xB7 Student view";
      mountStudent(root);
    } else {
      document.title = "Watt Wise \xB7 Manager view";
      mountManager(root);
    }
  }
  function signIn(session) {
    state.session = session;
    if (session.role === "student") state.flatId = session.flatId;
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
  var saved = loadSession();
  if (saved) {
    state.session = saved;
    if (saved.role === "student") state.flatId = saved.flatId;
  }
  render();
})();
