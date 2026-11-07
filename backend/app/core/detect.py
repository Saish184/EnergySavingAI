"""Evidence-based anomaly detection on the BASELINE data. Each anomaly carries frozen references.

Detectors (all thresholds are in config.py with their justification):
  fault_step_change  lasting level increase on a continuous channel. Daily means (>= MIN_HOURS_PER_DAY observed;
                     days with nobody home all day are excluded); statistic = max one-sided Welch t over every split
                     leaving >= MIN_SEGMENT_DAYS each side; p from a day-permutation test (exact for the max over
                     splits, no distributional assumption); PLAUSIBLE if p < DETECTION_ALPHA. Split hour refined
                     within +/-24 h. Excess reference r = pre-split mean.
  base_load_outlier  always-on floor (P5 of hourly kWh) above the range of the other flats in EVERY week.
                     Excess = min(max(x - m, 0), floor - m), m = median of the other flats' floors.
  scheduled_block    hours of day where the flat's weekly median exceeds every other flat's weekly median in EVERY
                     week, AND the level persists while nobody is home (device-driven, not person-driven).
                     Excess = max(x - peer median at that local hour, 0).
  heater_pattern     heater-like use while nobody is home in absences >= MIN_ABSENCE_HOURS on >= MIN_EVIDENCE_DAYS
                     days. Excess = that use. Responsibility unknown until a person confirms the heater.
  peak_usage         flexible-appliance runs starting in data-driven peak-price hours on >= MIN_EVIDENCE_DAYS days.
                     Not waste: a timing opportunity (load shift, same kWh).
Anomaly dict: id, flat_id, appliance_id, channel, type, status, responsibility, start, end, cells (bool[672]),
ref (float[672]), cap (float[672]), stats, evidence, baseline_kwh_per_h, observed_kwh_per_h, excess_kwh.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C
from .claims import Status
from .hourly import CHANNELS, N_HOURS, T0, FlatData

DAYS = N_HOURS // 24


def channel_classes(flats: dict[str, FlatData]) -> dict[str, str]:
    allv = {c: np.concatenate([fd.kwh[c].to_numpy(dtype=float) for fd in flats.values()]) for c in CHANNELS}
    return {c: ("continuous" if np.nanmean(v == 0) <= C.CONTINUOUS_MAX_ZERO_SHARE else "event") for c, v in allv.items()}


def peak_hours(flats: dict[str, FlatData]) -> set[int]:
    fd = next(iter(flats.values()))
    p = pd.DataFrame({"p": fd.price.to_numpy(dtype=float), "lh": fd.local_hour.to_numpy()})
    if p.p.notna().sum() < N_HOURS / 2:
        return set(C.PEAK_HOURS_FALLBACK)
    by = p.groupby("lh").p.mean()
    return {int(h) for h, v in by.items() if v > p.p.mean()}


def _ts(h: int) -> pd.Timestamp:
    return T0 + pd.Timedelta(hours=int(h))


def _base(fd: FlatData, a: dict) -> dict:
    return {"flat_id": fd.flat_id, "appliance_id": f"{fd.flat_id}-{a['channel']}", "confidence": None, **a}


def _finish(fd: FlatData, a: dict) -> dict:
    x = fd.kwh[a["channel"]].to_numpy(dtype=float)
    m = a["cells"] & ~np.isnan(x)
    exc = np.minimum(np.maximum(x[m] - a["ref"][m], 0.0), a["cap"][m])
    a["observed_kwh_per_h"] = float(np.mean(x[m])) if m.any() else np.nan
    a["baseline_kwh_per_h"] = float(np.mean(a["ref"][m])) if m.any() else np.nan
    a["excess_kwh"] = float(exc.sum())
    a["observed_cells"] = int(m.sum())
    hrs = np.where(a["cells"])[0]
    a["start"], a["end"] = _ts(hrs.min()), _ts(hrs.max() + 1)
    return a


# ----------------------------------------------------------------------------------------------- step change
def _welch_max_t(D: np.ndarray, kmin: int) -> np.ndarray:
    """D: (B, n) day means. Returns (B,) max over splits k in [kmin, n-kmin] of one-sided Welch t (post - pre)."""
    n = D.shape[1]
    best = np.full(D.shape[0], -np.inf)
    for k in range(kmin, n - kmin + 1):
        a, b = D[:, :k], D[:, k:]
        va, vb = a.var(axis=1, ddof=1) / k, b.var(axis=1, ddof=1) / (n - k)
        t = (b.mean(axis=1) - a.mean(axis=1)) / np.sqrt(np.maximum(va + vb, 1e-18))
        best = np.maximum(best, t)
    return best


def check_test_resolution():
    """A permutation p-value cannot be smaller than 1/(B+1): an alpha at or below that can never be met and would
    silently disable detection (found in the sensitivity analysis)."""
    if C.DETECTION_ALPHA <= 1.0 / (C.PERMUTATIONS + 1):
        raise ValueError(f"DETECTION_ALPHA={C.DETECTION_ALPHA} is not attainable with {C.PERMUTATIONS} permutations "
                         f"(smallest p = {1 / (C.PERMUTATIONS + 1):.4f}); increase PERMUTATIONS")


def detect_step_changes(fd: FlatData, ch: str, rng: np.random.Generator) -> dict | None:
    x = fd.kwh[ch].to_numpy(dtype=float)
    occ = fd.occupants.to_numpy(dtype=float)
    days = []
    for d in range(DAYS):
        seg, o = x[24 * d:24 * d + 24], occ[24 * d:24 * d + 24]
        vacant = np.all(o[~np.isnan(o)] == 0) and (~np.isnan(o)).sum() >= C.MIN_HOURS_PER_DAY
        days.append(np.nan if (np.isfinite(seg).sum() < C.MIN_HOURS_PER_DAY or vacant) else np.nanmean(seg))
    days = np.array(days)
    keep = np.isfinite(days)
    D = days[keep]
    idx = np.where(keep)[0]
    if D.size < 2 * C.MIN_SEGMENT_DAYS:
        return None
    t_obs = _welch_max_t(D[None, :], C.MIN_SEGMENT_DAYS)[0]
    perms = np.array([rng.permutation(D) for _ in range(C.PERMUTATIONS)])
    t_null = _welch_max_t(perms, C.MIN_SEGMENT_DAYS)
    p = (1 + np.sum(t_null >= t_obs)) / (C.PERMUTATIONS + 1)
    if p >= C.DETECTION_ALPHA:
        return None
    # split day = argmax, then refine hour within +/- 24 h by maximising the hourly mean difference
    n = D.size
    ts = [((D[k:].mean() - D[:k].mean()) / np.sqrt(D[:k].var(ddof=1) / k + D[k:].var(ddof=1) / (n - k)), k)
          for k in range(C.MIN_SEGMENT_DAYS, n - C.MIN_SEGMENT_DAYS + 1)]
    k = max(ts)[1]
    h0 = int(idx[k]) * 24
    cand = range(max(24, h0 - 24), min(N_HOURS - 24, h0 + 25))
    split = max(cand, key=lambda h: np.nanmean(x[h:]) - np.nanmean(x[:h]))
    pre, post = x[:split], x[split:]
    if (np.isfinite(post).sum() / 24) < C.MIN_SEGMENT_DAYS:
        return None
    ref = float(np.nanmean(pre))
    cells = np.zeros(N_HOURS, bool)
    cells[split:] = True
    status = Status.PLAUSIBLE if (N_HOURS - split) / 24 >= C.PLAUSIBLE_MIN_DAYS else Status.DETECTED
    a = _base(fd, {
        "id": f"FS-{fd.flat_id}-{ch}", "channel": ch, "type": "fault_step_change", "status": status,
        "responsibility": "manager" if ch in C.EQUIPMENT_CHANNELS else "resident",
        "cells": cells, "ref": np.full(N_HOURS, ref), "cap": np.full(N_HOURS, np.inf),
        "stats": {"test": "one-sided max-Welch-t over day splits, day-permutation p-value",
                  "t_max": float(t_obs), "p_value": float(p), "permutations": C.PERMUTATIONS, "alpha": C.DETECTION_ALPHA,
                  "split_utc": str(_ts(split)), "pre_mean": ref, "post_mean": float(np.nanmean(post)),
                  "ratio": float(np.nanmean(post) / ref) if ref > 0 else None, "days_used": int(D.size),
                  "excluded_vacant_or_sparse_days": int((~keep).sum())},
        "evidence": f"lasting level increase from {_ts(split):%Y-%m-%d %H:%M} UTC: {ref:.4f} -> {np.nanmean(post):.4f} kWh/h "
                    f"(permutation p = {p:.3f})",
    })
    return _finish(fd, a)


# ----------------------------------------------------------------------------------------------- base load / blocks
def _weekly(v: np.ndarray, fn) -> np.ndarray:
    return np.array([fn(v[168 * w:168 * (w + 1)]) for w in range(N_HOURS // 168)])


def detect_base_load(flats: dict[str, FlatData], fl: str, ch: str) -> dict | None:
    p5 = lambda v: np.nanpercentile(v, 5) if np.isfinite(v).any() else np.nan  # noqa: E731
    own = _weekly(flats[fl].kwh[ch].to_numpy(dtype=float), p5)
    peers = {k: _weekly(f.kwh[ch].to_numpy(dtype=float), p5) for k, f in flats.items() if k != fl}
    pmax = np.nanmax(np.vstack(list(peers.values())), axis=0)
    weeks_above = int(np.sum(own > pmax))
    if weeks_above < 2:
        return None
    m = float(np.median([np.nanpercentile(f.kwh[ch].to_numpy(dtype=float), 5) for k, f in flats.items() if k != fl]))
    floor = float(np.nanpercentile(flats[fl].kwh[ch].to_numpy(dtype=float), 5))
    delta = floor - m
    if delta <= 0:
        return None
    fd = flats[fl]
    a = _base(fd, {
        "id": f"BL-{fl}-{ch}", "channel": ch, "type": "base_load_outlier",
        "status": Status.PLAUSIBLE if weeks_above == len(own) else Status.DETECTED, "responsibility": "resident",
        "cells": np.ones(N_HOURS, bool), "ref": np.full(N_HOURS, m), "cap": np.full(N_HOURS, delta),
        "stats": {"criterion": "always-on floor (P5) above every other flat's floor, per week", "weeks_above_peer_range": weeks_above,
                  "weeks": len(own), "floor_kwh_h": floor, "peer_median_floor_kwh_h": m, "peer_max_floor_by_week": pmax.tolist(),
                  "excess_w": 1000 * delta},
        "evidence": f"always-on level {1000 * floor:.0f} W vs {1000 * m:.0f} W in the other flats, above their range in "
                    f"{weeks_above}/{len(own)} weeks",
    })
    return _finish(fd, a)


def detect_scheduled_block(flats: dict[str, FlatData], fl: str, ch: str) -> dict | None:
    fd = flats[fl]
    lh = fd.local_hour.to_numpy()
    weeks = N_HOURS // 168

    def weekly_hour_medians(f):
        x = f.kwh[ch].to_numpy(dtype=float)
        return np.array([[np.nanmedian(x[168 * w:168 * (w + 1)][lh[168 * w:168 * (w + 1)] == h]) for h in range(24)] for w in range(weeks)])

    own = weekly_hour_medians(fd)
    peer = np.nanmax(np.stack([weekly_hour_medians(f) for k, f in flats.items() if k != fl]), axis=0)
    flagged = [h for h in range(24) if np.all(own[:, h] > peer[:, h])]
    if not flagged:
        return None
    peer_med = pd.concat([pd.DataFrame({"v": f.kwh[ch], "lh": f.local_hour}) for k, f in flats.items() if k != fl]).dropna().groupby("lh").v.median()
    x = fd.kwh[ch].to_numpy(dtype=float)
    occ = fd.occupants.to_numpy(dtype=float)
    in_block = np.isin(lh, flagged)
    unocc = in_block & (occ == 0) & np.isfinite(x)
    unocc_days = len(set(np.where(unocc)[0] // 24))
    peer_at = np.array([peer_med.get(h, np.nan) for h in lh])
    if unocc_days < C.MIN_EVIDENCE_DAYS or not np.nanmedian(x[unocc]) > np.nanmax(peer[:, flagged]):
        return None                                          # level not shown to persist with nobody home
    a = _base(fd, {
        "id": f"SB-{fl}-{ch}", "channel": ch, "type": "scheduled_block", "status": Status.PLAUSIBLE, "responsibility": "resident",
        "cells": in_block, "ref": peer_at, "cap": np.full(N_HOURS, np.inf),
        "stats": {"criterion": "hour-of-day weekly median above every other flat in every week, and persists with nobody home",
                  "local_hours": flagged, "unoccupied_days_with_block": unocc_days,
                  "median_when_unoccupied_kwh_h": float(np.nanmedian(x[unocc])),
                  "peer_max_weekly_median_kwh_h": float(np.nanmax(peer[:, flagged]))},
        "evidence": f"{float(np.nanmedian(x[in_block])) * 1000:.0f} W at local hours {min(flagged):02d}-{max(flagged) + 1:02d} on "
                    f"every week, also with nobody home ({unocc_days} days); other flats <= {1000 * np.nanmax(peer[:, flagged]):.0f} W",
    })
    return _finish(fd, a)


# ----------------------------------------------------------------------------------------------- behaviour
def unoccupied_cells(fd: FlatData, min_len: int) -> np.ndarray:
    from .hourly import unoccupied_runs
    m = np.zeros(N_HOURS, bool)
    m[unoccupied_runs(fd, min_len)] = True
    return m


def detect_heater(fd: FlatData, ch: str) -> dict | None:
    x = fd.kwh[ch].to_numpy(dtype=float)
    if not np.nansum(x) > 0:
        return None
    cells = unoccupied_cells(fd, C.MIN_ABSENCE_HOURS) & (np.nan_to_num(x) > 0)
    upper = unoccupied_cells(fd, 1) & (np.nan_to_num(x) > 0)
    days = len(set(np.where(cells)[0] // 24))
    if days < C.MIN_EVIDENCE_DAYS:
        return None
    a = _base(fd, {
        "id": f"HU-{fd.flat_id}-{ch}", "channel": ch, "type": "heater_pattern", "status": Status.PLAUSIBLE,
        "responsibility": "unknown", "cells": cells, "ref": np.zeros(N_HOURS), "cap": np.full(N_HOURS, np.inf),
        "stats": {"criterion": f"heater-like use with nobody home, absences >= {C.MIN_ABSENCE_HOURS} h, on >= {C.MIN_EVIDENCE_DAYS} days",
                  "days": days, "hours": int(cells.sum()), "hours_any_absence": int(upper.sum()),
                  "kwh_any_absence": float(np.nansum(x[upper])), "occupancy_source": "simulated sensor estimate"},
        "evidence": f"heater-like use in {int(cells.sum())} unoccupied hours on {days} days (absences >= {C.MIN_ABSENCE_HOURS} h); "
                    f"{int(upper.sum())} h incl. 1-h gaps",
    })
    return _finish(fd, a)


def detect_peak_usage(fd: FlatData, ch: str, peak: set[int]) -> dict | None:
    x = fd.kwh[ch].to_numpy(dtype=float)
    lh = fd.local_hour.to_numpy()
    runs = np.nan_to_num(x) > 0
    cells = runs & np.isin(lh, list(peak))
    days = len(set(np.where(cells)[0] // 24))
    if days < C.MIN_EVIDENCE_DAYS:
        return None
    a = _base(fd, {
        "id": f"PK-{fd.flat_id}-{ch}", "channel": ch, "type": "peak_usage", "status": Status.PLAUSIBLE, "responsibility": "resident",
        "cells": cells, "ref": np.zeros(N_HOURS), "cap": np.full(N_HOURS, np.inf),
        "stats": {"criterion": f"runs in peak-price hours on >= {C.MIN_EVIDENCE_DAYS} days", "peak_hours_local": sorted(peak),
                  "runs_in_peak": int(cells.sum()), "runs_total": int(runs.sum()), "days": days,
                  "kwh_in_peak": float(np.nansum(x[cells]))},
        "evidence": f"{int(cells.sum())} of {int(runs.sum())} runs start in peak-price hours (local {sorted(peak)})",
    })
    return _finish(fd, a)


# ----------------------------------------------------------------------------------------------- all
def detect_all(flats: dict[str, FlatData]) -> list[dict]:
    check_test_resolution()
    classes = channel_classes(flats)
    peak = peak_hours(flats)
    rng = np.random.default_rng(C.PERMUTATION_SEED)
    out = []
    for fl in sorted(flats):
        fd = flats[fl]
        for ch in CHANNELS:
            if classes[ch] != "continuous" or ch in C.HEATER_CHANNELS:
                continue
            step = detect_step_changes(fd, ch, rng)
            if step:
                out.append(step)
                continue                                    # a lasting step explains the channel's excess
            bl = detect_base_load(flats, fl, ch)
            if bl:
                out.append(bl)
                continue
            if ch not in C.EQUIPMENT_CHANNELS:
                sb = detect_scheduled_block(flats, fl, ch)
                if sb:
                    out.append(sb)
        for ch in sorted(C.HEATER_CHANNELS):
            h = detect_heater(fd, ch)
            if h:
                out.append(h)
        for ch in sorted(C.FLEXIBLE_CHANNELS):
            pk = detect_peak_usage(fd, ch, peak)
            if pk:
                out.append(pk)
    return out
