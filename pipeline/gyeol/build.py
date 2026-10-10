"""파이프라인 전체: make data REGION=<id>

1 layers   어댑터 → 미터 좌표계 레이어
2 network  보행망 CSR
3 spaces   공간 표: 면적, 녹지 비율, 정의별 포함 여부, 출입구 노드
4 cells    H3 셀, 셀↔노드, 래스터 가산 통계, 인구·맥락·라벨
5 dist     셀×공간 네트워크 거리 (희소)
6 metrics  셀 단위 지표 (모든 렌즈)
7 export   웹 산출물 + 데이터 보고서 + 레이어 PNG
"""

from __future__ import annotations

import json
import time

import geopandas as gpd
import numpy as np
import pandas as pd

from .config import params, params_hash, region, region_dirs
from .layers import build_layers, metric_crs
from .network import Network, build_network, entrances
from .raster import (
    class_counts,
    classify,
    coarsen_label,
    coarsen_mode,
    grain_counts,
    label_cells,
    make_grid,
    patch_max_area,
)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def build_all(region_id: str, force: bool = False) -> None:
    reg, prm = region(region_id), params()
    dirs = region_dirs(region_id)
    proc = dirs["processed"]
    L = proc / "layers"

    _log("1 layers")
    build_layers(region_id, force)
    target = gpd.read_parquet(L / "target.parquet")
    study = gpd.read_parquet(L / "study.parquet")
    land = gpd.read_parquet(L / "land.parquet")
    crs = metric_crs(reg, target)

    _log("2 network")
    npath = proc / "network.npz"
    if npath.exists() and not force:
        net = Network.load(npath)
    else:
        net = build_network(study, crs, dirs["raw"])
        net.save(npath)
    _log(f"  nodes={net.n} edges={len(net.indices) // 2}")

    _log("3 raster + spaces")
    spaces = gpd.read_parquet(L / "open_spaces.parquet")
    res = prm["raster"]["resolution_m"]
    grid = make_grid(study.total_bounds, res, max(prm["raster"]["multiscale_m"]))
    land_geom = land.geometry.iloc[0]
    rd = lambda n: gpd.read_parquet(L / f"{n}.parquet") if (L / f"{n}.parquet").exists() else None  # noqa: E731
    cls = classify(grid, land_geom, rd("roadways"), rd("sidewalks"), spaces)
    np.save(proc / "class5m.npy", cls)
    from .ndvi import ndvi_on_grid
    ndvi, items = ndvi_on_grid(grid, crs, tuple(study.to_crs("EPSG:4326").total_bounds), prm["greenness"],
                               dirs["raw"], cls > 0)
    green = ndvi >= prm["greenness"]["ndvi_threshold"]
    spaces = prepare_spaces(spaces, net, grid, green, prm)
    spaces.to_parquet(proc / "spaces.parquet")

    _log("4 cells")
    from .grid import build_cells
    cells = build_cells(land, target, prm["grid"]["h3_resolution"], net, prm["grid"]["max_node_snap_m"])
    lbl = label_cells(grid, cells)
    stats = cell_raster_stats(cls, lbl, len(cells), green, prm)
    cells = pd.concat([cells, stats], axis=1)
    cells = add_vector_stats(cells, L, land_geom, prm)
    cells.to_parquet(proc / "cells.parquet")
    _log(f"  cells={len(cells)} in_target={int(cells.in_target.sum())}")

    _log("5 dist")
    from .metrics.access import space_distances
    D = space_distances(cells, spaces, net, prm)
    import scipy.sparse as sp
    sp.save_npz(proc / "dist.npz", D)

    _log("6 metrics")
    from .metrics.cellmetrics import compute_cell_metrics
    cm = compute_cell_metrics(cells, spaces, D, net, L, prm)
    cm.to_parquet(proc / "cell_metrics.parquet")

    _log("7 export")
    from .export import export_region
    from .report import data_report
    export_region(region_id)
    data_report(region_id, items)
    _log(f"done params_hash={params_hash()}")


def prepare_spaces(spaces: gpd.GeoDataFrame, net: Network, grid, green: np.ndarray, prm: dict) -> gpd.GeoDataFrame:
    from rasterio import features
    os_cfg = prm["open_space"]
    s = spaces.copy().reset_index(drop=True)
    s["area_m2"] = pd.to_numeric(s["area_m2"], errors="coerce")
    poly = s.geom_type.isin(["Polygon", "MultiPolygon"])
    s.loc[poly, "area_m2"] = s.loc[poly].area
    # 공간별 녹지 비율 = 공간 안 NDVI 식생 픽셀 비율 (점 공간은 데이터 없음)
    gr = np.full(len(s), np.nan)
    for i in np.where(poly)[0]:
        g = s.geometry.iloc[i]
        minx, miny, maxx, maxy = g.bounds
        inv = ~grid.transform
        c0, r0 = inv * (minx, maxy)
        c1, r1 = inv * (maxx, miny)
        r0, c0 = max(int(np.floor(r0)), 0), max(int(np.floor(c0)), 0)
        r1, c1 = min(int(np.ceil(r1)) + 1, grid.height), min(int(np.ceil(c1)) + 1, grid.width)
        if r1 <= r0 or c1 <= c0:
            continue
        from rasterio.windows import Window
        from rasterio.windows import transform as wtransform
        win = Window(c0, r0, c1 - c0, r1 - r0)
        m = features.geometry_mask([g], out_shape=(r1 - r0, c1 - c0), transform=wtransform(win, grid.transform), invert=True)
        if m.sum():
            gr[i] = green[r0:r1, c0:c1][m].mean()
    s["green_ratio"] = gr
    free = (s["access"] == "free") & (s["kind"] != "pops")
    s["def_green_only"] = free & s["kind"].isin(os_cfg["green_kinds"]) & (s["green_ratio"] >= os_cfg["green_only_min_green_ratio"])
    s["def_with_plaza_playground"] = free | (s["kind"] == "schoolyard")
    s["def_with_pops"] = s["def_with_plaza_playground"] | (s["kind"] == "pops")
    ent, fb = entrances(s, net, os_cfg["entrance"]["boundary_spacing_m"], os_cfg["entrance"]["snap_max_m"])
    s["entrances"] = [e.tolist() for e in ent]
    s["entrance_fallback"] = fb
    return s


