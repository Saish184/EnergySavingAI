"""How much does a score depend on our choice of weights? Redraw weights 2000 times."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config as C


def weight_draws(weights: dict, n: int = C.SENS_DRAWS, concentration: float = C.SENS_CONCENTRATION,
                 seed: int = C.SENS_SEED) -> np.ndarray:
    alpha = np.array([weights[k] * concentration for k in weights])
    return np.random.default_rng(seed).dirichlet(alpha, size=n)          # (n, k)


def sensitivity(pillars: pd.DataFrame, weights: dict, **kw) -> pd.DataFrame:
    """Per flat: score p5/p95 and rank p5/p95 (rank 1 = best) under random weights."""
    keys = list(weights)
    P = pillars[keys].to_numpy(dtype=float)                               # (flats, k)
    valid = ~np.isnan(P).any(axis=1)
    logp = np.log(np.maximum(1.0, np.nan_to_num(P, nan=1.0)))
    W = weight_draws(weights, **kw)
    S = np.exp(logp @ W.T)                                               # (flats, n)
    S[~valid] = np.nan
    ranks = pd.DataFrame(S).rank(axis=0, ascending=False, method="min").to_numpy()
    out = pd.DataFrame({
        "score_p5": np.nanpercentile(S, 5, axis=1) if valid.any() else np.nan,
        "score_p95": np.nanpercentile(S, 95, axis=1) if valid.any() else np.nan,
        "rank_p5": np.nanpercentile(ranks, 5, axis=1),
        "rank_p95": np.nanpercentile(ranks, 95, axis=1),
    }, index=pillars.index)
    out.loc[~valid, :] = np.nan
    out["draws"] = W.shape[0]
    return out
