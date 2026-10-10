"""셀 단위 지표 중 네트워크가 필요한 것: 접근성 렌즈 전부, 일상 시설 보행 시간, POI 범주 개수."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd

from .access import cover, g2sfca, gravity

DEFS = ["green_only", "with_plaza_playground", "with_pops"]


def lens_key(kind: str, d: str, decay: str = "", alpha=None, beta=None, demand: str = "") -> str:
    parts = [kind, d]
    if decay:
        parts.append(decay)
    if alpha is not None:
        parts.append(f"a{alpha}")
    if beta is not None:
        parts.append(f"b{beta}")
    if demand:
        parts.append(demand)
    return "|".join(parts)


def access_lenses(cells: pd.DataFrame, spaces: pd.DataFrame, D, prm: dict) -> dict[str, np.ndarray]:
    a = prm["access"]
    S = spaces["area_m2"].to_numpy(float)
    walk = prm["walk"]
    P = {"night": cells["pop_night"].fillna(0).to_numpy(float), "day": cells["pop_day"].fillna(0).to_numpy(float)}
    out = {}
    for d in DEFS:
        mask = spaces[f"def_{d}"].to_numpy(bool)
        for decay in a["decays"]:
            for beta in a["betas"]:
                for alpha in a["alphas"]:
                    out[lens_key("os_gravity", d, decay, alpha, beta)] = gravity(D, S, mask, alpha, beta, decay, a)
                for dem in a["demand"]:
                    out[lens_key("os_g2sfca", d, decay, None, beta, dem)] = g2sfca(D, S, mask, P[dem], beta, decay, a)
        for m in a["cover_minutes"]:
            out[lens_key(f"os_cover_{m}", d)] = cover(D, S, mask, m * 60 * walk["speed_mps"], prm["open_space"]["min_area_m2"])
    return out


def daily_amenity_times(cells, pois: gpd.GeoDataFrame | None, net, prm) -> dict[str, np.ndarray]:
    """일상 필수 시설 범주별 가장 가까운 곳까지 보행 분. 한계 밖은 cutoff 값."""
    am = prm["amenity"]
    cut = am["daily_cutoff_minutes"]
    out = {}
    if pois is None or not len(pois):
        for cat in am["daily_categories"]:
            out[f"t_{cat}"] = np.full(len(cells), np.nan)
        return out
    tree = net.kdtree()
    speed = prm["walk"]["speed_mps"]
    node = cells["node"].to_numpy()
    for cat, rule in am["daily_categories"].items():
        sel = np.zeros(len(pois), dtype=bool)
        for key, vals in rule.items():
            sel |= (pois["key"] == key).to_numpy() & pois["value"].isin(vals).to_numpy()
        p = pois[sel]
        if not len(p):
            out[f"t_{cat}"] = np.full(len(cells), np.nan)
            continue
        _, k = tree.query(np.c_[p.geometry.x, p.geometry.y])
        dist = net.dist_at(k, cut * 60 * speed, node)
        out[f"t_{cat}"] = np.minimum(dist / speed / 60, cut)
    return out


def poi_counts(cells: gpd.GeoDataFrame, pois: gpd.GeoDataFrame | None) -> tuple[list[str], list[list[int]]]:
    """셀별 POI 범주 개수 (희소: [범주 인덱스, 개수, ...])."""
    if pois is None or not len(pois):
        return [], [[] for _ in range(len(cells))]
    cat = (pois["key"] + "=" + pois["value"].astype(str)).to_numpy()
    j = gpd.sjoin(gpd.GeoDataFrame({"cat": cat}, geometry=pois.geometry, crs=pois.crs), cells[["geometry"]], predicate="within")
    cats = sorted(j["cat"].unique())
    idx = {c: i for i, c in enumerate(cats)}
    out: list[list[int]] = [[] for _ in range(len(cells))]
    for (cell, c), n in j.groupby(["index_right", "cat"]).size().items():
        out[int(cell)] += [idx[c], int(n)]
    return cats, out


def compute_cell_metrics(cells, spaces, D, net, L, prm) -> pd.DataFrame:
    lenses = access_lenses(cells, spaces, D, prm)
    pois = gpd.read_parquet(L / "pois.parquet") if (L / "pois.parquet").exists() else None
    t = daily_amenity_times(cells, pois, net, prm)
    df = pd.DataFrame({**lenses, **{f"amen_{k}": v for k, v in t.items()}})
    df.loc[cells["node"].to_numpy() < 0, :] = np.nan   # 보행망 밖 셀: 데이터 없음
    df.insert(0, "h3", cells["h3"].values)
    return df
