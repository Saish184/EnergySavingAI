// Watt Wise: placeholder data. Replace these arrays with your real analysis output.
// Hours are UTC, matching the dataset.

var BASE_PROFILE = [0.14,0.12,0.12,0.11,0.13,0.28,0.38,0.30,0.22,0.20,0.19,0.21,0.24,0.22,0.23,0.34,0.52,0.66,0.58,0.46,0.38,0.30,0.22,0.17]; // kWh per hour, 2-person flat
var PRICE  = [0.35,0.37,0.38,0.38,0.38,0.85,0.88,0.85,0.35,0.30,0.30,0.25,0.30,0.30,0.30,0.88,0.95,0.90,0.88,0.33,0.33,0.33,0.30,0.38]; // SEK/kWh
var CARBON = [33,32,31,32,33,52,53,52,33,31,31,31,30,31,31,50,52,48,50,34,35,34,33,32]; // gCO2e/kWh

var FLATS = [
  { id: 'F001', meta: '2 residents · 56 m²', residents: 2, scale: 1.0, night: 0.00 },
  { id: 'F003', meta: '4 residents · 82 m²', residents: 4, scale: 1.7, night: 0.10 },
  { id: 'F005', meta: '5 residents · 95 m²', residents: 5, scale: 2.1, night: 0.04 }
];

var DAYS = 28;
var state = { flat: 0, shift: 30 };

function $(id) { return document.getElementById(id); }
function avg(arr, idx) { return idx.reduce(function (a, i) { return a + arr[i]; }, 0) / idx.length; }

function render() {
  var f = FLATS[state.flat];
  var prof = BASE_PROFILE.map(function (v, i) { return v * f.scale + (i < 5 ? f.night : 0); });
  var max = Math.max.apply(null, prof);

  // tabs
  var tabs = $('tabs');
  tabs.innerHTML = '';
  FLATS.forEach(function (x, i) {
    var b = document.createElement('button');
    b.className = 'tab';
    b.textContent = x.id;
    b.setAttribute('aria-pressed', i === state.flat ? 'true' : 'false');
    b.addEventListener('click', function () { state.flat = i; render(); });
    tabs.appendChild(b);
  });

  $('viewing').innerHTML = 'Viewing <b>' + f.id + '</b> · ' + f.meta +
    ' · October 2026, 4 weeks · sample figures for the design mockup, not real results';

  // totals
  var kwh = prof.reduce(function (a, v) { return a + v; }, 0) * DAYS;
  var cost = prof.reduce(function (a, v, i) { return a + v * PRICE[i]; }, 0) * DAYS;
  var co2 = prof.reduce(function (a, v, i) { return a + v * CARBON[i] / 1000; }, 0) * DAYS;
  $('kwh').textContent = Math.round(kwh);
  $('kwhPerPerson').textContent = Math.round(kwh / f.residents);
  $('cost').textContent = cost.toFixed(0);
  $('co2').textContent = co2.toFixed(1);

  // chart
  var bars = $('bars'), labels = $('barLabels');
  bars.innerHTML = ''; labels.innerHTML = '';
  prof.forEach(function (v, i) {
    var d = document.createElement('div');
    d.className = 'bar';
    d.style.height = Math.round(v / max * 190) + 'px';
    d.style.background = PRICE[i] > 0.7 ? '#D9622B' : (PRICE[i] < 0.3 ? '#1F7A5A' : '#8FB3A5');
    d.title = String(i).padStart(2, '0') + ':00 UTC, ' + v.toFixed(2) + ' kWh, ' + PRICE[i].toFixed(2) + ' SEK/kWh';
    bars.appendChild(d);
    var s = document.createElement('span');
    s.textContent = i % 3 === 0 ? String(i).padStart(2, '0') : '';
    labels.appendChild(s);
  });
  var night = (prof[0] + prof[1] + prof[2] + prof[3] + prof[4]) / 5;
  $('nightKwh').textContent = night.toFixed(2);

  // what-if
  var peak = [15, 16, 17], dest = [22, 23, 0, 1, 2, 3];
  var peakKwh = peak.reduce(function (a, i) { return a + prof[i]; }, 0) * DAYS;
  var moved = peakKwh * state.shift / 100;
  $('shiftLabel').textContent = 'Share moved: ' + state.shift + '%';
  $('movedKwh').textContent = moved.toFixed(1);
  $('saveSek').textContent = (moved * (avg(PRICE, peak) - avg(PRICE, dest))).toFixed(1);
  $('saveCo2').textContent = (moved * (avg(CARBON, peak) - avg(CARBON, dest)) / 1000).toFixed(2);
}

$('shift').addEventListener('input', function (e) {
  state.shift = Number(e.target.value);
  render();
});

render();
