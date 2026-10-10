"""녹지성: Sentinel-2 L2A NDVI (Earth Search STAC, 키 없음, 전 세계 공통).

여름철 구름 적은 장면부터 대상 격자로 재투영해 채운다. 여러 타일·장면을 써서 빈 곳을 메운다.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject

from .fetch import UA, log_source
from .raster import Grid

STAC = "https://earth-search.aws.element84.com/v1/search"


def search(bbox_wgs, year: int, months: list[int], max_cloud: float) -> list[dict]:
    m0, m1 = min(months), max(months)
    end_day = 30 if m1 in (4, 6, 9, 11) else 28 if m1 == 2 else 31
    body = {
        "collections": ["sentinel-2-l2a"], "bbox": list(bbox_wgs),
        "datetime": f"{year}-{m0:02d}-01T00:00:00Z/{year}-{m1:02d}-{end_day}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": max_cloud}}, "limit": 100,
    }
    r = requests.post(STAC, json=body, headers=UA, timeout=120)
    r.raise_for_status()
    feats = r.json()["features"]
    return sorted(feats, key=lambda f: f["properties"]["eo:cloud_cover"])


def ndvi_on_grid(grid: Grid, crs: str, bbox_wgs, cfg: dict, raw_dir: Path, valid_mask: np.ndarray) -> tuple[np.ndarray, list[str]]:
    cache = raw_dir / "ndvi.npy"
    meta = raw_dir / "ndvi_items.json"
    if cache.exists() and meta.exists():
        return np.load(cache), json.loads(meta.read_text())
    items = search(bbox_wgs, cfg["year"], cfg["season_months"], cfg["max_cloud_pct"])
    out = np.full((grid.height, grid.width), np.nan, dtype=np.float32)
    used = []
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", AWS_NO_SIGN_REQUEST="YES"):
        for it in items[:8]:
            need = np.isnan(out) & valid_mask
            if not need.any():
                break
            bands = {}
            for b in ("red", "nir"):
                dst = np.full(out.shape, np.nan, dtype=np.float32)
                with rasterio.open(it["assets"][b]["href"]) as src:
                    reproject(rasterio.band(src, 1), dst, dst_transform=grid.transform, dst_crs=crs,
                              resampling=Resampling.bilinear, src_nodata=0, dst_nodata=np.nan)
                bands[b] = dst
            with np.errstate(invalid="ignore", divide="ignore"):
                nd = (bands["nir"] - bands["red"]) / (bands["nir"] + bands["red"])
            fill = need & np.isfinite(nd)
            out[fill] = nd[fill]
            used.append(it["id"])
    np.save(cache, out)
    meta.write_text(json.dumps(used))
    log_source(raw_dir, "ndvi", source="Sentinel-2 L2A via Earth Search STAC (element84)", items=used)
    return out, used