def cell_raster_stats(cls, lbl, ncell: int, green: np.ndarray, prm: dict) -> pd.DataFrame:
    res = prm["raster"]["resolution_m"]
    out = {}
    for variant in ("base", "pops"):
        for r in prm["raster"]["multiscale_m"]:
            f = int(round(r / res))
            c = coarsen_mode(cls, f)
            lb = coarsen_label(lbl, f)
            gc = grain_counts(c, lb, ncell, variant)
            for k, v in gc.items():
                out[f"g_{variant}_{r}_{k}"] = v
        out[f"patch_{variant}_max_m2"] = patch_max_area(cls, lbl, ncell, variant, res)
    px = res * res
    for code, name in ((1, "open_free"), (2, "roadway"), (3, "private"), (4, "sidewalk"), (5, "open_cond"), (6, "pops")):
        out[f"a_{name}_m2"] = class_counts(cls, lbl, ncell, code) * px
    for code, name in ((1, "open_free"), (6, "pops")):
        m = (cls == code) & green
        out[f"a_{name}_green_m2"] = np.bincount(lbl[m], minlength=ncell + 1)[1:] * px
    return pd.DataFrame(out)


def add_vector_stats(cells: gpd.GeoDataFrame, L, land_geom, prm: dict) -> gpd.GeoDataFrame:
    """인구(면적 가중), 가로 중심선 길이, 가로변 건물 높이, 용도, 소득·라벨(셀 중심이 든 트랙트)."""
    cells = cells.copy()
    cen = gpd.GeoDataFrame(geometry=cells.geometry.centroid, crs=cells.crs)
    rd = lambda n: gpd.read_parquet(L / f"{n}.parquet") if (L / f"{n}.parquet").exists() else None  # noqa: E731

    for layer, col, out in (("pop_night", "pop", "pop_night"), ("pop_day", "jobs", "pop_day")):
        g = rd(layer)
        cells[out] = np.nan if g is None else areal_interpolate(g, col, cells, land_geom)

    cl = rd("centerlines")
    if cl is not None:
        cells["street_len_m"] = line_length_by_cell(cl, cells)
        b = rd("buildings")
        if b is not None:
            b = b[b["height_m"].notna()].copy()
            near = gpd.sjoin(b, gpd.GeoDataFrame(geometry=cl.buffer(prm["streets"]["building_search_m"]), crs=cl.crs),
                             predicate="intersects", how="inner")
            near = b.loc[near.index.unique()].copy()
            near["a"] = near.area
            near["ha"] = near["a"] * near["height_m"]
            j = gpd.sjoin(gpd.GeoDataFrame(near[["a", "ha"]], geometry=near.geometry.representative_point(), crs=b.crs),
                          cells[["geometry"]], predicate="within")
            agg = j.groupby("index_right")[["a", "ha"]].sum()
            cells["bldg_street_a_m2"] = agg["a"].reindex(cells.index).fillna(0).values
            cells["bldg_street_ha_m3"] = agg["ha"].reindex(cells.index).fillna(0).values
    else:
        cells["street_len_m"] = np.nan

    lu = rd("landuse")
    if lu is not None:
        j = gpd.sjoin(lu, cells[["geometry"]], predicate="within")
        piv = j.pivot_table(index="index_right", columns="category", values="area_m2", aggfunc="sum").fillna(0)
        for c in piv.columns:
            cells[f"lu_{c}"] = piv[c].reindex(cells.index).fillna(0).values

    for layer in ("income", "labels"):
        g = rd(layer)
        if g is None:
            continue
        j = gpd.sjoin(cen, g, predicate="within", how="left")
        j = j[~j.index.duplicated()]
        for c in g.columns:
            if c in ("geometry", "geoid"):
                continue
            cells[c] = pd.to_numeric(j[c], errors="coerce").values
        if "geoid" in g.columns and "tract" not in cells.columns:
            cells["tract"] = j["geoid"].values
    return cells


def areal_interpolate(src: gpd.GeoDataFrame, col: str, cells: gpd.GeoDataFrame, land_geom) -> np.ndarray:
    """블록 값을 땅 위 면적 비율로 셀에 나눈다. 블록 중 땅 밖(물) 부분은 분모에서 뺀다."""
    src = src[src[col].fillna(0) > 0].copy()
    src["land_a"] = src.geometry.intersection(land_geom).area
    src = src[src["land_a"] > 0]
    ii, jj = cells.sindex.query(src.geometry, predicate="intersects")
    inter = src.geometry.values[ii].intersection(cells.geometry.values[jj])
    w = np.asarray(inter.area) / src["land_a"].values[ii]
    val = src[col].values[ii] * np.minimum(w, 1.0)
    return np.bincount(jj, weights=val, minlength=len(cells))


def line_length_by_cell(lines: gpd.GeoDataFrame, cells: gpd.GeoDataFrame) -> np.ndarray:
    ii, jj = cells.sindex.query(lines.geometry, predicate="intersects")
    inter = lines.geometry.values[ii].intersection(cells.geometry.values[jj])
    return np.bincount(jj, weights=np.asarray(inter.length), minlength=len(cells))


def write_json(path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
