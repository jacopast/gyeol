"""보행망: OSMnx walk 그래프 → 무방향 CSR (미터). 웹 워커와 같은 구조를 쓴다.

직선거리는 쓰지 않는다 (SPEC 2.1). 출입구는 공간 경계를 따라 찍은 점에서 가까운 보행 노드.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiPolygon, Polygon

from .fetch import log_source


@dataclass
class Network:
    x: np.ndarray          # float64 (N,)
    y: np.ndarray
    indptr: np.ndarray     # int32 (N+1,)
    indices: np.ndarray    # int32 (E,)
    weights: np.ndarray    # float32 (E,) 미터

    @property
    def n(self) -> int:
        return len(self.x)

    def csr(self) -> sp.csr_matrix:
        return sp.csr_matrix((self.weights.astype(np.float64), self.indices, self.indptr), shape=(self.n, self.n))

    def kdtree(self) -> cKDTree:
        return cKDTree(np.c_[self.x, self.y])

    def save(self, path: Path) -> None:
        np.savez_compressed(path, x=self.x, y=self.y, indptr=self.indptr, indices=self.indices, weights=self.weights)

    @classmethod
    def load(cls, path: Path) -> Network:
        d = np.load(path)
        return cls(d["x"], d["y"], d["indptr"], d["indices"], d["weights"])

    def dist_at(self, sources, limit: float, at: np.ndarray) -> np.ndarray:
        """dist_from을 노드 목록 at에서 읽는다. at < 0 (보행망 밖)은 inf."""
        d = self.dist_from(sources, limit)
        return np.where(at >= 0, d[np.maximum(at, 0)], np.inf)

    def dist_from(self, sources, limit: float) -> np.ndarray:
        """여러 출발 노드 중 가장 가까운 것까지의 네트워크 거리. limit 밖은 inf."""
        src = np.unique(np.asarray(sources, dtype=np.int64))
        return dijkstra(self.csr(), directed=False, indices=src, limit=limit, min_only=True)


def build_network(study_m: gpd.GeoDataFrame, crs: str, raw_dir: Path) -> Network:
    poly = study_m.to_crs("EPSG:4326").geometry.iloc[0]
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(raw_dir / "osmnx_cache")
    g = ox.graph_from_polygon(poly, network_type="walk", simplify=True, retain_all=True)
    log_source(raw_dir, "walk_network", source="OpenStreetMap via osmnx graph_from_polygon(network_type='walk')")
    g = ox.project_graph(g, to_crs=crs)
    return graph_to_network(g)


def graph_to_network(g) -> Network:
    nodes = list(g.nodes)
    idx = {n: i for i, n in enumerate(nodes)}
    x = np.array([g.nodes[n]["x"] for n in nodes])
    y = np.array([g.nodes[n]["y"] for n in nodes])
    best: dict[tuple[int, int], float] = {}
    for u, v, d in g.edges(data=True):
        a, b = idx[u], idx[v]
        if a == b:
            continue
        key = (min(a, b), max(a, b))
        w = float(d.get("length", np.hypot(x[a] - x[b], y[a] - y[b])))
        if key not in best or w < best[key]:
            best[key] = w
    return edges_to_network(x, y, best)


def edges_to_network(x, y, edges: dict[tuple[int, int], float]) -> Network:
    if edges:
        a = np.array([k[0] for k in edges], dtype=np.int64)
        b = np.array([k[1] for k in edges], dtype=np.int64)
        w = np.array(list(edges.values()), dtype=np.float32)
    else:
        a = b = np.zeros(0, dtype=np.int64)
        w = np.zeros(0, dtype=np.float32)
    rows = np.r_[a, b]
    cols = np.r_[b, a]
    ww = np.r_[w, w]
    m = sp.csr_matrix((ww, (rows, cols)), shape=(len(x), len(x)))
    m.sort_indices()
    return Network(np.asarray(x, float), np.asarray(y, float), m.indptr.astype(np.int32),
                   m.indices.astype(np.int32), m.data.astype(np.float32))


def entrances(spaces: gpd.GeoDataFrame, net: Network, spacing: float, snap: float) -> tuple[list[np.ndarray], np.ndarray]:
    """공간별 출입구 노드 목록. 경계를 spacing 간격으로 샘플 → snap 거리 안의 가장 가까운 노드.
    하나도 없으면 대표점에서 가장 가까운 노드 하나 (fallback=True로 표시)."""
    tree = net.kdtree()
    out, fallback = [], np.zeros(len(spaces), dtype=bool)
    for i, geom in enumerate(spaces.geometry):
        pts = _boundary_points(geom, spacing)
        d, k = tree.query(pts, distance_upper_bound=snap)
        ok = np.isfinite(d)
        nodes = np.unique(k[ok])
        if len(nodes) == 0:
            p = geom.representative_point() if geom.geom_type != "Point" else geom
            nodes = np.array([tree.query([p.x, p.y])[1]])
            fallback[i] = geom.geom_type != "Point"   # 점 공간(POPS)은 원래 최근접 노드가 출입구
        out.append(nodes.astype(np.int32))
    return out, fallback


def _boundary_points(geom, spacing: float) -> np.ndarray:
    if geom.geom_type == "Point":
        return np.array([[geom.x, geom.y]])
    rings: list[LineString] = []
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom] if isinstance(geom, Polygon) else []
    for p in polys:
        rings.append(LineString(p.exterior.coords))
    pts = []
    for r in rings:
        n = max(int(r.length // spacing), 1)
        for t in np.linspace(0, r.length, n, endpoint=False):
            q = r.interpolate(t)
            pts.append((q.x, q.y))
    if not pts:
        c = geom.representative_point()
        pts = [(c.x, c.y)]
    return np.array(pts)
