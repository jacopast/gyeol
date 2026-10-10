"""전지구 인구: GHSL GHS-POP E2025 (R2023A), 100 m, Mollweide(ESRI:54009). 키 없음.

타일 = 1000 km 정사각형, R(위→아래)·C(왼→오른) 1부터. 원점 x = -18,041,000, y = 9,000,000.
연구 범위에 걸친 타일 창만 읽어 100 m 칸 사각형(인구 열 pop)으로 돌려준다.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from shapely.geometry import box

from ..fetch import log_source

BASE = ("https://jeodpp.jrc.ec.europa.eu/ftp/jrc-opendata/GHSL/GHS_POP_GLOBE_R2023A/"
        "GHS_POP_E2025_GLOBE_R2023A_54009_100/V1-0/tiles/")
NAME = "GHS_POP_E2025_GLOBE_R2023A_54009_100_V1_0_R{r}_C{c}"
X0, Y0, TILE = -18_041_000, 9_000_000, 1_000_000


def ghsl_population(study: gpd.GeoDataFrame, raw_dir) -> gpd.GeoDataFrame:
    cache = raw_dir / "ghsl_pop.parquet"
    if cache.exists():
        return gpd.read_parquet(cache)
    s = study.to_crs("ESRI:54009")
    minx, miny, maxx, maxy = s.total_bounds
    frames = []
    used = []
    for r in range(int((Y0 - maxy) // TILE) + 1, int((Y0 - miny) // TILE) + 2):
        for c in range(int((minx - X0) // TILE) + 1, int((maxx - X0) // TILE) + 2):
            name = NAME.format(r=r, c=c)
            url = f"/vsizip//vsicurl/{BASE}{name}.zip/{name}.tif"
            with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), rasterio.open(url) as src:
                b = src.bounds
                w = from_bounds(max(minx, b.left), max(miny, b.bottom), min(maxx, b.right), min(maxy, b.top), src.transform)
                w = w.round_offsets().round_lengths()
                a = src.read(1, window=w).astype(float)
                tr = src.window_transform(w)
                nod = src.nodata
            used.append(name)
            if nod is not None:
                a[a == nod] = 0
            rr, cc = np.nonzero(a > 0)
            if not len(rr):
                continue
            xs = tr.c + cc * tr.a
            ys = tr.f + rr * tr.e
            geoms = [box(x, y + tr.e, x + tr.a, y) for x, y in zip(xs, ys, strict=True)]
            frames.append(gpd.GeoDataFrame({"pop": a[rr, cc]}, geometry=geoms, crs="ESRI:54009"))
    out = gpd.GeoDataFrame(np.concatenate([f.values for f in frames]) if frames else [], columns=["pop", "geometry"],
                           geometry="geometry", crs="ESRI:54009").to_crs("EPSG:4326") if frames else gpd.GeoDataFrame(
        {"pop": []}, geometry=[], crs="EPSG:4326")
    out["pop"] = out["pop"].astype(float)
    out.to_parquet(cache)
    log_source(raw_dir, "ghsl_pop", source="GHSL GHS-POP E2025 R2023A 100 m (JRC)", tiles=used)
    return out
