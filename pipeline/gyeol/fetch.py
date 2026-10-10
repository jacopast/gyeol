"""다운로드 도우미. 모든 다운로드는 스크립트로 재현 가능해야 한다 (SPEC 9.3).

받은 원본은 data/raw/<region>/ 에 캐시하고, 출처·시각을 sources.json에 남긴다.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

UA = {"User-Agent": "gyeol-pipeline/0.1 (https://github.com/jacopast/gyeol)"}


def log_source(raw_dir: Path, key: str, **info) -> None:
    p = raw_dir / "sources.json"
    d = json.loads(p.read_text()) if p.exists() else {}
    d[key] = {**info, "fetched": datetime.now(UTC).isoformat(timespec="seconds")}
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2))


def download(url: str, dest: Path, retries: int = 3) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for i in range(retries):
        try:
            with requests.get(url, headers=UA, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.rename(dest)
            return dest
        except requests.RequestException:
            if i == retries - 1:
                raise
            time.sleep(3 * (i + 1))
    return dest


def socrata_geo(
    domain: str,
    dataset: str,
    geom_col: str,
    bbox: tuple[float, float, float, float],
    where: str | None = None,
    select: str | None = None,
    page: int = 20000,
) -> gpd.GeoDataFrame:
    """Socrata 데이터셋에서 bbox와 겹치는 피처를 전부 GeoJSON으로 받는다."""
    w, s, e, n = bbox
    poly = f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"
    clause = f"intersects({geom_col}, '{poly}')"
    if where:
        clause = f"({clause}) AND ({where})"
    frames = []
    offset = 0
    while True:
        params = {"$where": clause, "$limit": page, "$offset": offset, "$order": ":id"}
        if select:
            params["$select"] = select
        r = _get(f"https://{domain}/resource/{dataset}.geojson", params)
        feats = r.json().get("features", [])
        if not feats:
            break
        frames.append(gpd.GeoDataFrame.from_features(feats, crs="EPSG:4326"))
        if len(feats) < page:
            break
        offset += page
    if not frames:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")


def socrata_rows(domain: str, dataset: str, where: str, select: str | None = None, page: int = 50000) -> pd.DataFrame:
    frames, offset = [], 0
    while True:
        params = {"$where": where, "$limit": page, "$offset": offset, "$order": ":id"}
        if select:
            params["$select"] = select
        rows = _get(f"https://{domain}/resource/{dataset}.json", params).json()
        if not rows:
            break
        frames.append(pd.DataFrame(rows))
        if len(rows) < page:
            break
        offset += page
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _get(url: str, params: dict) -> requests.Response:
    for i in range(4):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=300)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if i == 3:
                raise
            time.sleep(5 * (i + 1))
    raise RuntimeError("unreachable")


def cached(path: Path, build) -> gpd.GeoDataFrame | pd.DataFrame:
    """parquet 캐시. build()가 None을 돌려주면 None (데이터 없음)."""
    if path.exists():
        try:
            return gpd.read_parquet(path)
        except (ValueError, KeyError):
            return pd.read_parquet(path)
    out = build()
    if out is None:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path)
    return out
