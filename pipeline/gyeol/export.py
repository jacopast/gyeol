"""웹 산출물 (web/public/data/regions/<id>/) — 웹은 이 파일들만 읽는다.

meta.json      지역·파라미터·지표 목록·열 배치
cells.bin      Float32 열 묶음 (셀 수 × 열 수, 열 우선)
network.bin    보행망: lon/lat(Float32) · indptr(Int32) · indices(Int32) · weights(Float32)
spaces.json    공간 표 (면적, 종류, 정의 포함 여부, 출입구 노드) — 설계안 재계산용
spaces.geojson 공간 윤곽 (지도 레이어)
pois.json      셀별 POI 범주 개수 (희소)
xval.json      교차 검증 기준값 (Python 기준 구현)
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer

from .config import params, params_hash, region, region_dirs
from .metrics.cellmetrics import poi_counts
from .network import Network

# 웹에 싣는 셀 열 (가산 통계 + 지표 렌즈). 나머지(기하 등)는 싣지 않는다
CELL_BASE_COLS = ["node", "in_target", "land_m2", "pop_night", "pop_day", "street_len_m", "bldg_street_a_m2",
                  "bldg_street_ha_m3", "income"]


def _cell_columns(cells: pd.DataFrame, cm: pd.DataFrame) -> list[tuple[str, np.ndarray]]:
    cols = []
    for c in cells.columns:
        if c in CELL_BASE_COLS or c.startswith(("g_", "a_", "patch_", "lu_", "places_")):
            cols.append((c, cells[c].to_numpy(dtype=float)))
    for c in cm.columns:
        if c != "h3":
            cols.append((c, cm[c].to_numpy(dtype=float)))
    return cols


def load_region(region_id: str):
    d = region_dirs(region_id)["processed"]
    cells = gpd.read_parquet(d / "cells.parquet")
    cm = pd.read_parquet(d / "cell_metrics.parquet")
    spaces = gpd.read_parquet(d / "spaces.parquet")
    net = Network.load(d / "network.npz")
    L = d / "layers"
    pois = gpd.read_parquet(L / "pois.parquet") if (L / "pois.parquet").exists() else None
    cats, rows = poi_counts(cells, pois)
    return cells, cm, spaces, net, cats, rows


def export_region(region_id: str) -> None:
    prm, reg = params(), region(region_id)
    dirs = region_dirs(region_id)
    out = dirs["web"]
    cells, cm, spaces, net, cats, rows = load_region(region_id)
    crs = cells.crs
    to_wgs = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    # 셀 열
    cols = _cell_columns(cells, cm)
    mat = np.vstack([v for _, v in cols]).astype(np.float32)
    mat.tofile(out / "cells.bin")
    (out / "cells_h3.json").write_text(json.dumps(cells["h3"].tolist()))

    # 보행망
    lon, lat = to_wgs.transform(net.x, net.y)
    with open(out / "network.bin", "wb") as f:
        np.asarray(lon, np.float32).tofile(f)
        np.asarray(lat, np.float32).tofile(f)
        net.indptr.astype(np.int32).tofile(f)
        net.indices.astype(np.int32).tofile(f)
        net.weights.astype(np.float32).tofile(f)

    # 공간
    sw = spaces.to_crs("EPSG:4326")
    rp = sw.geometry.representative_point()
    sp_rows = []
    for i, r in spaces.iterrows():
        sp_rows.append({
            "id": r["id"], "name": None if pd.isna(r["name"]) else str(r["name"]), "kind": r["kind"],
            "access": r["access"], "area_m2": round(float(r["area_m2"]), 1),
            "green_ratio": None if pd.isna(r["green_ratio"]) else round(float(r["green_ratio"]), 3),
            "defs": [d for d in ("green_only", "with_plaza_playground", "with_pops") if r[f"def_{d}"]],
            "entrances": [int(x) for x in r["entrances"]],
            "pt": [round(rp.iloc[i].x, 6), round(rp.iloc[i].y, 6)],
        })
    (out / "spaces.json").write_text(json.dumps(sp_rows, ensure_ascii=False, separators=(",", ":")))
    gj = spaces[["id", "kind", "access", "geometry"]].copy()
    pts = gj.geom_type == "Point"
    gj.loc[pts, "geometry"] = spaces.loc[pts].apply(lambda r: r.geometry.buffer(np.sqrt(r["area_m2"] / np.pi)), axis=1)
    gj["geometry"] = gj.geometry.simplify(1.5)
    gj.to_crs("EPSG:4326").to_file(out / "spaces.geojson", driver="GeoJSON", COORDINATE_PRECISION=6)

    (out / "pois.json").write_text(json.dumps({"categories": cats, "rows": rows}, separators=(",", ":")))

    tgt = gpd.read_parquet(dirs["processed"] / "layers" / "target.parquet").to_crs("EPSG:4326")
    b = tgt.total_bounds
    meta = {
        "id": region_id, "name": reg["name"], "name_en": reg.get("name_en"), "crs": crs.to_string(),
        "bounds": [float(x) for x in b], "center": [float((b[0] + b[2]) / 2), float((b[1] + b[3]) / 2)],
        "units_display": reg.get("units_display", "metric"),
        "run_id": prm["run_id"], "params_hash": params_hash(),
        "params": {**{k: prm[k] for k in ("walk", "access", "open_space", "raster", "streets", "grain", "greenness", "region")},
                   "design": {"persons_per_unit": _persons_per_unit(dirs)}},
        "n_cells": len(cells), "columns": [c for c, _ in cols],
        "network": {"n_nodes": int(net.n), "n_entries": int(len(net.indices))},
        "lu_columns": [c for c in cells.columns if c.startswith("lu_")],
        "label_columns": [c for c in cells.columns if c.startswith("places_")],
        "missing_layers": _missing_layers(dirs),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    _update_region_index()


def _persons_per_unit(dirs) -> float | None:
    """설계안 units → 인구: 대상 지역 센서스 블록의 인구 / 주택 수 (데이터에서, 문헌값 아님). 없으면 None."""
    raw = dirs["raw"] / "census_blocks.parquet"
    if not raw.exists():
        return None
    b = gpd.read_parquet(raw)
    tgt = gpd.read_parquet(dirs["processed"] / "layers" / "target.parquet").to_crs(b.crs)
    b = b[b.representative_point().within(tgt.geometry.iloc[0])]
    h = float(b["HOUSING20"].sum())
    return round(float(b["POP20"].sum()) / h, 3) if h > 0 else None


def _missing_layers(dirs) -> list[str]:
    p = dirs["processed"] / "layers_summary.json"
    if not p.exists():
        return []
    s = json.loads(p.read_text())
    return [k for k, v in s["layers"].items() if v is None]


def _update_region_index() -> None:
    from .config import CONFIG, WEB_DATA
    idx = []
    for f in sorted((WEB_DATA / "regions").glob("*/meta.json")):
        m = json.loads(f.read_text())
        rid = m["id"]
        if (CONFIG / "regions" / f"{rid}.yaml").exists():
            idx.append({"id": rid, "name": m["name"], "name_en": m.get("name_en"), "center": m["center"]})
    (WEB_DATA / "regions.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1))


def export_xval(region_id: str) -> None:
    """무작위 지점(대상 안 셀의 노드) 20곳에서 Python 기준 구현의 표본 지표를 계산해 저장."""
    from .sample import aggregate, walkshed_cells
    prm = params()
    cells, cm, spaces, net, cats, rows = load_region(region_id)
    cfg = prm["comparison"]
    rng = np.random.default_rng(cfg["xval_random_state"])
    tgt = np.where(cells["in_target"].to_numpy())[0]
    picks = rng.choice(tgt, cfg["xval_points"], replace=False)
    a = prm["access"]
    lens = {"definition": prm["open_space"]["default_definition"], "decay": a["default_decay"],
            "alpha": a["default_alpha"], "beta": a["default_beta"]}
    pts = []
    for ci in picks:
        start = int(cells["node"].iloc[ci])
        for mins in prm["walk"]["sample_minutes"]:
            idx = walkshed_cells(net, cells["node"].to_numpy(), start, mins, prm["walk"]["speed_mps"])
            pts.append({"start_node": start, "minutes": mins, "n_cells": int(len(idx)),
                        "cells": [int(i) for i in idx], "metrics": aggregate(idx, cells, cm, rows, lens, prm)})
    out = region_dirs(region_id)["web"] / "xval.json"
    out.write_text(json.dumps({"lens": lens, "tolerance": cfg["xval_tolerance"], "points": pts}, ensure_ascii=False))
