"""1단계: 어댑터로 레이어를 모아 미터 좌표계로 정제해 data/processed/<region>/layers/ 에 저장."""

from __future__ import annotations

import json

import geopandas as gpd
import pandas as pd

from .adapters import get_adapter
from .config import params, region, region_dirs

LAYERS = [
    "open_spaces", "temporary_spaces", "sidewalks", "roadways", "centerlines", "buildings",
    "pop_night", "pop_day", "landuse", "income", "pois", "labels",
]


def metric_crs(reg: dict, target_wgs: gpd.GeoDataFrame) -> str:
    if reg.get("crs_metric"):
        return reg["crs_metric"]
    return str(target_wgs.estimate_utm_crs())


def _clean(g: gpd.GeoDataFrame, crs: str) -> gpd.GeoDataFrame:
    g = g[g.geometry.notna() & ~g.geometry.is_empty].to_crs(crs)
    poly = g.geom_type.isin(["Polygon", "MultiPolygon"])
    if poly.any():
        g.loc[poly, "geometry"] = g.loc[poly, "geometry"].make_valid()
    return g.reset_index(drop=True)


def build_layers(region_id: str, force: bool = False) -> dict:
    reg, prm = region(region_id), params()
    dirs = region_dirs(region_id)
    out_dir = dirs["processed"] / "layers"
    out_dir.mkdir(parents=True, exist_ok=True)
    ad = get_adapter(reg, prm, dirs["raw"])

    target = ad.target()
    crs = metric_crs(reg, target)
    target_m = target.to_crs(crs)
    target_m = gpd.GeoDataFrame(geometry=[target_m.geometry.union_all()], crs=crs)
    study_m = gpd.GeoDataFrame(geometry=target_m.buffer(prm["region"]["boundary_buffer_m"]), crs=crs)
    target_m.to_parquet(out_dir / "target.parquet")
    study_m.to_parquet(out_dir / "study.parquet")

    land = _clean(ad.land(study_m), crs)
    land = gpd.GeoDataFrame(geometry=[land.geometry.union_all()], crs=crs)
    land.to_parquet(out_dir / "land.parquet")

    summary = {"crs": crs, "layers": {}}
    study_geom = study_m.geometry.iloc[0]
    for name in LAYERS:
        path = out_dir / f"{name}.parquet"
        if path.exists() and not force:
            g = gpd.read_parquet(path)
        else:
            raw = getattr(ad, name)(study_m)
            if raw is None:
                summary["layers"][name] = None
                if path.exists():
                    path.unlink()
                continue
            g = _clean(raw, crs)
            g = g[g.intersects(study_geom)].reset_index(drop=True)
            if name == "open_spaces":
                g = dedupe_open_spaces(g, prm["open_space"]["min_area_m2"])
            g.to_parquet(path)
        summary["layers"][name] = _layer_stats(g)
    summary["versions"] = ad.versions()
    sources = dirs["raw"] / "sources.json"
    summary["sources"] = json.loads(sources.read_text()) if sources.exists() else {}
    (dirs["processed"] / "layers_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return summary


def dedupe_open_spaces(g: gpd.GeoDataFrame, min_area_m2: float, overlap: float = 0.5) -> gpd.GeoDataFrame:
    """겹치는 공간을 한 번만 센다. 행 순서 = 우선순위(어댑터가 공식 출처를 먼저 둔다).
    면 공간은 이미 받아들인 공간과 overlap 이상 겹치면 버리고, 덜 겹치면 겹친 부분을 잘라 낸다.
    점 공간(POPS 등)은 면적 속성을 쓰고 그대로 둔다. 잘라낸 뒤 min_area_m2보다 작으면 버린다."""
    poly = g.geom_type.isin(["Polygon", "MultiPolygon"])
    pts = g[~poly]
    polys = g[poly].reset_index(drop=True)
    kept_geoms, kept_idx = [], []
    from shapely.strtree import STRtree
    accepted: list = []
    for i, geom in enumerate(polys.geometry):
        if accepted:
            tree = STRtree(accepted)
            hits = [accepted[j] for j in tree.query(geom, predicate="intersects")]
            if hits:
                from shapely import union_all
                inter = geom.intersection(union_all(hits))
                if inter.area >= overlap * geom.area:
                    continue
                geom = geom.difference(inter)
        if geom.area < min_area_m2:
            continue
        accepted.append(geom)
        kept_geoms.append(geom)
        kept_idx.append(i)
    out = polys.iloc[kept_idx].copy()
    out["geometry"] = kept_geoms
    out["area_m2"] = [geom.area for geom in kept_geoms]
    pts = pts.copy()
    pts = pts[pd.to_numeric(pts["area_m2"], errors="coerce").fillna(0) >= min_area_m2]
    return gpd.GeoDataFrame(pd.concat([out, pts], ignore_index=True), crs=g.crs)


def _layer_stats(g: gpd.GeoDataFrame) -> dict:
    s = {"features": int(len(g))}
    types = g.geom_type.value_counts().to_dict()
    s["geom_types"] = {k: int(v) for k, v in types.items()}
    poly = g[g.geom_type.isin(["Polygon", "MultiPolygon"])]
    if len(poly):
        s["area_m2"] = float(poly.area.sum())
    lines = g[g.geom_type.isin(["LineString", "MultiLineString"])]
    if len(lines):
        s["length_m"] = float(lines.length.sum())
    for c in ["pop", "jobs"]:
        if c in g.columns:
            s[f"sum_{c}"] = float(pd.to_numeric(g[c], errors="coerce").sum())
    return s
