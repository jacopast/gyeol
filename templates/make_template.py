"""설계안 템플릿·예제 만들기: 실제 맨해튼 레이어에서 한 블록을 잘라 9.6 스키마로 바꾼 뒤 작은 개입을 넣는다.

uv run python templates/make_template.py
→ templates/design_template.geojson (스키마 예시 = 예제와 같음)
→ web/public/data/regions/manhattan/design_example.geojson

예제 개입 (시연용, 제안 아님): 블록 하나의 가장 낮은 건물 자리를 포켓파크로, 블록 중간 보행 통로 하나,
가로 하나의 차로를 1개 줄여 보도로, 대상지 안 건물은 그대로(units/jobs 없음 → 기존 인구 유지).
"""

from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
from shapely import affinity
from shapely.geometry import LineString, Point, box, mapping

from gyeol.config import ROOT, region_dirs

SITE_LONLAT = (-73.9917, 40.7639)   # Hell's Kitchen, 10~11번가 사이 W 50~51 St 근처
SIZE_M = (260, 150)                 # 애비뉴 방향 × 스트리트 방향
GRID_ROT = -29.0                    # 맨해튼 가로망 기울기(도, 시계 방향 29°)


def main():
    L = region_dirs("manhattan")["processed"] / "layers"
    crs = "EPSG:32618"
    c = gpd.GeoSeries([Point(SITE_LONLAT)], crs="EPSG:4326").to_crs(crs).iloc[0]
    site = affinity.rotate(box(c.x - SIZE_M[1] / 2, c.y - SIZE_M[0] / 2, c.x + SIZE_M[1] / 2, c.y + SIZE_M[0] / 2), GRID_ROT, origin=c)
    feats = [{"layer": "boundary", "geometry": site}]

    sw = gpd.read_parquet(L / "sidewalks.parquet")
    rw = gpd.read_parquet(L / "roadways.parquet")
    bl = gpd.read_parquet(L / "buildings.parquet")
    sw_in = sw.clip(site).explode(index_parts=False)
    sw_in = sw_in[sw_in.geom_type == "Polygon"]
    rw_in = rw.clip(site).explode(index_parts=False)
    rw_in = rw_in[rw_in.geom_type == "Polygon"]
    bl_in = bl[bl.representative_point().within(site)].copy()
    bl_in = bl_in.explode(index_parts=False)
    bl_in = bl_in[bl_in.area > 20]

    # 기존 공공공간은 그대로 옮겨 적는다 (설계안은 대상지 안을 통째로 교체하므로)
    sp = gpd.read_parquet(region_dirs("manhattan")["processed"] / "spaces.parquet")
    sp_in = sp[sp.representative_point().within(site) & sp.geom_type.isin(["Polygon", "MultiPolygon"])]
    for k, r in enumerate(sp_in.itertuples()):
        gr = 0.0 if np.isnan(r.green_ratio) else round(float(r.green_ratio), 2)
        feats.append({"layer": "open_space", "id": f"e{k}", "access": r.access, "kind": r.kind, "green_ratio": gr,
                      "geometry": r.geometry.intersection(site)})

    # 개입 1: 가장 낮은 건물 자리를 포켓파크로
    bl_in = bl_in[bl_in["height_m"].notna()].sort_values("height_m")
    # 공간 최소 면적(params open_space.min_area_m2)보다 넉넉히 큰 건물 중 가장 낮은 것
    pick = bl_in[bl_in.area >= 450].index[0]
    park_geom = bl_in.loc[pick].geometry
    if hasattr(park_geom, "iloc"):
        park_geom = park_geom.iloc[0]
    if park_geom.geom_type == "MultiPolygon":
        park_geom = max(park_geom.geoms, key=lambda q: q.area)
    bl_keep = bl_in.drop(index=pick)
    feats.append({"layer": "open_space", "id": "p1", "access": "free", "kind": "park", "green_ratio": 0.7, "hours": "06:00-01:00",
                  "geometry": park_geom})
    ep = park_geom.exterior.interpolate(0.0)
    feats.append({"layer": "entrance", "serves": "p1", "geometry": ep})

    # 개입 2: 차로 하나를 줄여 보도로 — 가장 큰 차로 면의 한쪽 3.2 m 띠를 보도로
    rw_in = rw_in[rw_in.area > 50]
    big = rw_in.geometry.iloc[int(np.argmax(rw_in.area.values))]
    strip = big.intersection(big.exterior.buffer(3.2)) if big.geom_type == "Polygon" else None
    for g in rw_in.geometry:
        if g.equals(big) and strip is not None:
            feats.append({"layer": "roadway", "lanes": 1, "use": "car", "geometry": g.difference(strip)})
            feats.append({"layer": "sidewalk", "clear_width_m": 3.0, "geometry": strip})
        else:
            feats.append({"layer": "roadway", "lanes": 2, "use": "car", "geometry": g})
    for g in sw_in.geometry:
        if g.area > 5:
            feats.append({"layer": "sidewalk", "geometry": g})
    for _, b in bl_keep.iterrows():
        feats.append({"layer": "building", "height_m": round(float(b["height_m"]), 1), "ground_use": "mixed", "geometry": b.geometry})

    # 개입 3: 블록 중간 보행 통로 (스트리트 방향으로 블록을 가로지름)
    mid = affinity.rotate(LineString([(c.x - SIZE_M[1] / 2 - 15, c.y), (c.x + SIZE_M[1] / 2 + 15, c.y)]), GRID_ROT, origin=c)
    feats.append({"layer": "ped_link", "geometry": mid})
    # 전면: 애비뉴 쪽 한 변
    edge = affinity.rotate(LineString([(c.x + SIZE_M[1] / 2 - 2, c.y - SIZE_M[0] / 2), (c.x + SIZE_M[1] / 2 - 2, c.y + SIZE_M[0] / 2)]), GRID_ROT, origin=c)
    feats.append({"layer": "frontage", "doors_per_100m": 8, "transparency": 0.6, "geometry": edge})

    g = gpd.GeoDataFrame([{k: v for k, v in f.items() if k != "geometry"} for f in feats],
                         geometry=[f["geometry"] for f in feats], crs=crs).to_crs("EPSG:4326")
    g = g[~g.geometry.is_empty]
    out = {"type": "FeatureCollection", "name": "gyeol_design_example", "features": []}
    for _, r in g.iterrows():
        props = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.drop("geometry").items()}
        props = {k: v for k, v in props.items() if v is not None}
        geom = r.geometry
        if geom.geom_type == "GeometryCollection":
            continue
        out["features"].append({"type": "Feature", "properties": props, "geometry": _round(mapping(geom))})
    txt = json.dumps(out, ensure_ascii=False)
    (ROOT / "templates" / "design_template.geojson").write_text(txt)
    (ROOT / "web" / "public" / "data" / "regions" / "manhattan" / "design_example.geojson").write_text(txt)
    print(len(out["features"]), "features")


def _round(g):
    def r(c):
        return [round(c[0], 7), round(c[1], 7)] if isinstance(c[0], float) else [r(x) for x in c]
    return {"type": g["type"], "coordinates": r(g["coordinates"]) if g["type"] != "Point" else [round(g["coordinates"][0], 7), round(g["coordinates"][1], 7)]}


if __name__ == "__main__":
    main()
