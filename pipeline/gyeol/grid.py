"""H3 격자. 연구 범위(대상+버퍼)의 땅을 덮는 셀을 만들고, 셀마다 가장 가까운 보행 노드를 붙인다."""

from __future__ import annotations

import geopandas as gpd
import h3
import numpy as np
from shapely.geometry import Polygon, mapping

from .network import Network


def build_cells(land_m: gpd.GeoDataFrame, target_m: gpd.GeoDataFrame, res: int, net: Network, max_snap: float) -> gpd.GeoDataFrame:
    land_w = land_m.to_crs("EPSG:4326").geometry.iloc[0]
    ids = sorted(h3.geo_to_cells(mapping(land_w), res))
    polys = [Polygon([(lng, lat) for lat, lng in h3.cell_to_boundary(c)]) for c in ids]
    cells = gpd.GeoDataFrame({"h3": ids}, geometry=polys, crs="EPSG:4326").to_crs(land_m.crs)
    cen = cells.geometry.centroid
    tgt = target_m.geometry.iloc[0]
    cells["in_target"] = cen.within(tgt).values
    land = land_m.geometry.iloc[0]
    cells["land_m2"] = cells.geometry.intersection(land).area.values
    cells = cells[cells["land_m2"] > 0].reset_index(drop=True)
    cen = cells.geometry.centroid
    d, k = net.kdtree().query(np.c_[cen.x, cen.y])
    # 보행망에서 너무 먼 셀(보행로 없는 섬 등)은 노드 없음(-1): 권역·접근성 계산에서 빠진다
    cells["node"] = np.where(d <= max_snap, k, -1).astype(np.int32)
    cells["node_snap_m"] = d
    return cells
