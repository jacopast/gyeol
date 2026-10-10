"""파라미터·지역 설정 로드. 모든 지표 코드는 값을 여기서만 읽는다."""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
WEB_DATA = ROOT / "web" / "public" / "data"


@cache
def params() -> dict:
    return yaml.safe_load((CONFIG / "params.yaml").read_text())


def params_hash() -> str:
    """params.yaml 원문의 sha256 앞 12자. 표본에 붙여 비교 가능성을 판정한다."""
    return hashlib.sha256((CONFIG / "params.yaml").read_bytes()).hexdigest()[:12]


def region(region_id: str) -> dict:
    return yaml.safe_load((CONFIG / "regions" / f"{region_id}.yaml").read_text())


def region_dirs(region_id: str) -> dict[str, Path]:
    d = {
        "raw": DATA / "raw" / region_id,
        "processed": DATA / "processed" / region_id,
        "web": WEB_DATA / "regions" / region_id,
    }
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    return d
