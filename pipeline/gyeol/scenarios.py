"""시나리오 실험실 (SPEC 9.9) — 추상 격자 도시에서 배치만 바꿔 원리를 검사한다.

총 공공공간 면적은 모든 배치에서 정확히 같다. 실제 도시와 **같은 함수**(출입구, 다익스트라, 감쇠, 2SFCA, 래스터 결 지표)를 쓴다.
배치: C 집중형(1개) · M 중간(4개) · D 분산형(포켓 N개) · X 혼합형(큰 것 2개 + 그린웨이 + 포켓)
"""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import scipy.sparse as sp
from shapely.geometry import box

from .config import ROOT, params, params_hash
from .metrics.access import cover, g2sfca, gravity, max_reach
from .network import Network, edges_to_network, entrances
from .raster import Grid, classify, coarsen_mode, grain_counts, patch_max_area
from .sample import interspersion

LETTER = {"concentrated": "C", "medium": "M", "dispersed": "D", "mixed": "X"}


@dataclass
class City:
    n: int
    block: float
    street: float
    pitch: float
    size: float

    def block_box(self, i: int, j: int):
        x0 = self.street + i * self.pitch
        y0 = self.street + j * self.pitch
        return box(x0, y0, x0 + self.block, y0 + self.block)

    def block_center(self, i: int, j: int):
        return (self.street + i * self.pitch + self.block / 2, self.street + j * self.pitch + self.block / 2)


def make_city(cfg) -> City:
    pitch = cfg["block_m"] + cfg["street_m"]
    n = cfg["city_size_blocks"]
    return City(n, cfg["block_m"], cfg["street_m"], pitch, n * pitch + cfg["street_m"])


def _square(cx, cy, area):
    h = np.sqrt(area) / 2
    return box(cx - h, cy - h, cx + h, cy + h)


