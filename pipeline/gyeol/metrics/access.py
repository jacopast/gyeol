"""공공공간 접근성 (SPEC 2.1~2.2). 실제 도시와 시나리오 실험실이 같은 함수를 쓴다.

A_i = Σ_j S_j^α · f(d_ij; R_j),   R_j = clip(r0 · (S_j / S0)^β, r_min, r_max)
가우시안 감쇠 (Gaussian 2SFCA의 형태):  f = (exp(-½(d/R)²) − exp(-½)) / (1 − exp(-½)),  d ≤ R,  그 밖 0
단계형 감쇠: scale = R / r0,  d ≤ inner·scale → 1,  d ≤ outer·scale → mid,  그 밖 0
2SFCA:  ratio_j = S_j / Σ_k P_k f(d_kj; R_j),   A_i = Σ_j ratio_j f(d_ij; R_j)
"""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp

EXP_HALF = np.exp(-0.5)


def radius(S: np.ndarray, beta: float, a: dict) -> np.ndarray:
    R = a["r0_m"] * np.power(np.maximum(S, 1e-9) / a["s0_m2"], beta)
    return np.clip(R, a["r_min_m"], a["r_max_m"])


def decay(d: np.ndarray, R: np.ndarray, kind: str, a: dict) -> np.ndarray:
    d = np.asarray(d, float)
    if kind == "gaussian":
        f = (np.exp(-0.5 * (d / R) ** 2) - EXP_HALF) / (1 - EXP_HALF)
        return np.where(d <= R, f, 0.0)
    if kind == "step":
        scale = R / a["r0_m"]
        return np.where(d <= a["step_inner_m"] * scale, 1.0, np.where(d <= a["step_outer_m"] * scale, a["step_mid"], 0.0))
    raise ValueError(kind)


def max_reach(S: np.ndarray, a: dict, extra_m: float = 0.0) -> np.ndarray:
    """공간마다 다익스트라 한계 거리: 가장 큰 β의 반경(단계형 바깥 경계 포함)과 extra_m 중 큰 값."""
    R = radius(S, max(a["betas"]), a)
    step_outer = a["step_outer_m"] * R / a["r0_m"]
    return np.maximum(np.maximum(R, step_outer), extra_m)


def space_distances(cells, spaces, net, prm) -> sp.csr_matrix:
    """셀 × 공간 네트워크 거리(m) 희소 행렬. 저장값 = 거리 + 1 (0과 '도달 못함'을 구분하려고)."""
    a = prm["access"]
    S = spaces["area_m2"].to_numpy(float)
    walk = prm["walk"]
    extra = max(a["cover_minutes"]) * 60 * walk["speed_mps"]
    lim = max_reach(S, a, extra)
    node = cells["node"].to_numpy()
    rows, cols, vals = [], [], []
    for j, ent in enumerate(spaces["entrances"]):
        d = net.dist_at(ent, lim[j], node)
        ok = np.isfinite(d)
        rows.append(np.where(ok)[0])
        cols.append(np.full(ok.sum(), j))
        vals.append(d[ok] + 1.0)
    r, c, v = np.concatenate(rows), np.concatenate(cols), np.concatenate(vals)
    return sp.csr_matrix((v, (r, c)), shape=(len(cells), len(spaces)))


def _pairs(D: sp.csr_matrix, mask: np.ndarray):
    C = D.tocoo()
    keep = mask[C.col]
    return C.row[keep], C.col[keep], C.data[keep] - 1.0


def gravity(D, S, mask, alpha, beta, kind, a) -> np.ndarray:
    i, j, d = _pairs(D, mask)
    R = radius(S, beta, a)
    w = np.power(S[j], alpha) * decay(d, R[j], kind, a)
    return np.bincount(i, weights=w, minlength=D.shape[0])


def g2sfca(D, S, mask, P, beta, kind, a) -> np.ndarray:
    i, j, d = _pairs(D, mask)
    R = radius(S, beta, a)
    f = decay(d, R[j], kind, a)
    demand = np.bincount(j, weights=P[i] * f, minlength=D.shape[1])
    # 수요 0인 공간(닿는 인구 없음)은 비율 0 — 누구의 값에도 들어가지 않는다
    ratio = np.divide(S, demand, out=np.zeros_like(S), where=demand > 0)
    return np.bincount(i, weights=ratio[j] * f, minlength=D.shape[0])


def cover(D, S, mask, limit_m: float, min_area: float) -> np.ndarray:
    i, j, d = _pairs(D, mask & (S >= min_area))
    ok = d <= limit_m
    out = np.zeros(D.shape[0])
    out[np.unique(i[ok])] = 1.0
    return out
