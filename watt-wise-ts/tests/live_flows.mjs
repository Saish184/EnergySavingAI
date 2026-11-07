// Live-mode flows against a FRESH backend (state-changing):  make api   then   npm run live-flows
// Checks: work-order lifecycle reaches the backend and survives a reload; backend outage shows an error, never numbers;
// student mobile and manager desktop layouts render.
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const API = process.env.LIVE_API ?? 'http://localhost:8000';
const APP = `${API}/app/`;
const results = [];
const check = (name, cond, extra = '') => {
  results.push(!!cond);
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? `  (${extra})` : ''}`);
};
const j = async (path) => (await fetch(API + path)).json();

const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
p.on('pageerror', (e) => errors.push(e.message));

// --- manager work-order lifecycle (technician outcome) ---
await p.goto(APP);
await p.evaluate(() => sessionStorage.setItem('wattwise.session', JSON.stringify({ role: 'manager', email: 'm@example.se' })));
await p.reload();
const card = '#finding-FS-F002-A01';
await p.waitForSelector(`${card} [data-wo-create]`);
await p.click(`${card} [data-wo-create]`);
await p.waitForSelector(`${card} .wo [data-wo-action]`);
let f = (await j('/portfolio/findings?responsibility=manager')).find((x) => x.id === 'FS-F002-A01');
check('opening a work order does not confirm the finding', f.status === 'PLAUSIBLE', f.status);
const wos = await j('/workorders');
check('work order stored by the backend', wos.length === 1 && wos[0].finding_id === 'FS-F002-A01');

await p.click(`${card} button:has-text("Mark as sent")`);
await p.waitForSelector(`${card} .wo:has-text("Sent to technician")`);
await p.click(`${card} button:has-text("Technician: fault found")`);
await p.waitForSelector(`${card} .wo:has-text("Technician found a fault")`);
f = (await j('/portfolio/findings?responsibility=manager')).find((x) => x.id === 'FS-F002-A01');
check('technician outcome -> CONFIRMED in the backend', f.status === 'CONFIRMED', f.wording);
check('UI shows backend wording "confirmed"', (await p.innerText(`${card} .alert-head`)).includes(f.wording));

await p.click(`${card} button:has-text("Mark as repaired")`);
await p.waitForSelector(`${card} button:has-text("Verify")`);
await p.click(`${card} button:has-text("Verify")`);
await p.waitForSelector(`${card} .wo:has-text("Verification")`);
const woText = await p.innerText(`${card} .wo`);
check('verification shown and flagged SIMULATED', woText.includes('SIMULATED') && /Verification: (VERIFIED|REPAIRED)/.test(woText), woText.split('\n').find((l) => l.startsWith('Verification')));
await p.reload();
await p.waitForSelector(`${card} .wo`);
check('work-order state persists across reload (backend)', (await p.innerText(`${card} .wo`)).includes('Verification'));

// --- backend outage: live mode against a dead port ---
const o = await b.newPage();
await o.goto(`${APP}?api=http://127.0.0.1:9`);
await o.evaluate(() => sessionStorage.setItem('wattwise.session', JSON.stringify({ role: 'student', flatId: 'F002' })));
await o.reload();
await o.waitForSelector('#s-over .error-box');
const ot = await o.innerText('#s-over');
check('backend down: error shown, no numbers', ot.includes('Could not load') && !/\d kWh/.test(ot));
check('backend down: data source labelled live', (await o.innerText('#data-source')).includes('live backend'));

// --- layouts ---
const m = await b.newPage({ viewport: { width: 390, height: 844 } });
await m.goto(APP);
await m.evaluate(() => sessionStorage.setItem('wattwise.session', JSON.stringify({ role: 'student', flatId: 'F002' })));
await m.reload();
await m.waitForSelector('#s-findings .card');
check('mobile student: no horizontal overflow', !(await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));
await p.waitForSelector('#m-flats tbody tr');
check('desktop manager: 8 flats', (await p.$$('#m-flats tbody tr')).length === 8);
check('no page errors', errors.length === 0, errors.join(' | '));
await b.close();
console.log(`\n${results.filter(Boolean).length}/${results.length} checks passed`);
process.exit(results.every(Boolean) ? 0 : 1);
