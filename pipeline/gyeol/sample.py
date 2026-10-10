"""표본 = 보행 권역(walkshed) 안 셀들의 가산 통계를 합쳐 지표를 다시 만든 것 (SPEC 9.5, 9.8).

웹 워커(web/src/engine.ts)가 같은 알고리즘을 TypeScript로 구현하고, 교차 검증(make xval)이 둘을 비교한다.
권역 규칙: 클릭 지점에서 가장 가까운 보행 노드에서 출발, 셀의 대표 노드까지 네트워크 거리 ≤ 분×60×속도 인 셀.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .metrics.cellmetrics import lens_key


def walkshed_cells(net, cell_node: np.ndarray, start_node: int, minutes: float, speed: float) -> np.ndarray:
    lim = minutes * 60 * speed
    d = net.dist_at([start_node], lim, cell_node)
    return np.where(d <= lim)[0]


def _div(a, b):
    return None if b is None or b == 0 or a is None or not np.isfinite(b) else float(a / b)


def entropy(counts) -> float | None:
    c = np.asarray([x for x in counts if x > 0], float)
    if c.sum() == 0:
        return None
    p = c / c.sum()
    return float(-(p * np.log(p)).sum())


def aggregate(idx: np.ndarray, cells: pd.DataFrame, cm: pd.DataFrame, poi_rows: list[list[int]], lens: dict, prm: dict) -> dict:
    """lens: definition, decay, alpha, beta. 반환: 지표 ID → 값 (없으면 None)."""
    c = cells.iloc[idx]
    m = cm.iloc[idx]
    d = lens["definition"]
    variant = "pops" if d == "with_pops" else "base"
    res = prm["raster"]["resolution_m"]
    out: dict = {}
    s = lambda col: float(c[col].fillna(0).sum()) if col in c.columns else None  # noqa: E731

    # 공공공간
    def mean(col):
        return float(m[col].mean()) if len(m) else None
    out["os_gravity"] = mean(lens_key("os_gravity", d, lens["decay"], lens["alpha"], lens["beta"]))
    out["os_g2sfca_night"] = mean(lens_key("os_g2sfca", d, lens["decay"], None, lens["beta"], "night"))
    out["os_g2sfca_day"] = mean(lens_key("os_g2sfca", d, lens["decay"], None, lens["beta"], "day"))
    pop = c["pop_night"].fillna(0).to_numpy()
    for mins in prm["access"]["cover_minutes"]:
        cov = m[lens_key(f"os_cover_{mins}", d)].to_numpy()
        out[f"os_cover_{mins}"] = _div(float((pop * cov).sum()), float(pop.sum()))
    green = s("a_open_free_green_m2") + (s("a_pops_green_m2") if variant == "pops" else 0)
    opena = s("a_open_free_m2") + (s("a_pops_m2") if variant == "pops" else 0)
    out["os_greenness"] = _div(green, opena)

    # 결
    pre = f"g_{variant}_{res}_"
    nP, nQ, nV = s(pre + "nP"), s(pre + "nQ"), s(pre + "nV")
    ground = nP + nQ + nV
    out["nolli_ratio"] = _div(nP, ground)
    out["edge_density"] = _div(s(pre + "PQ") * res, ground * res * res / 1e4)
    ms = []
    for r in prm["raster"]["multiscale_m"]:
        p = f"g_{variant}_{r}_"
        ms.append(interspersion(s(p + "nP"), s(p + "nQ"), s(p + "PP"), s(p + "PQ"), s(p + "QQ")))
    out["interspersion"] = ms[0]
    out["grain_multiscale"] = ms if all(x is not None for x in ms) else None
    out["largest_public_patch"] = float(c[f"patch_{variant}_max_m2"].max()) if len(c) else None

    # 가로
    sl = s("street_len_m") if "street_len_m" in c.columns else 0
    sw, rw = s("a_sidewalk_m2"), s("a_roadway_m2")
    out["sidewalk_width"] = _div(sw, sl * prm["streets"]["sides"]) if sl else None
    land_ha = s("land_m2") / 1e4
    demand = (s("pop_night") or 0) + (s("pop_day") or 0)
    dens = _div(demand, land_ha)
    out["sidewalk_adequacy"] = _div(out["sidewalk_width"], dens) if out["sidewalk_width"] is not None else None
    out["lane_share"] = _div(rw, rw + sw)
    hmean = _div(s("bldg_street_ha_m3"), s("bldg_street_a_m2")) if "bldg_street_a_m2" in c.columns else None
    row_w = _div(rw + sw, sl) if sl else None
    out["enclosure"] = _div(row_w, hmean) if row_w is not None else None
    out["frontage_permeability"] = None   # 1차 버전 비워둠 (SPEC 9.3)

    # 근접성
    tcols = [col for col in m.columns if col.startswith("amen_t_")]
    if tcols and m[tcols].notna().all(axis=None):
        out["amenity_daily"] = float(m[tcols].max(axis=1).mean())
    else:
        out["amenity_daily"] = None
    tot: dict[int, int] = {}
    for i in idx:
        row = poi_rows[i]
        for k in range(0, len(row), 2):
            tot[row[k]] = tot.get(row[k], 0) + row[k + 1]
    out["amenity_diversity"] = entropy(tot.values())

    # 맥락 (평가 아님)
    out["ctx_density"] = _div(s("pop_night"), land_ha)
    lu = [col for col in cells.columns if col.startswith("lu_")]
    if lu:
        h = entropy([s(col) for col in lu])
        out["ctx_landuse_mix"] = None if h is None else h / math.log(len(lu))
    else:
        out["ctx_landuse_mix"] = None
    has_day = "pop_day" in cells.columns and bool(cells["pop_day"].notna().any())   # 지역 전체에 주간 데이터가 있는가
    out["ctx_daytime_ratio"] = _div(s("pop_day"), s("pop_night")) if has_day else None
    if "income" in c.columns:
        ok = c["income"].notna().to_numpy() & (pop > 0)
        out["ctx_income"] = _div(float((c["income"].to_numpy()[ok] * pop[ok]).sum()), float(pop[ok].sum()))
    else:
        out["ctx_income"] = None
    # 외부 라벨: 땅 면적 가중
    for col in [x for x in c.columns if x.startswith("places_")]:
        ok = c[col].notna().to_numpy()
        w = c["land_m2"].to_numpy()
        out[col] = _div(float((c[col].to_numpy()[ok] * w[ok]).sum()), float(w[ok].sum()))
    return out


def interspersion(nP, nQ, PP, PQ, QQ):
    """관측 공공-사적 이웃 쌍 비율 / 무작위 기대 2p(1-p). 1 = 무작위로 섞임, 0 = 완전히 분리."""
    tot = nP + nQ
    pairs = PP + PQ + QQ
    if tot == 0 or pairs == 0:
        return None
    p = nP / tot
    exp = 2 * p * (1 - p)
    if exp == 0:
        return None
    return float((PQ / pairs) / exp)
