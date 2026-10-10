"""성격 모드 (SPEC 9.10): 표본 지표를 지역의 지문으로 보고 유형으로 묶는다. 좋고 나쁨을 매기지 않는다.

1 시연 라이브러리: 대상 지역 셀에서 10분 권역의 맥락 변수(밀도, 주간/야간 비) 3분위로 9층 → 층마다 4개 무작위
2 표준화(z 또는 순위) → PCA(누적 설명 분산 기준) → k-평균, k는 실루엣 최대(동점이면 작은 k). 규칙은 params에 사전 고정
3 유형 이름은 A, B, C… (평가 형용사 금지). 프로필 = 지표별 평균·범위
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import h3
import numpy as np
import pandas as pd
from pyproj import Transformer
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score

from .config import params, params_hash, region_dirs
from .export import load_region
from .sample import aggregate, walkshed_cells


def build_demo(region_id: str) -> None:
    prm = params()
    pc = prm["personality"]
    dc = pc["demo_library"]
    cells, cm, spaces, net, cats, rows = load_region(region_id)
    a = prm["access"]
    lens = {"definition": prm["open_space"]["default_definition"], "decay": a["default_decay"],
            "alpha": a["default_alpha"], "beta": a["default_beta"]}
    node = cells["node"].to_numpy()
    cand = np.where(cells["in_target"].to_numpy() & (node >= 0))[0]
    speed = prm["walk"]["speed_mps"]
    mins = dc["walk_minutes"]

    # 1. 후보 셀마다 10분 권역의 층화 변수
    pop_n = cells["pop_night"].fillna(0).to_numpy()
    pop_d = cells["pop_day"].fillna(0).to_numpy()
    land = cells["land_m2"].to_numpy()
    strata_vals = []
    sheds = {}
    for ci in cand:
        idx = walkshed_cells(net, node, int(node[ci]), mins, speed)
        sheds[ci] = idx
        pn, pd_, la = pop_n[idx].sum(), pop_d[idx].sum(), land[idx].sum()
        strata_vals.append((pn / (la / 1e4) if la else np.nan, pd_ / pn if pn else np.nan))
    sv = pd.DataFrame(strata_vals, columns=dc["strata"], index=cand).dropna()
    rng = np.random.default_rng(dc["random_state"])
    q = {c: pd.qcut(sv[c], 3, labels=False) for c in dc["strata"]}
    sv["stratum"] = q[dc["strata"][0]] * 3 + q[dc["strata"][1]]
    per = dc["n_samples"] // 9
    picks = []
    for s in range(9):
        pool = sv.index[sv["stratum"] == s].to_numpy()
        picks += list(rng.choice(pool, size=min(per, len(pool)), replace=False))

    # 2. 표본 지표 (9.5 구조)
    to_wgs = Transformer.from_crs(cells.crs, "EPSG:4326", always_xy=True)
    lon_all, lat_all = to_wgs.transform(net.x, net.y)
    samples = []
    created = datetime.now(UTC).isoformat(timespec="seconds")
    for k, ci in enumerate(picks, 1):
        idx = sheds[ci]
        m = aggregate(idx, cells, cm, rows, lens, prm)
        nd = int(node[ci])
        shape = h3.cells_to_h3shape([cells["h3"].iloc[i] for i in idx])
        gj = shape.__geo_interface__
        samples.append({
            "id": f"demo_{k:03d}", "name": f"시연 {k:02d} (층 {int(sv.loc[ci, 'stratum']) + 1})", "region": region_id,
            "point": [round(float(lon_all[nd]), 6), round(float(lat_all[nd]), 6)], "walk_minutes": mins,
            "walkshed": gj, "created": created, "params_hash": params_hash(), "lens": lens,
            "metrics": {k2: v for k2, v in m.items() if not k2.startswith(("ctx_", "places_"))},
            "context": {k2: v for k2, v in m.items() if k2.startswith("ctx_")},
            "labels": {k2: v for k2, v in m.items() if k2.startswith("places_")},
            "notes": f"층화 추출: {dc['strata'][0]} 3분위 {int(q[dc['strata'][0]][ci]) + 1}, {dc['strata'][1]} 3분위 {int(q[dc['strata'][1]][ci]) + 1}",
        })

    # 3. 군집
    model = cluster([s["metrics"] for s in samples], pc)
    for s, t in zip(samples, model.pop("assign_by_index"), strict=True):
        s["type"] = t
        model["assignment"][s["id"]] = t
    out = region_dirs(region_id)["web"]
    (out / "demo_library.json").write_text(json.dumps({"format": "gyeol-library", "version": 1, "samples": samples},
                                                      ensure_ascii=False, separators=(",", ":"), default=_num))
    (out / "personality.json").write_text(json.dumps(model, ensure_ascii=False, indent=1, default=_num))
    print(f"demo samples {len(samples)}, k={model['k']}, silhouette={model['silhouette'][str(model['k'])]:.3f}")


def _num(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    raise TypeError(type(o))


def cluster(metric_dicts: list[dict], pc: dict) -> dict:
    feats = pc["features"]
    X = pd.DataFrame([{f: m.get(f) for f in feats} for m in metric_dicts], dtype=float)
    ok = X.notna().all(axis=1).to_numpy()
    Xo = X[ok].to_numpy()
    if pc["standardize"] == "rank":
        Z = pd.DataFrame(Xo).rank(pct=True).to_numpy()
        mean, std = None, None
    else:
        mean = Xo.mean(axis=0)
        std = Xo.std(axis=0)
        std[std == 0] = 1.0
        Z = (Xo - mean) / std
    pca = PCA(n_components=pc["pca_variance"], svd_solver="full", random_state=pc["random_state"]).fit(Z)
    P = pca.transform(Z)
    sil = {}
    fits = {}
    for k in range(pc["k_min"], pc["k_max"] + 1):
        if k >= len(P):
            break
        km = KMeans(n_clusters=k, n_init=pc["n_init"], random_state=pc["random_state"]).fit(P)
        sil[str(k)] = float(silhouette_score(P, km.labels_))
        fits[k] = km
    best = max(sil.values())
    k = min(int(x) for x, v in sil.items() if np.isclose(v, best))   # 동점이면 작은 k
    km = fits[k]
    # 유형 이름: 크기 순서가 아니라 첫 주성분 값 순서로 A, B, C… (이름에 가치가 실리지 않게 순서만)
    order = np.argsort(km.cluster_centers_[:, 0])
    name = {int(c): chr(65 + r) for r, c in enumerate(order)}
    labels = [name[int(c)] for c in km.labels_]
    assign = [None] * len(metric_dicts)
    for i, lab in zip(np.where(ok)[0], labels, strict=True):
        assign[i] = lab
    profiles = {}
    for t in sorted(set(labels)):
        rows = Xo[np.array(labels) == t]
        profiles[t] = {f: {"mean": float(rows[:, j].mean()), "min": float(rows[:, j].min()), "max": float(rows[:, j].max())}
                       for j, f in enumerate(feats)}
        profiles[t]["n"] = int(len(rows))
    centers = {name[int(c)]: km.cluster_centers_[c].tolist() for c in range(k)}
    return {
        "features": feats, "standardize": pc["standardize"],
        "mean": None if mean is None else mean.tolist(), "std": None if std is None else std.tolist(),
        "pca_components": pca.components_.tolist(), "pca_mean": pca.mean_.tolist(),
        "pca_explained": pca.explained_variance_ratio_.tolist(),
        "k": k, "silhouette": sil, "centers": centers, "profiles": profiles,
        "n_samples": int(len(metric_dicts)), "n_clustered": int(ok.sum()),
        "rule": f"k ∈ [{pc['k_min']}, {pc['k_max']}] 중 실루엣 최대, 동점이면 작은 k. PCA 누적 설명 분산 {pc['pca_variance']}",
        "assignment": {}, "assign_by_index": assign,
    }
