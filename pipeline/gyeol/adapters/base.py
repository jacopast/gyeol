"""데이터 어댑터 계약.

어떤 도시든 같은 레이어 스키마로 바꿔 주면 나머지 파이프라인(보행망·격자·래스터·지표)은 그대로 돈다.
모든 메서드는 WGS84 GeoDataFrame(또는 DataFrame)을 돌려주고, 데이터가 없으면 None(= 화면의 "데이터 없음").

레이어 스키마
- target           : Polygon 1개. 분석 대상 (셀은 여기만 화면에 보인다)
- land             : Polygon. 연구 범위(대상+버퍼) 안의 땅. 물은 빠진다. 래스터의 유효 영역
- open_spaces      : Polygon/Point. id, name, kind, access(free|conditional|restricted), area_m2(점일 때 필수), source
                     kind ∈ park, garden, greenway, waterfront, nature, plaza, playground, schoolyard, pops, other
- temporary_spaces : LineString/Polygon (Open Streets 등). 정의에 넣지 않고 레이어로만
- sidewalks        : Polygon. 보도
- roadways         : Polygon. 차로(차도 노면)
- centerlines      : LineString. 보도가 딸린 가로 중심선, width_m(선택)
- buildings        : Polygon. height_m(없으면 NaN)
- pop_night        : Polygon. pop (야간 = 거주 인구)
- pop_day          : Polygon. jobs (주간 = 일자리 수)
- landuse          : Point/Polygon. category(문자열), area_m2
- income           : Polygon. income (지역 통화, 연 중위 가구소득)
- pois             : Point. key(shop|amenity), value
- labels           : Polygon. places_* 등 외부 라벨 열
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import geopandas as gpd
import pandas as pd

OPEN_SPACE_COLUMNS = ["id", "name", "kind", "access", "area_m2", "source", "geometry"]

# 소비 공간 근접성(5.2): 상점·음식·서비스 중 '소비를 전제로 열리는' 곳만. 공공시설(벤치, 화장실 등)은 제외
CONSUMER_AMENITIES = [
    "restaurant", "cafe", "bar", "pub", "fast_food", "ice_cream", "food_court", "biergarten",
    "pharmacy", "bank", "marketplace", "cinema", "theatre", "nightclub", "dentist", "doctors",
    "clinic", "veterinary", "post_office", "laundry", "car_wash", "fuel", "bureau_de_change",
]


class Adapter(ABC):
    def __init__(self, region: dict, params: dict, raw_dir):
        self.region = region
        self.params = params
        self.raw = raw_dir

    # 모든 어댑터가 반드시 제공
    @abstractmethod
    def target(self) -> gpd.GeoDataFrame: ...

    @abstractmethod
    def land(self, study: gpd.GeoDataFrame) -> gpd.GeoDataFrame: ...

    @abstractmethod
    def open_spaces(self, study: gpd.GeoDataFrame) -> gpd.GeoDataFrame: ...

    # 없으면 None
    def temporary_spaces(self, study) -> gpd.GeoDataFrame | None:
        return None

    def sidewalks(self, study) -> gpd.GeoDataFrame | None:
        return None

    def roadways(self, study) -> gpd.GeoDataFrame | None:
        return None

    def centerlines(self, study) -> gpd.GeoDataFrame | None:
        return None

    def buildings(self, study) -> gpd.GeoDataFrame | None:
        return None

    def pop_night(self, study) -> gpd.GeoDataFrame | None:
        return None

    def pop_day(self, study) -> gpd.GeoDataFrame | None:
        return None

    def landuse(self, study) -> gpd.GeoDataFrame | None:
        return None

    def income(self, study) -> gpd.GeoDataFrame | None:
        return None

    def pois(self, study) -> gpd.GeoDataFrame | None:
        return None

    def labels(self, study) -> gpd.GeoDataFrame | None:
        return None

    def versions(self) -> dict:
        """데이터 출처별 버전·날짜 (REPORT용)."""
        return {}


def ensure_open_space_schema(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    for c in OPEN_SPACE_COLUMNS:
        if c not in gdf.columns:
            gdf[c] = None
    return gpd.GeoDataFrame(gdf[OPEN_SPACE_COLUMNS], crs=gdf.crs)


def empty(crs="EPSG:4326") -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(geometry=[], crs=crs)


def concat(frames: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    frames = [f for f in frames if f is not None and len(f)]
    if not frames:
        return empty()
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
