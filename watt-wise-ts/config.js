// Runtime settings (no rebuild needed). URL overrides: ?mode=live&api=http://localhost:8000  or  ?mode=mock
// mode "mock": real engine responses recorded in fixtures/ (no backend needed). mode "live": FastAPI backend.
window.WATTWISE_CONFIG = { mode: 'mock', apiBase: 'http://localhost:8000', fixturesBase: 'fixtures', timeoutMs: 20000 };
