"""MOCK stand-in for the teammate's data/processed/ files (same schema), written to data/mock/.

    python mock_data.py            # from backend/

Synthetic readings shaped by the organisers' occupancy, with a handful of injected patterns so
every engine path is exercised. Anomaly numbers (excess, rates) are computed FROM the generated
readings, not typed in. Replace with the teammate's files by putting clean_readings.csv +
anomalies.json in data/processed/ (picked up automatically)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import config as C  # noqa: E402

RNG_SEED = 42


def _occupancy(flats: pd.DataFrame) -> pd.DataFrame:
    c = pd.read_csv(C.RAW_DIR / "hourly_context.csv", dtype=str)
    c["timestamp_utc"] = pd.to_datetime(c["timestamp_utc"], utc=True, format="ISO8601")
    c["occ"] = pd.to_numeric(c["occupants_home"], errors="coerce")
    res = c["flat_id"].map(flats.set_index("flat_id")["residents"])
    c["occ_frac"] = (c["occ"] / res).where(c["occ"] <= res).clip(0, 1).fillna(0.5)
    c["outdoor"] = pd.to_numeric(c["outdoor_temp_c"], errors="coerce").where(lambda s: s > -60).fillna(7.0)
    return c[["flat_id", "timestamp_utc", "occ", "occ_frac", "outdoor"]]


def _base_profiles(flat: str, residents: int, ts: pd.DatetimeIndex, occ: np.ndarray, outdoor: np.ndarray,
                   rng: np.random.Generator) -> dict[str, np.ndarray]:
    n = len(ts)
    lh = ts.tz_convert(C.TZ_LOCAL).hour.to_numpy()
    day = np.arange(n) // 24
    s = np.sqrt(residents)
    noise = lambda scale: np.abs(1 + scale * rng.standard_normal(n))  # noqa: E731
    p = {}
    p["A01"] = 0.035 * s * noise(0.15)                                                   # fridge-like
    evening = np.isin(lh, [6, 7, 8, 16, 17, 18, 19, 20, 21, 22])
    p["A02"] = (0.01 + 0.06 * occ * evening) * s * noise(0.2)                            # lighting-like
    meal = np.isin(lh, [7, 12, 18]) & (rng.random(n) < 0.6)
    p["A03"] = (0.005 + 0.55 * meal * occ) * s * noise(0.25)                             # cooking-like
    dish = np.zeros(n)
    run_hours = np.where((lh == 20) & (day % 2 == int(flat[1:]) % 2))[0]
    dish[run_hours] = 1.05
    p["A04"] = 0.002 + dish * noise(0.08)                                                # dishwasher-like
    p["A05"] = (0.03 + 0.05 * occ) * s * noise(0.2)                                     # electronics-like
    wash = np.zeros(n)
    wash[np.where((lh == 10) & (rng.random(n) < 0.25 * s / 2))[0]] = 0.8
    p["A06"] = 0.004 + wash * noise(0.1)                                                 # laundry-like
    cold = np.clip((8 - outdoor) / 8, 0, 1)
    p["A07"] = 0.4 * cold * occ * (rng.random(n) < 0.15) * noise(0.2)                    # heater-like
    return {k: np.maximum(0, v) for k, v in p.items()}


def generate(seed: int = RNG_SEED) -> None:
    rng = np.random.default_rng(seed)
    flats = pd.read_csv(C.RAW_DIR / "flats.csv", dtype={"flat_id": str})
    occ_all = _occupancy(flats)
    ts = pd.date_range(C.PERIOD_START, C.PERIOD_END, freq="h", tz="UTC", inclusive="left")
    assert len(ts) == C.PERIOD_HOURS
    lh = ts.tz_convert(C.TZ_LOCAL).hour.to_numpy()

    series: dict[str, np.ndarray] = {}
    occ_raw: dict[str, np.ndarray] = {}
    for _, f in flats.iterrows():
        o = occ_all[occ_all["flat_id"] == f.flat_id].set_index("timestamp_utc").reindex(ts)
        occ_raw[f.flat_id] = o["occ"].to_numpy()
        prof = _base_profiles(f.flat_id, int(f.residents), ts, o["occ_frac"].fillna(0.5).to_numpy(),
                              o["outdoor"].fillna(7.0).to_numpy(), rng)
        for ch, v in prof.items():
            series[f"{f.flat_id}-{ch}"] = v

    t = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731
    i = lambda s: int(ts.searchsorted(t(s)))  # noqa: E731  (end of period -> len(ts))
    injected = []

    def inject(app, typ, start, end, add, conf, evidence, mask=None):
        a, b = i(start), i(end)
        m = np.zeros(len(ts), bool)
        m[a:b] = True
        if mask is not None:
            m &= mask
        series[app] = series[app] + np.where(m, add, 0.0)
        injected.append(dict(appliance_id=app, type=typ, start=start, end=end, conf=conf, evidence=evidence, mask=m))

    # equipment faults (manager)
    inject("F003-A01", "fault_step_change", "2026-10-12T00:00:00Z", "2026-10-29T00:00:00Z", 0.11, 0.92,
           "sustained step change: fridge-like channel ~3x its first-11-day level, no return")
    inject("F008-A01", "fault_step_change", "2026-10-20T06:00:00Z", "2026-10-22T06:00:00Z", 0.06, 0.85,
           "short step change, 2 days, then back to normal")
    inject("F004-A06", "peer_outlier", "2026-10-01T00:00:00Z", "2026-10-29T00:00:00Z", 0.03, 0.62,
           "standby ~5x the same channel's median in the other flats")
    # behaviour (resident)
    for f, occ in occ_raw.items():
        if f == "F002":
            away = (occ == 0)
            inject("F002-A02", "away_usage", "2026-10-01T00:00:00Z", "2026-10-29T00:00:00Z", 0.12, 0.81,
                   "lighting-like load stays on while occupancy sensor reports nobody home", mask=away)
    night = np.isin(lh, [0, 1, 2, 3, 4])
    inject("F005-A05", "night_baseload", "2026-10-01T00:00:00Z", "2026-10-29T00:00:00Z", 0.09, 0.76,
           "night-time (00-05 local) base load well above the other flats", mask=night)
    peak = np.isin(lh, [18])
    inject("F007-A04", "peak_usage", "2026-10-01T00:00:00Z", "2026-10-29T00:00:00Z", 0.9, 0.66,
           "dishwasher-like runs mostly start 18:00 local, in the price/carbon peak", mask=peak & (np.arange(len(ts)) // 24 % 2 == 0))
    # heating (unknown)
    nights = np.isin(lh, [22, 23, 0, 1, 2, 3, 4, 5])
    inject("F006-A07", "heater_pattern", "2026-10-15T00:00:00Z", "2026-10-29T00:00:00Z", 0.9, 0.72,
           "heater-like channel runs every night after outdoor temperature drop", mask=nights)

    # missing data: random gaps + one 24 h outage. NaN = missing, never 0.
    for app, v in series.items():
        v[rng.random(len(v)) < 0.004] = np.nan
    series["F001-A03"][i("2026-10-09T00:00:00Z"):i("2026-10-10T00:00:00Z")] = np.nan

    rows = []
    for app, v in series.items():
        rows.append(pd.DataFrame({"flat_id": app[:4], "appliance_id": app, "channel": app[-3:],
                                  "timestamp_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"), "kwh": np.round(v, 5)}))
    readings = pd.concat(rows, ignore_index=True)

    # anomalies.json, numbers measured from the generated series
    anomalies = []
    for k, inj in enumerate(injected, 1):
        v = series[inj["appliance_id"]]
        a, b = i(inj["start"]), i(inj["end"])
        pre = v[:a] if a > 48 else v[b:]
        pre = pre[~np.isnan(pre)]
        m = inj["mask"]
        baseline = float(np.median(pre)) if inj["type"] != "peer_outlier" and len(pre) else None
        if baseline is None:  # peers: median of same channel elsewhere
            ch = inj["appliance_id"][-3:]
            peers = np.concatenate([s for ap, s in series.items() if ap.endswith(ch) and ap != inj["appliance_id"]])
            baseline = float(np.nanmedian(peers))
        if inj["type"] in ("away_usage", "night_baseload", "peak_usage", "heater_pattern"):
            ref = v[~m & ~np.isnan(v)]
            hours = np.isin(lh, np.unique(lh[m]))
            ref = v[hours & ~m & ~np.isnan(v)] if (hours & ~m).any() else ref
            baseline = float(np.median(ref)) if len(ref) else 0.0
        obs = float(np.nanmean(v[m]))
        excess = float(np.nansum(np.maximum(0, v[m] - baseline)))
        anomalies.append({
            "id": f"AN{k:03d}", "flat_id": inj["appliance_id"][:4], "appliance_id": inj["appliance_id"],
            "type": inj["type"], "start": inj["start"], "end": inj["end"],
            "excess_kwh": round(excess, 3), "baseline_kwh_per_h": round(baseline, 4),
            "observed_kwh_per_h": round(obs, 4), "confidence": inj["conf"],
            "evidence": inj["evidence"] + " [MOCK]",
        })

    C.MOCK_DIR.mkdir(parents=True, exist_ok=True)
    readings.to_csv(C.MOCK_DIR / "clean_readings.csv", index=False)
    (C.MOCK_DIR / "anomalies.json").write_text(json.dumps(anomalies, indent=2), encoding="utf-8")
    (C.MOCK_DIR / "cleaning_log.json").write_text(json.dumps(
        {"note": "MOCK data - no cleaning performed", "rows": len(readings),
         "missing_kwh": int(readings["kwh"].isna().sum())}, indent=2), encoding="utf-8")
    print(f"mock: {len(readings)} readings, {len(anomalies)} anomalies -> {C.MOCK_DIR}")


if __name__ == "__main__":
    generate()
