// Browser smoke test (Playwright, headless Chromium).
//   npm run serve            (in another terminal, serves http://localhost:5173)
//   npm run smoke            mock mode (default)
//   SMOKE_MODE=live npm run smoke   (needs the FastAPI backend on :8000)
// Expected numbers are read from the recorded engine responses (fixtures/), never hard-coded.
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = require('playwright');
const here = dirname(fileURLToPath(import.meta.url));
const fx = join(here, '..', 'fixtures');
const idx = JSON.parse(readFileSync(join(fx, 'index.json'), 'utf8'));
const get = (p) => JSON.parse(readFileSync(join(fx, idx.get[p]), 'utf8'));
const scen = (k) => JSON.parse(readFileSync(join(fx, idx.scenarios[k]), 'utf8'));
const n = (x, d) => Number(x.toFixed(d)).toLocaleString('en-GB', { minimumFractionDigits: d, maximumFractionDigits: d });

const BASE = process.env.SMOKE_URL ?? 'http://localhost:5173/';
const MODE = process.env.SMOKE_MODE ?? 'mock';
const results = [];
const check = (name, cond, extra = '') => {
  results.push({ name, ok: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'}  ${name}${extra ? `  (${extra})` : ''}`);
};

const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1280, height: 900 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));

await page.goto(`${BASE}?mode=${MODE}`);
await page.evaluate(() => sessionStorage.clear());
await page.reload();

// 1. student login F002
await page.fill('#l-flat', '2');
await page.click('#l-student button[type=submit]');
await page.waitForSelector('#s-over .kpi');
const br = get('/flats/F002/breakdown');
const over = await page.innerText('#s-over');
check('F002 consumption from engine', over.includes(`${n(br.totals.kwh, 1)} kWh`), `${n(br.totals.kwh, 1)} kWh`);
check('F002 spot cost from engine', over.includes(`${n(br.totals.sek, 2)} SEK`));
check('F002 CO2e from engine', over.includes(`${n(br.totals.co2_kg, 2)} kg CO₂e`));

await page.waitForSelector('#s-score .score-num');
const sc = get('/flats/F002/scores');
check('F002 resident score', (await page.innerText('#s-score .score-num')) === n(sc.lenses.resident.score, 1), n(sc.lenses.resident.score, 1));

await page.waitForSelector('#s-hours .bar');
check('hourly chart has 24 local hours', (await page.$$('#s-hours .bar')).length === 24);
check('daily chart has local dates incl. partial days', (await page.$$('#s-days .bar')).length === get('/flats/F002/profile').daily.length);

// LLM / text layer (validated text from the backend; template wording offline)
const ex = sc.explainer.output;
const scoreText = await page.innerText('#s-score-text');
check('score explanation connected (no "not connected")', scoreText.includes(ex.summary) && !/not connected/i.test(await page.innerText('#app')));
check('text source is labelled', /Standard explanation|AI explanation/.test(scoreText));
await page.waitForSelector('#s-digest .textcard');
check('28-day digest shown', (await page.innerText('#s-digest')).includes(get('/flats/F002/digest').output.headline));

// 2. fridge-like finding
await page.waitForSelector('#finding-FS-F002-A01');
const fs = get('/flats/F002/findings').find((f) => f.id === 'FS-F002-A01');
const card = await page.innerText('#finding-FS-F002-A01');
check('fridge finding: avoidable kWh', card.includes(`${n(fs.avoidable_28d.kwh, 1)} kWh`), `${n(fs.avoidable_28d.kwh, 1)} kWh`);
check('fridge finding: 14-day window', card.includes('14 days'));
check('fridge finding: SEK conditional on hourly spot', card.includes(`${n(fs.valuation.sek_if_hourly_spot, 2)} SEK if you pay hourly spot prices`));
check('fridge finding: wording verbatim', card.includes(fs.wording));
check('fridge finding: validated student explanation', card.includes(fs.student_text.output.explanation));
check('no confidence percentages shown', !/confidence:\s*(medium|low)/i.test(await page.innerText('#app')));

// 3. dishwasher scenario under hourly spot
await page.check('input[name="s-tariff"][value="hourly_spot"]');
await page.click('#finding-PK-F002-A04 [data-sim]');
await page.click('#sim-run');
await page.waitForSelector('#sim-result .sim-out');
const key = JSON.stringify({ flat_id: 'F002', params: { anomaly_id: 'PK-F002-A04', tariff: { type: 'hourly_spot' } }, scenario: 'return_to_baseline' });
const dw = scen(key);
const out = await page.innerText('#sim-result');
check('dishwasher: 0 kWh change (shift)', out.includes('0.00 kWh') && out.includes('same kWh'));
check('dishwasher: hourly-spot benefit from engine', out.includes(`${n(dw.valuation.sek, 2)} SEK`), `${n(dw.valuation.sek, 2)} SEK`);
check('dishwasher: score after from engine', out.includes(n(dw.after.resident.score, 1)));

// other tariffs must not inherit the shift benefit
await page.check('input[name="s-tariff"][value="monthly_average_spot"]');
await page.click('#sim-run');
await page.waitForFunction(() => document.querySelector('#sim-result')?.textContent?.includes('does not change your cost'));
check('dishwasher: monthly average tariff -> 0 SEK', (await page.innerText('#sim-result')).includes('0.00 SEK'));

// 4. manager
await page.click('#signout');
await page.click('.seg [data-role=manager]');
await page.fill('#l-email', 'manager@example.se');
await page.fill('#l-pass', 'demo-password');
await page.click('#l-manager button[type=submit]');
await page.waitForSelector('#m-over .kpi');
const pf = get('/portfolio');
const mo = await page.innerText('#m-over');
check('portfolio kWh', mo.includes(`${n(pf.totals.kwh, 1)} kWh`), n(pf.totals.kwh, 1));
check('portfolio SEK', mo.includes(`${n(pf.totals.sek, 2)} SEK`), n(pf.totals.sek, 2));
check('portfolio CO2e', mo.includes(`${n(pf.totals.co2_kg, 2)} kg CO₂e`), n(pf.totals.co2_kg, 2));
check('portfolio potential (combined engine calc)', mo.includes(`${n(pf.potential.kwh, 1)} kWh`), n(pf.potential.kwh, 1));
await page.waitForSelector('#m-summary .textcard');
check('manager portfolio summary text', (await page.innerText('#m-summary')).includes(get('/portfolio/summary').output.headline));
check('8 flats in comparison table', (await page.$$('#m-flats tbody tr')).length === 8);
await page.waitForSelector('#m-maint .card');
const mf = get('/portfolio/findings?responsibility=manager').find((f) => f.id === 'FS-F002-A01');
check('maintenance: manager summary + triage', (await page.innerText('#finding-FS-F002-A01')).includes(mf.manager_text.output.suggested_check) && (await page.innerText('#finding-FS-F002-A01')).includes('Send a technician'));
check('maintenance: F002 fridge-like finding listed', (await page.innerText('#m-maint')).includes('FS-F002-A01') || (await page.$('#finding-FS-F002-A01')) !== null);
await page.waitForSelector('#m-res table');
check('resident findings include F007 heater', (await page.innerText('#m-res')).includes('F007'));

// mobile: no horizontal overflow
await page.setViewportSize({ width: 375, height: 800 });
check('no horizontal overflow at 375 px', !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)));

if (process.env.SMOKE_SHOTS) {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: `${process.env.SMOKE_SHOTS}/manager.png`, fullPage: true });
}
check('no browser console errors', errors.length === 0, errors.join(' | '));
await b.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
