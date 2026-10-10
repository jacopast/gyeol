"""지상층 공공/차량/사적 분류 래스터와 셀 단위 가산 통계 (SPEC 9.3, 9.4 결 지표).

클래스 코드
  0 = 땅 아님(물·범위 밖)      1 = 조건 없는 열린 공간(공원·광장·수변 등, access=free)
  2 = 차량 공간(차로 노면)       3 = 사적(필지, 건물)
  4 = 보도                       5 = 조건부 열린 공간(시간제 운동장, 정원 등)
  6 = POPS (사유 공개공지)
공공(보행 공공) = {1, 4} (+6, with_pops), 사적 = {3, 5, 6} (with_pops에서는 {3, 5}), 차량 = {2}는 따로 보고.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
from affine import Affine
from rasterio import features
from scipy import ndimage

PUBLIC = {"base": (1, 4), "pops": (1, 4, 6)}
PRIVATE = {"base": (3, 5, 6), "pops": (3, 5)}
OPEN_PATCH = {"base": (1,), "pops": (1, 6)}


@dataclass
class Grid:
    transform: Affine
    width: int
    height: int
    res: float


def make_grid(bounds, res: float, align: float) -> Grid:
    minx, miny, maxx, maxy = bounds
    minx = np.floor(minx / align) * align
    miny = np.floor(miny / align) * align
    maxx = np.ceil(maxx / align) * align
    maxy = np.ceil(maxy / align) * align
    w = int(round((maxx - minx) / res))
    h = int(round((maxy - miny) / res))
    return Grid(Affine(res, 0, minx, 0, -res, maxy), w, h, res)


def _burn(arr, geoms, value, grid: Grid):
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return
    mask = features.geometry_mask(geoms, out_shape=(grid.height, grid.width), transform=grid.transform, invert=True)
    arr[mask] = value


def classify(grid: Grid, land, roadways, sidewalks, spaces: gpd.GeoDataFrame) -> np.ndarray:
    """그리는 순서가 우선순위: 사적(땅 전체) → 차로 → 보도 → 조건부 → POPS → 조건 없는 열린 공간."""
    a = np.zeros((grid.height, grid.width), dtype=np.uint8)
    _burn(a, [land], 3, grid)
    if roadways is not None:
        _burn(a, roadways.geometry, 2, grid)
    if sidewalks is not None:
        _burn(a, sidewalks.geometry, 4, grid)
    sp = spaces[spaces.geom_type.isin(["Polygon", "MultiPolygon"]) | (spaces["kind"] == "pops")].copy()
    # 점 POPS는 요구 면적만큼의 원으로 근사
    pts = sp.geom_type == "Point"
    sp.loc[pts, "geometry"] = sp.loc[pts].apply(lambda r: r.geometry.buffer(np.sqrt(r["area_m2"] / np.pi)), axis=1)
    cond = sp[(sp["access"] == "conditional") & (sp["kind"] != "pops")]
    _burn(a, cond.geometry, 5, grid)
    _burn(a, sp[sp["kind"] == "pops"].geometry, 6, grid)
    _burn(a, sp[sp["access"] == "free"].geometry, 1, grid)
    # 땅 밖은 0 (차로·보도 데이터가 물 위 교량에 걸친 부분 포함)
    outside = ~features.geometry_mask([land], out_shape=a.shape, transform=grid.transform, invert=True)
    a[outside] = 0
    return a


def label_cells(grid: Grid, cells: gpd.GeoDataFrame) -> np.ndarray:
    """셀 번호 래스터 (셀 인덱스 + 1, 셀 밖 0)."""
    shapes = ((g, i + 1) for i, g in enumerate(cells.geometry))
    return features.rasterize(shapes, out_shape=(grid.height, grid.width), transform=grid.transform,
                              fill=0, dtype="int32")


def coarsen_mode(a: np.ndarray, f: int) -> np.ndarray:
    """f×f 블록 최빈값. 동점이면 블록 왼쪽 위 픽셀의 클래스 (params grain.coarsen_tie=top_left)."""
    if f == 1:
        return a
    h, w = a.shape[0] // f * f, a.shape[1] // f * f
    b = a[:h, :w].reshape(h // f, f, w // f, f).transpose(0, 2, 1, 3).reshape(h // f, w // f, f * f)
    nclass = int(a.max()) + 1
    counts = np.stack([(b == k).sum(axis=2) for k in range(nclass)], axis=2)
    best = counts.max(axis=2)
    top_left = b[:, :, 0]
    tl_count = np.take_along_axis(counts, top_left[..., None].astype(np.int64), axis=2)[..., 0]
    mode = counts.argmax(axis=2).astype(a.dtype)
    return np.where(tl_count == best, top_left, mode).astype(a.dtype)


def coarsen_label(lbl: np.ndarray, f: int) -> np.ndarray:
    """셀 번호도 같은 규칙(최빈, 동점 왼쪽 위)으로. 셀 수가 많아 bincount 대신 정렬 기반."""
    if f == 1:
        return lbl
    h, w = lbl.shape[0] // f * f, lbl.shape[1] // f * f
    b = lbl[:h, :w].reshape(h // f, f, w // f, f).transpose(0, 2, 1, 3).reshape(h // f, w // f, f * f)
    s = np.sort(b, axis=2)
    # 블록 안 연속 구간 길이로 최빈값
    out = b[:, :, 0].copy()
    best = (b == out[..., None]).sum(axis=2)
    for k in range(f * f):
        v = s[:, :, k]
        c = (b == v[..., None]).sum(axis=2)
        better = c > best
        out[better] = v[better]
        best[better] = c[better]
    return out


def grain_counts(cls: np.ndarray, lbl: np.ndarray, ncell: int, variant: str) -> dict[str, np.ndarray]:
    """셀별 가산 통계: 공공·사적·차량 픽셀 수, 4-이웃 쌍(PP, PQ, QQ). 쌍은 왼쪽/위 픽셀의 셀에 귀속."""
    P = np.isin(cls, PUBLIC[variant])
    Q = np.isin(cls, PRIVATE[variant])
    V = cls == 2
    out = {}
    for name, m in (("nP", P), ("nQ", Q), ("nV", V)):
        out[name] = np.bincount(lbl[m], minlength=ncell + 1)[1:]
    pp = np.zeros(ncell + 1, dtype=np.int64)
    pq = np.zeros(ncell + 1, dtype=np.int64)
    qq = np.zeros(ncell + 1, dtype=np.int64)
    for a_sl, b_sl in (((slice(None), slice(None, -1)), (slice(None), slice(1, None))),
                       ((slice(None, -1), slice(None)), (slice(1, None), slice(None)))):
        pa, pb, qa, qb = P[a_sl], P[b_sl], Q[a_sl], Q[b_sl]
        la = lbl[a_sl]
        pp += np.bincount(la[pa & pb], minlength=ncell + 1)
        pq += np.bincount(la[(pa & qb) | (qa & pb)], minlength=ncell + 1)
        qq += np.bincount(la[qa & qb], minlength=ncell + 1)
    out["PP"], out["PQ"], out["QQ"] = pp[1:], pq[1:], qq[1:]
    return out


def patch_max_area(cls: np.ndarray, lbl: np.ndarray, ncell: int, variant: str, res: float) -> np.ndarray:
    """열린 공간(보도 제외) 4-연결 패치. 셀마다 그 셀에 닿는 가장 큰 패치의 면적(m²)."""
    m = np.isin(cls, OPEN_PATCH[variant])
    comp, n = ndimage.label(m, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    if n == 0:
        return np.zeros(ncell)
    area = np.bincount(comp.ravel(), minlength=n + 1).astype(float) * res * res
    area[0] = 0
    pa = area[comp]
    out = np.zeros(ncell + 1)
    np.maximum.at(out, lbl.ravel(), pa.ravel())
    return out[1:]


def patch_id_area(cls: np.ndarray, variant: str, res: float):
    m = np.isin(cls, OPEN_PATCH[variant])
    comp, n = ndimage.label(m, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    area = np.bincount(comp.ravel(), minlength=n + 1).astype(float) * res * res
    return comp, area


def class_counts(cls: np.ndarray, lbl: np.ndarray, ncell: int, code: int) -> np.ndarray:
    return np.bincount(lbl[cls == code], minlength=ncell + 1)[1:]