def layout(name: str, city: City, cfg) -> list[dict]:
    total = cfg["open_space_share"] * city.n * city.n * city.block ** 2
    S = city.size
    if name == "concentrated":
        return [{"geom": _square(S / 2, S / 2, total), "role": "big"}]
    if name == "medium":
        k = int(round(np.sqrt(cfg["medium_count"])))
        a = total / (k * k)
        return [{"geom": _square(S * (i + 0.5) / k, S * (j + 0.5) / k, a), "role": "medium"} for i in range(k) for j in range(k)]
    if name == "dispersed":
        k = int(round(np.sqrt(cfg["dispersed_count"])))
        a = total / (k * k)
        step = city.n // k
        idx = [step * t + step // 2 for t in range(k)]
        return [{"geom": _square(*city.block_center(i, j), a), "role": "pocket"} for i in idx for j in idx]
    if name == "mixed":
        m = cfg["mixed"]
        big_a = total * m["big_share"] / m["big_count"]
        side = np.sqrt(big_a)
        cx = [S * (t + 0.5) / m["big_count"] for t in range(m["big_count"])]
        out = [{"geom": _square(x, S / 2, big_a), "role": "big"} for x in cx]
        gw_a = total * m["greenway_share"]
        gap_x0, gap_x1 = cx[0] + side / 2, cx[-1] - side / 2
        w = gw_a / (gap_x1 - gap_x0)
        out.append({"geom": box(gap_x0, S / 2 - w / 2, gap_x1, S / 2 + w / 2), "role": "greenway"})
        pa = total * (1 - m["big_share"] - m["greenway_share"]) / m["pocket_count"]
        k = int(round(np.sqrt(m["pocket_count"])))
        step = city.n // k
        want = [(step * a + step // 2, step * b + step // 2) for a in range(k) for b in range(k)]
        taken = [o["geom"] for o in out]
        used = set()
        for (i, j) in want:
            ii, jj = _nearest_free_block(city, i, j, taken, used, pa)
            used.add((ii, jj))
            g = _square(*city.block_center(ii, jj), pa)
            taken.append(g)
            out.append({"geom": g, "role": "pocket"})
        return out
    raise ValueError(name)


def _nearest_free_block(city, i, j, taken, used, area):
    cand = sorted((abs(a - i) + abs(b - j), a, b) for a in range(city.n) for b in range(city.n))
    for _, a, b in cand:
        if (a, b) in used:
            continue
        g = _square(*city.block_center(a, b), area)
        if not any(g.buffer(city.street).intersects(t) for t in taken):
            return a, b
    raise RuntimeError("no free block")


def build_network(city: City, spacing: float, barrier_geoms=None) -> tuple[Network, np.ndarray]:
    """가로 중심선 격자 위에 spacing 간격 노드. barrier면 공간 내부 노드를 지운다."""
    lines = [city.street / 2 + t * city.pitch for t in range(city.n + 1)]
    pts = {}
    edges = {}

    def nid(x, y):
        key = (round(x, 3), round(y, 3))
        if key not in pts:
            pts[key] = len(pts)
        return pts[key]

    for fixed in lines:
        for horiz in (True, False):
            coords = np.arange(lines[0], lines[-1] + 1e-6, spacing)
            coords = np.unique(np.r_[coords, lines])
            prev = None
            for c in coords:
                x, y = (c, fixed) if horiz else (fixed, c)
                k = nid(x, y)
                if prev is not None:
                    a, b = min(prev[0], k), max(prev[0], k)
                    edges[(a, b)] = float(abs(c - prev[1]))
                prev = (k, c)
    xy = np.array(list(pts.keys()))
    keep = np.ones(len(xy), bool)
    if barrier_geoms:
        from shapely import contains_xy
        for g in barrier_geoms:
            keep &= ~contains_xy(g.buffer(-1.0), xy[:, 0], xy[:, 1])
    remap = -np.ones(len(xy), int)
    remap[keep] = np.arange(keep.sum())
    e2 = {(int(remap[a]), int(remap[b])): w for (a, b), w in edges.items() if keep[a] and keep[b]}
    return edges_to_network(xy[keep, 0], xy[keep, 1], e2), xy[keep]


def cell_side_nodes(city: City, xy: np.ndarray) -> np.ndarray:
    """블록마다 네 변 가운데의 가로 노드 (없으면 -1)."""
    idx = {(round(x, 3), round(y, 3)): k for k, (x, y) in enumerate(xy)}
    out = -np.ones((city.n * city.n, 4), int)
    for i in range(city.n):
        for j in range(city.n):
            cx, cy = city.block_center(i, j)
            h = city.pitch / 2
            for s, (x, y) in enumerate(((cx - h, cy), (cx + h, cy), (cx, cy - h), (cx, cy + h))):
                out[i * city.n + j, s] = idx.get((round(x, 3), round(y, 3)), -1)
    return out


def residential(city: City, spaces: list[dict], cfg, opportunity_cost: bool) -> np.ndarray:
    """블록별 인구. 공간이 덮은 만큼 주거 부지가 줄어든다."""
    union = gpd.GeoSeries([s["geom"] for s in spaces]).union_all()
    base = cfg["density_per_ha"] * city.block ** 2 / 1e4
    left = np.array([city.block_box(i, j).difference(union).area / city.block ** 2
                     for i in range(city.n) for j in range(city.n)])
    if not opportunity_cost:
        # 기회비용 없음: 공간이 주거를 밀어내지 않는다 — 인구 분포가 공간 없는 도시와 같다
        # (run-001은 밀려난 인구를 비례 재배분해서 인구 가중 평균이 기회비용 있음과 똑같아지는 버그가 있었다)
        return np.full(city.n * city.n, base)
    return base * left


def cell_space_dist(net: Network, side: np.ndarray, spaces_gdf, limits) -> sp.csr_matrix:
    ent, _ = entrances(spaces_gdf, net, 50.0, 40.0)
    rows, cols, vals = [], [], []
    for j, e in enumerate(ent):
        d = net.dist_from(e, limits[j])
        ds = np.where(side >= 0, d[np.maximum(side, 0)], np.inf).min(axis=1)
        ok = np.isfinite(ds)
        rows.append(np.where(ok)[0])
        cols.append(np.full(ok.sum(), j))
        vals.append(ds[ok] + 1.0)
    r, c, v = map(np.concatenate, (rows, cols, vals))
    return sp.csr_matrix((v, (r, c)), shape=(side.shape[0], len(spaces_gdf)))


def wquantile(x, w, q):
    o = np.argsort(x)
    cw = np.cumsum(w[o])
    if cw[-1] == 0:
        return float("nan")
    return float(x[o][np.searchsorted(cw, q * cw[-1])])


def grain_stats(city: City, spaces: list[dict], cfg, prm) -> dict:
    res = prm["raster"]["resolution_m"]
    from affine import Affine
    w = int(np.ceil(city.size / res))
    grid = Grid(Affine(res, 0, 0, 0, -res, w * res), w, w, res)
    S = city.size
    land = box(0, 0, S, S)
    streets_all = land.difference(gpd.GeoSeries([city.block_box(i, j) for i in range(city.n) for j in range(city.n)]).union_all())
    sw = cfg["sidewalk_m"]
    roads = streets_all.buffer(-sw)
    sidewalks = streets_all.difference(roads)
    sp_gdf = gpd.GeoDataFrame({"kind": "park", "access": "free", "area_m2": [s["geom"].area for s in spaces]},
                              geometry=[s["geom"] for s in spaces])
    cls = classify(grid, land, gpd.GeoDataFrame(geometry=[roads]), gpd.GeoDataFrame(geometry=[sidewalks]), sp_gdf)
    lbl = np.where(cls > 0, 1, 0).astype(np.int32)
    out = {}
    for r in prm["raster"]["multiscale_m"]:
        f = int(round(r / res))
        c = coarsen_mode(cls, f)
        lb = coarsen_mode(lbl.astype(np.uint8), f).astype(np.int32)
        g = {k: float(v[0]) for k, v in grain_counts(c, lb, 1, "base").items()}
        if r == res:
            ground = g["nP"] + g["nQ"] + g["nV"]
            out["nolli_ratio"] = g["nP"] / ground
            out["edge_density"] = g["PQ"] * res / (ground * res * res / 1e4)
        out[f"interspersion_{r}"] = interspersion(g["nP"], g["nQ"], g["PP"], g["PQ"], g["QQ"])
    out["largest_public_patch"] = float(patch_max_area(cls, lbl, 1, "base", res)[0])
    edge = prm["scenarios"]["proxies"]["environment_edge_m"]
    union = gpd.GeoSeries([s["geom"] for s in spaces]).union_all()
    out["proxy_environment"] = union.buffer(-edge).area / 1e4
    out["_cls"] = cls
    return out


def evaluate(name: str, city: City, cfg, prm, *, opportunity_cost: bool, barrier: bool, cache: dict) -> list[dict]:
    """한 배치·한 (기회비용, 장벽) 조건에서 α·β·감쇠·혼잡 스윕 전체."""
    spaces = layout(name, city, cfg)
    geoms = [s["geom"] for s in spaces]
    net, xy = build_network(city, cfg["node_spacing_m"], geoms if barrier else None)
    side = cell_side_nodes(city, xy)
    gdf = gpd.GeoDataFrame({"area_m2": [g.area for g in geoms]}, geometry=geoms)
    S = gdf["area_m2"].to_numpy()
    a = dict(prm["access"])
    a["betas"] = cfg["sweep"]["betas"]
    px = cfg["proxies"]
    lim = max_reach(S, a, max(px["restoration_reach_m"], max(a["cover_minutes"]) * 60 * prm["walk"]["speed_mps"]))
    D = cell_space_dist(net, side, gdf, lim)
    P = residential(city, spaces, cfg, opportunity_cost)
    allm = np.ones(len(S), bool)
    big_act = S >= px["activity_min_area_m2"]
    big_rest = S >= px["restoration_min_area_m2"]
    rows = []
    cover5 = cover(D, S, allm, 5 * 60 * prm["walk"]["speed_mps"], 0)
    rest = cover(D, S, big_rest, px["restoration_reach_m"], 0)
    Dc = D.tocoo()
    near = (Dc.data - 1) <= px["social_reach_m"]
    social = np.bincount(Dc.row[near], minlength=D.shape[0])
    wmean = lambda v: float((v * P).sum() / P.sum())  # noqa: E731
    for decay, beta, alpha, cong in itertools.product(cfg["sweep"]["decays"], cfg["sweep"]["betas"],
                                                     cfg["sweep"]["alphas"], cfg["sweep"]["congestion"]):
        if cong:
            acc = g2sfca(D, S, allm, P, beta, decay, a)
            act = g2sfca(D, S, big_act, P, beta, decay, a) if big_act.any() else np.zeros(len(P))
        else:
            acc = gravity(D, S, allm, alpha, beta, decay, a)
            act = gravity(D, S, big_act, alpha, beta, decay, a) if big_act.any() else np.zeros(len(P))
        rows.append({
            "layout": name, "decay": decay, "beta": beta, "alpha": alpha, "congestion": cong,
            "opportunity_cost": opportunity_cost, "barrier": barrier,
            "access_mean": wmean(acc), "access_p10": wquantile(acc, P, 0.10),
            "proxy_activity": wmean(act), "proxy_restoration": wmean(rest), "proxy_social": wmean(social),
            "os_cover_5": wmean(cover5), "population": float(P.sum()), "total_area_m2": float(S.sum()),
            "n_spaces": len(S),
        })
    if name not in cache:
        cache[name] = grain_stats(city, spaces, cfg, prm)
    g = {k: v for k, v in cache[name].items() if not k.startswith("_")}
    for r in rows:
        r.update(g)
        r["proxy_equity"] = r["access_p10"]
    return rows


def run_sweep(prm=None) -> pd.DataFrame:
    prm = prm or params()
    cfg = prm["scenarios"]
    city = make_city(cfg)
    rows, cache = [], {}
    for name in cfg["layouts"]:
        for oc, bar in itertools.product(cfg["sweep"]["opportunity_cost"], cfg["sweep"]["park_barrier"]):
            rows += evaluate(name, city, cfg, prm, opportunity_cost=oc, barrier=bar, cache=cache)
    df = pd.DataFrame(rows)
    df.attrs["cache"] = cache
    df.attrs["city"] = city
    return df


# ---------------------------------------------------------------- 보고서

AXES = ["decay", "congestion", "opportunity_cost", "barrier"]
OUTCOMES = {
    "access_mean": "접근성 평균 (혼잡 없음 = os_gravity, 혼잡 = os_g2sfca, 인구 가중)",
    "proxy_equity": "공정성: 접근성 하위 10% 값",
    "proxy_activity": "신체 활동: 1 ha 이상 공간만의 접근성",
    "proxy_restoration": "정신적 회복: 5 ha 이상 공간 1.2 km 안 인구 비율",
    "proxy_social": "사회적 연결: 5분 안 공간 수",
    "os_cover_5": "5분 안 공공공간 인구 비율",
}


def winners(df: pd.DataFrame, col: str) -> pd.DataFrame:
    keys = ["decay", "beta", "alpha", "congestion", "opportunity_cost", "barrier"]
    piv = df.pivot_table(index=keys, columns="layout", values=col)
    best = piv.max(axis=1)
    win = piv.apply(lambda r: "".join(sorted(LETTER[c] for c in piv.columns if np.isclose(r[c], best[r.name], rtol=1e-6))), axis=1)
    out = piv.copy()
    out["winner"] = win
    out["D_over_C"] = piv["dispersed"] / piv["concentrated"]
    return out.reset_index()


def run_all() -> None:
    prm = params()
    df = run_sweep(prm)
    out_dir = ROOT / "reports"
    fig_dir = out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    run = prm["run_id"]
    df.to_csv(out_dir / f"scenarios_{run}.csv", index=False)
    write_report(df, prm, out_dir, fig_dir)
    export_web(df, prm)


def export_web(df: pd.DataFrame, prm: dict) -> None:
    """웹 '실험' 칸용: 배치 그림 4장 + 조건별 값 (가우시안 감쇠, 혼잡 없음/있음)."""
    from PIL import Image

    from .config import WEB_DATA
    out = WEB_DATA / "scenarios"
    out.mkdir(parents=True, exist_ok=True)
    cache = df.attrs["cache"]
    for name, g in cache.items():
        c = g["_cls"]
        # 값 = 클래스 코드 (웹이 테마 색으로 칠함)
        Image.fromarray(c.astype(np.uint8), mode="L").save(out / f"{name}.png", optimize=True)
    sel = df[df.decay == "gaussian"]
    rows = []
    for _, r in sel.iterrows():
        rows.append({k: (bool(r[k]) if k in ("congestion", "opportunity_cost", "barrier") else
                         r[k] if k == "layout" else float(r[k]))
                     for k in ("layout", "alpha", "beta", "congestion", "opportunity_cost", "barrier",
                               "access_mean", "access_p10", "os_cover_5", "proxy_restoration", "proxy_social")})
    first = df.drop_duplicates("layout").set_index("layout")
    layouts = {n: {"n_spaces": int(first.loc[n, "n_spaces"]), "total_ha": float(first.loc[n, "total_area_m2"]) / 1e4,
                   "largest_patch_ha": float(first.loc[n, "largest_public_patch"]) / 1e4,
                   "edge_density": float(first.loc[n, "edge_density"])} for n in cache}
    (out / "scenarios.json").write_text(json.dumps({
        "run_id": prm["run_id"], "params_hash": params_hash(), "layouts": layouts, "rows": rows,
        "city": {k: prm["scenarios"][k] for k in ("city_size_blocks", "block_m", "street_m", "density_per_ha", "open_space_share")},
    }, ensure_ascii=False, separators=(",", ":")))


def _grid_table(w: pd.DataFrame, fixed: dict, value: str = "winner") -> list[str]:
    sub = w
    for k, v in fixed.items():
        sub = sub[sub[k] == v]
    alphas = sorted(sub["alpha"].unique())
    betas = sorted(sub["beta"].unique())
    lines = ["| α \\ β | " + " | ".join(f"{b:g}" for b in betas) + " |", "| --- |" + " :---: |" * len(betas)]
    for a in alphas:
        cells = []
        for b in betas:
            r = sub[(sub["alpha"] == a) & (sub["beta"] == b)]
            if not len(r):
                cells.append("")
                continue
            r = r.iloc[0]
            cells.append(f"{r['winner']} · {r['D_over_C']:.2f}" if value == "winner" else f"{r[value]:.2f}")
        lines.append(f"| {a:g} | " + " | ".join(cells) + " |")
    return lines


def flip_boundaries(w: pd.DataFrame) -> list[dict]:
    """각 (감쇠, 혼잡, 기회비용, 장벽, α)에서 β를 키울 때 D/C 비율이 1을 가로지르는 구간."""
    out = []
    for keys, g in w.groupby(["decay", "congestion", "opportunity_cost", "barrier", "alpha"]):
        g = g.sort_values("beta")
        r = g["D_over_C"].to_numpy()
        b = g["beta"].to_numpy()
        for k in range(len(r) - 1):
            # |D/C − 1| < 1e-6은 동률 (2SFCA 인구 가중 평균은 항등식으로 모든 배치에서 같다)
            lo, hi = r[k] - 1, r[k + 1] - 1
            if abs(lo) > 1e-6 and abs(hi) > 1e-6 and lo * hi < 0:
                out.append(dict(zip(["decay", "congestion", "opportunity_cost", "barrier", "alpha"], keys, strict=True))
                           | {"beta_low": b[k], "beta_high": b[k + 1], "ratio_low": r[k], "ratio_high": r[k + 1]})
    return out


def write_report(df: pd.DataFrame, prm: dict, out_dir: Path, fig_dir: Path) -> None:
    cfg = prm["scenarios"]
    city = df.attrs["city"]
    cache = df.attrs["cache"]
    figs = draw_layouts(cache, city, fig_dir)
    L = ["# 시나리오 실험실 결과 (M3)", "",
         f"run `{prm['run_id']}` · params_hash `{params_hash()}` · 원자료 `reports/scenarios_{prm['run_id']}.csv` ({len(df)}행)", "",
         "추상 격자 도시에서 **총 공공공간 면적을 고정**하고 배치만 바꾼 결과다. 결론을 내리지 않는다 — 어떤 조건에서 어떤 배치의 값이 큰지, "
         "그리고 그것이 **뒤집히는 경계**만 적는다. 가설과 반증 조건은 `HYPOTHESES.md`(실행 전 고정).", "",
         "## 도시와 배치", "",
         f"- {cfg['city_size_blocks']}×{cfg['city_size_blocks']} 블록, 블록 {cfg['block_m']} m, 가로 {cfg['street_m']} m(보도 {cfg['sidewalk_m']} m×2), "
         f"도시 한 변 {city.size:.0f} m, 보행 노드 간격 {cfg['node_spacing_m']} m",
         f"- 주거 밀도 {cfg['density_per_ha']} 인/ha(블록 면적), 총 공공공간 = 블록 면적 합의 {cfg['open_space_share']:.0%}", ""]
    base = df[(df.decay == "gaussian") & (df.beta == 0) & (df.alpha == 1.0) & (~df.congestion) & (~df.opportunity_cost) & (~df.barrier)]
    L += ["| 배치 | 공간 수 | 총 면적 (ha) | 인구(기회비용 없음) | nolli | 경계 밀도 (m/ha) | 혼재도 5/10/20/40 m | 최대 패치 (ha) | 핵심 면적 (ha) |",
          "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |"]
    for _, r in base.iterrows():
        ms = " / ".join(f"{r[f'interspersion_{m}']:.2f}" for m in prm["raster"]["multiscale_m"])
        L.append(f"| {LETTER[r['layout']]} {r['layout']} | {r['n_spaces']} | {r['total_area_m2'] / 1e4:.2f} | {r['population']:,.0f} | "
                 f"{r['nolli_ratio']:.3f} | {r['edge_density']:.1f} | {ms} | {r['largest_public_patch'] / 1e4:.2f} | {r['proxy_environment']:.2f} |")
    L += ["", *[f"![{f.stem}](figures/{f.name})" for f in figs], "",
          "결 지표(nolli·경계 밀도·혼재도·최대 패치·핵심 면적)는 α·β와 무관하다. 보도가 모든 배치에서 같으므로 nolli 차이는 작다.", ""]

    L += ["## 접근성 — 어느 배치의 값이 가장 큰가", "",
          "칸 = 가장 큰 배치(C 집중 · M 중간 · D 분산 · X 혼합) · D/C 비율. 비율 > 1이면 분산형이 집중형보다 큼.", "",
          "**주의 — 혼잡(2SFCA)의 인구 가중 평균은 항등식이다.** 모든 공간에 닿는 인구가 있으면 Σ_i P_i A_i = Σ_j S_j 이므로 "
          "평균 = 총 면적 ÷ 총 인구가 되어 배치와 무관하다(기회비용 없음이면 모든 배치에서 정확히 같아 'CMDX · 1.00'). "
          "혼잡을 넣었을 때 배치 차이는 **분포**(아래 하위 10% 표)에만 나타난다.", ""]
    for col in ("access_mean", "proxy_equity"):
        w = winners(df, col)
        L += [f"### {OUTCOMES[col]}", ""]
        for cong in (False, True):
            for decay in cfg["sweep"]["decays"]:
                for oc in (False, True):
                    for bar in (False, True):
                        L += [f"**감쇠 {decay} · 혼잡 {'있음 (2SFCA)' if cong else '없음'} · 기회비용 {'있음' if oc else '없음'} · 공원 장벽 {'있음' if bar else '없음'}**", ""]
                        L += _grid_table(w, {"decay": decay, "congestion": cong, "opportunity_cost": oc, "barrier": bar}) + [""]
        fb = flip_boundaries(w)
        L += [f"#### 뒤집히는 경계 ({OUTCOMES[col]}) — β를 키울 때 D/C가 1을 가로지르는 곳", ""]
        if fb:
            L += ["| 감쇠 | 혼잡 | 기회비용 | 장벽 | α | β 구간 | D/C |", "| --- | --- | --- | --- | ---: | --- | --- |"]
            for f in fb:
                L.append(f"| {f['decay']} | {f['congestion']} | {f['opportunity_cost']} | {f['barrier']} | {f['alpha']:g} | "
                         f"{f['beta_low']:g} → {f['beta_high']:g} | {f['ratio_low']:.2f} → {f['ratio_high']:.2f} |")
        else:
            L.append("스윕 범위 안에서 D/C가 1을 가로지르는 곳 없음.")
        L.append("")

    L += ["## 혜택 경로 대리 지표 — 배치별 값 (가우시안, 기회비용 없음, 장벽 없음, 혼잡 없음)", "",
          "| 대리 지표 | α | β | C | M | D | X | 가장 큰 배치 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    sel = df[(df.decay == "gaussian") & (~df.congestion) & (~df.opportunity_cost) & (~df.barrier)]
    for col in ("proxy_activity", "proxy_restoration", "proxy_social", "proxy_equity", "os_cover_5"):
        for (al, be), g in sel.groupby(["alpha", "beta"]):
            if col in ("proxy_restoration", "proxy_social", "os_cover_5") and (al, be) != (1.0, 0.0):
                continue
            if al not in (0.5, 1.0) or be not in (0.0, 0.5, 1.0):
                continue
            v = g.set_index("layout")[col]
            best = v.max()
            win = "".join(LETTER[k] for k in v.index if np.isclose(v[k], best))
            L.append(f"| {col} | {al:g} | {be:g} | " + " | ".join(f"{v[k]:.3g}" for k in ("concentrated", "medium", "dispersed", "mixed")) + f" | {win} |")
    env = base.set_index("layout")["proxy_environment"]
    L += ["| proxy_environment (ha) | – | – | " + " | ".join(f"{env[k]:.2f}" for k in ("concentrated", "medium", "dispersed", "mixed")) +
          f" | {''.join(LETTER[k] for k in env.index if np.isclose(env[k], env.max()))} |", ""]
    L += ["`proxy_restoration`(5 ha 문턱)·`proxy_activity`(1 ha 문턱)·`proxy_environment`(가장자리 20 m 안쪽)는 **정의상** 포켓에 0을 주고, "
          "`proxy_social`(공간 개수)은 정의상 개수가 많은 배치에 유리하다. 이 넷은 대리 지표 정의를 그대로 되돌려 주는 것에 가깝다. "
          "정의에 덜 묶인 것은 접근성 평균·하위 10%·커버리지다.", ""]
    L += hypothesis_section(df)
    (out_dir / "scenarios.md").write_text("\n".join(L))


def hypothesis_section(df: pd.DataFrame) -> list[str]:
    L = ["## 가설 판정 (HYPOTHESES.md A·B — 사전 고정 조건 그대로)", ""]
    w = winners(df, "access_mean")
    a1 = w[(w.beta == 0) & (w.alpha < 1) & (~w.congestion)]
    L.append(f"- **A1** (β=0, α<1, 혼잡 없음 → D > C): {int((a1.D_over_C > 1).sum())}/{len(a1)}칸에서 D > C. "
             f"{'약화 조건(어느 칸이든 C ≥ D) 충족 — A1 약화' if (a1.D_over_C <= 1).any() else '약화 조건 충족 안 됨'}.")
    a2 = w[~w.congestion]
    rev = a2[a2.D_over_C <= 1]
    L.append(f"- **A2** (β를 키우면 C ≥ D 칸 생김, 혼잡 없음): C ≥ D인 칸 {len(rev)}/{len(a2)}. "
             f"{'역전 구간 존재' if len(rev) else '역전 없음 — A2 약화'}" + (f", 가장 작은 β = {rev.beta.min():g}" if len(rev) else "") + ".")
    piv = df.pivot_table(index=["decay", "beta", "alpha", "opportunity_cost", "barrier"], columns=["congestion", "layout"], values="access_mean")
    ratio_nc = piv[(False, "dispersed")] / piv[(False, "concentrated")]
    ratio_c = piv[(True, "dispersed")] / piv[(True, "concentrated")]
    dec = (ratio_c < ratio_nc - 1e-9).mean()
    L.append(f"- **A3** (혼잡을 넣으면 D/C가 작아짐, 평균 기준): {dec:.0%}의 칸에서 작아짐. 단 혼잡 평균은 항등식(총 면적 ÷ 총 인구)이라 "
             "D/C ≈ 1로 고정되므로, 이 판정은 '혼잡 없음일 때 D/C가 1보다 컸는가'를 되돌려 줄 뿐이다 — **사전 고정한 A3는 평균으로는 판정 불가**로 기록한다.")
    pq = df.pivot_table(index=["decay", "beta", "alpha", "opportunity_cost", "barrier"], columns=["congestion", "layout"], values="access_p10")
    with np.errstate(divide="ignore", invalid="ignore"):
        q_nc = pq[(False, "dispersed")] / pq[(False, "concentrated")]
        q_c = pq[(True, "dispersed")] / pq[(True, "concentrated")]
    ok = np.isfinite(q_nc) & np.isfinite(q_c)
    dq = (q_c[ok] < q_nc[ok]).mean() if ok.any() else float("nan")
    L.append(f"  - (사후 보조, 사전 고정 아님) 하위 10% 값으로 같은 비교: 집중형 하위 10%가 0이 아닌 {int(ok.sum())}칸 중 {dq:.0%}에서 혼잡을 넣으면 D/C가 작아짐.")
    piv2 = df.pivot_table(index=["decay", "beta", "alpha", "congestion", "barrier"], columns=["opportunity_cost", "layout"], values="access_mean")
    r0 = piv2[(False, "dispersed")] / piv2[(False, "concentrated")]
    r1 = piv2[(True, "dispersed")] / piv2[(True, "concentrated")]
    dec2 = (r1 < r0 - 1e-12).mean()
    L.append(f"- **A4** (기회비용은 D에 더 불리): {dec2:.0%}의 칸에서 D/C가 작아짐.")
    cols = ["access_mean", "proxy_equity", "proxy_activity", "proxy_restoration", "proxy_social", "os_cover_5"]
    sel = df.groupby("layout")[cols].mean()
    worst = {}
    for lay in sel.index:
        ranks = [int((sel[c] > sel.loc[lay, c] + 1e-12).sum()) + 1 for c in cols]
        worst[lay] = max(ranks)
    L.append("- **A5** (X의 최악 순위가 가장 좋음, 스윕 평균값 기준): 최악 순위 " +
             ", ".join(f"{LETTER[k]} {v}" for k, v in worst.items()) +
             f". {'X가 가장 좋거나 공동' if worst['mixed'] <= min(worst.values()) else 'X보다 좋은 배치 있음 — A5 약화'}.")
    base = df[(df.decay == "gaussian") & (~df.congestion) & (~df.opportunity_cost) & (~df.barrier) & (df.alpha == 1.0) & (df.beta == 0.25)].set_index("layout")
    for hid, col, expect in (("B1", "proxy_activity", "CM"), ("B2", "proxy_restoration", "C"), ("B3", "proxy_social", "D"),
                             ("B4", "proxy_environment", "C"), ("B5", "proxy_equity", "D")):
        v = base[col]
        win = "".join(LETTER[k] for k in v.index if np.isclose(v[k], v.max()))
        ok = any(ch in expect for ch in win)
        L.append(f"- **{hid}** ({col}, 가우시안 α=1 β=0.25 기준): 가장 큰 배치 {win}, 가설 {expect}. {'부합' if ok else '불일치 — 가설 약화'}.")
    L += ["", "B 가설 판정은 대리 지표 정의에 강하게 묶여 있다(위 단락). 실증이 아니라 모델 안의 정합성 확인이다.", ""]
    return L


def draw_layouts(cache: dict, city: City, fig_dir: Path) -> list[Path]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(["#ecebe6", "#33322f", "#b4b1a9", "#dcdad3", "#8a8882", "#8a8882", "#8a8882"])
    fig, axes = plt.subplots(1, 4, figsize=(12, 3.3), dpi=130)
    for ax, (name, g) in zip(axes, cache.items(), strict=False):
        ax.imshow(g["_cls"], cmap=cmap, vmin=0, vmax=6, interpolation="nearest")
        ax.set_title(f"{LETTER[name]} {name}", fontsize=9, color="#33322f")
        ax.set_axis_off()
    fig.patch.set_facecolor("#ecebe6")
    p = fig_dir / "scenario_layouts.png"
    fig.savefig(p, bbox_inches="tight", facecolor="#ecebe6")
    plt.close(fig)
    return [p]
