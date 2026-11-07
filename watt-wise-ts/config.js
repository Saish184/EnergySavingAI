// Runtime settings (no rebuild needed).
//   Served by the backend (http://localhost:8000/app/): live mode against that backend.
//   Served on its own (npm run serve, http://localhost:5173): offline mode with recorded real engine responses.
//   URL overrides: ?mode=live&api=http://localhost:8000   or   ?mode=mock
(function () {
  var fromBackend = location.pathname.indexOf('/app') === 0;
  window.WATTWISE_CONFIG = {
    mode: fromBackend ? 'live' : 'mock',
    apiBase: fromBackend ? location.origin : 'http://localhost:8000',
    fixturesBase: 'fixtures',
    timeoutMs: 20000,
  };
})();
