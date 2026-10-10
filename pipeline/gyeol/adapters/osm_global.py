"""전 세계 기본 어댑터 — OpenStreetMap만으로 레이어를 만든다.

어떤 도시든 config/regions/<id>.yaml 에 `adapter: osm_global`과 `target.osm_query`만 적으면 동작한다.
OSM에는 보도 면이 거의 없으므로 보도·차로는 가로 중심선을 폭으로 버퍼링한 **근사**다 (지역마다 정확도가 다름).
인구는 GHSL(전지구 100m 격자) — 지역 설정 `osm_global.population: ghsl`이면 쓰고, 없으면 None.
"""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd

from ..fetch import cached, log_source
from .base import CONSUMER_AMENITIES, Adapter, concat, ensure_open_space_schema

ox.settings.use_cache = True
ox.settings.log_console = False

# OSM 태그 → kind, access. 대칭성: 큰 공원·작은 광장 모두 같은 규칙으로 들어온다
OPEN_SPACE_TAGS = {
    "leisure": ["park", "garden", "playground", "nature_reserve", "dog_park", "fitness_station", "pitch", "common"],
    "place": ["square"],
    "highway": ["pedestrian"],
    "landuse": ["recreation_ground", "village_green"],
}

# 차로 폭 근사 (차로당 m) 와 보도 폭 근사 (한쪽 m). 지역마다 다를 수 있으므로 메타데이터에 남긴다
LANE_M = 3.2
SIDEWALK_GUESS_M = {"primary": 4.0, "secondary": 3.5, "tertiary": 3.0, "residential": 2.5}
DRIVE_HIGHWAYS = ["motorway", "trunk", "primary", "secondary", "tertiary", "residential", "unclassified", "living_street", "service"]
STREET_HIGHWAYS = ["primary", "secondary", "tertiary", "residential", "unclassified", "living_street"]


def _poly(study: gpd.GeoDataFrame):
    return study.to_crs("EPSG:4326").geometry.union_all()


class OSMGlobalAdapter(Adapter):
    def _features(self, name: str, study, tags: dict) -> gpd.GeoDataFrame:
        def build():
            try:
                g = ox.features_from_polygon(_poly(study), tags)
            except ox._errors.InsufficientResponseError:
                return gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            g = g.reset_index()
            keep = [c for c in ["element", "id", "name", "geometry", "height", "building:levels", "access", "opening_hours",
                                "lanes", "width", "sidewalk", *tags.keys()] if c in g.columns]
            g = g[keep].copy()
            for c in g.columns:
                if c != "geometry" and g[c].dtype == object:
                    g[c] = g[c].astype(str).where(g[c].notna(), None)
            return gpd.GeoDataFrame(g, geometry="geometry", crs="EPSG:4326")

        out = cached(self.raw / f"osm_{name}.parquet", build)
        log_source(self.raw, f"osm_{name}", source="OpenStreetMap via Overpass (osmnx)", tags=str(tags))
        return out

    # ---- 필수 ----
    def target(self) -> gpd.GeoDataFrame:
        q = self.region["target"]["osm_query"]
        g = cached(self.raw / "target.parquet", lambda: ox.geocode_to_gdf(q)[["geometry"]])
        log_source(self.raw, "target", source="OSM Nominatim", query=q)
        return g

    def land(self, study):
        # 물: natural=water, waterway=riverbank 면. 해안선 바깥 바다는 OSM 면이 없을 수 있다 → 한계로 기록
        water = self._features("water", study, {"natural": ["water", "bay", "strait"], "waterway": ["riverbank"]})
        poly = _poly(study)
        if water is not None and len(water):
            w = water[water.geom_type.isin(["Polygon", "MultiPolygon"])]
            if len(w):
                poly = poly.difference(w.geometry.union_all())
        return gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")

    def open_spaces(self, study):
        g = self._features("open_spaces", study, OPEN_SPACE_TAGS)
        g = g[g.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
        kind = pd.Series("other", index=g.index)
        get = lambda c: g[c] if c in g.columns else pd.Series(None, index=g.index)  # noqa: E731
        leisure, place, highway, landuse = get("leisure"), get("place"), get("highway"), get("landuse")
        kind[leisure.isin(["park", "common", "dog_park"])] = "park"
        kind[landuse.isin(["recreation_ground", "village_green"])] = "park"
        kind[leisure == "garden"] = "garden"
        kind[leisure == "nature_reserve"] = "nature"
        kind[leisure.isin(["playground", "pitch", "fitness_station"])] = "playground"
        kind[(place == "square") | (highway == "pedestrian")] = "plaza"
        acc = get("access").fillna("yes")
        access = np.where(acc.isin(["private", "no"]), "restricted",
                          np.where(acc.isin(["customers", "permissive", "destination"]), "conditional", "free"))
        # OSM 정원(leisure=garden)은 사유 중정이 많다 → 명시적 access=yes/public이 없으면 conditional
        explicit_open = get("access").isin(["yes", "public"])
        access = np.where((kind == "garden") & ~explicit_open & (access == "free"), "conditional", access)
        out = gpd.GeoDataFrame({
            "id": "osm_" + g["element"].astype(str) + "_" + g["id"].astype(str),
            "name": get("name"), "kind": kind, "access": access, "area_m2": None, "source": "osm",
        }, geometry=g.geometry.values, crs="EPSG:4326")
        return ensure_open_space_schema(out)

    # ---- 선택 ----
    def _streets(self, study):
        return self._features("streets", study, {"highway": DRIVE_HIGHWAYS})

    def centerlines(self, study):
        s = self._streets(study)
        s = s[s["highway"].isin(STREET_HIGHWAYS) & s.geom_type.isin(["LineString", "MultiLineString"])]
        width = pd.to_numeric(s.get("width"), errors="coerce") if "width" in s.columns else np.nan
        return gpd.GeoDataFrame({"width_m": width}, geometry=s.geometry.values, crs="EPSG:4326")

    def roadways(self, study):
        s = self._streets(study)
        s = s[s.geom_type.isin(["LineString", "MultiLineString"])]
        lanes = pd.to_numeric(s.get("lanes"), errors="coerce").fillna(2).clip(1, 8) if "lanes" in s.columns else 2
        m = s.to_crs(s.estimate_utm_crs())
        geom = m.geometry.buffer(lanes * LANE_M / 2, cap_style="flat")
        return gpd.GeoDataFrame(geometry=geom, crs=m.crs).to_crs("EPSG:4326")

    def sidewalks(self, study):
        # 근사: 보도가 있을 법한 가로(STREET_HIGHWAYS) 양쪽에 등급별 폭의 띠. sidewalk=no 는 제외
        s = self._streets(study)
        s = s[s["highway"].isin(STREET_HIGHWAYS) & s.geom_type.isin(["LineString", "MultiLineString"])]
        if "sidewalk" in s.columns:
            s = s[~s["sidewalk"].isin(["no", "none"])]
        lanes = pd.to_numeric(s.get("lanes"), errors="coerce").fillna(2).clip(1, 8) if "lanes" in s.columns else 2
        sw = s["highway"].map(SIDEWALK_GUESS_M).fillna(2.0)
        m = s.to_crs(s.estimate_utm_crs())
        half_road = lanes * LANE_M / 2
        outer = m.geometry.buffer(half_road + sw, cap_style="flat")
        inner = m.geometry.buffer(half_road, cap_style="flat")
        return gpd.GeoDataFrame(geometry=outer.difference(inner), crs=m.crs).to_crs("EPSG:4326")

    def buildings(self, study):
        b = self._features("buildings", study, {"building": True})
        b = b[b.geom_type.isin(["Polygon", "MultiPolygon"])]
        h = pd.to_numeric(b.get("height"), errors="coerce") if "height" in b.columns else pd.Series(np.nan, index=b.index)
        lv = pd.to_numeric(b.get("building:levels"), errors="coerce") if "building:levels" in b.columns else np.nan
        h = h.fillna(lv * 3.2)
        return gpd.GeoDataFrame({"height_m": h}, geometry=b.geometry.values, crs="EPSG:4326")

    def landuse(self, study):
        lu = self._features("landuse", study, {"landuse": True})
        lu = lu[lu.geom_type.isin(["Polygon", "MultiPolygon"])]
        m = lu.to_crs(lu.estimate_utm_crs())
        return gpd.GeoDataFrame({"category": lu["landuse"].values, "area_m2": m.area.values},
                                geometry=lu.geometry.representative_point().values, crs="EPSG:4326")

    def pois(self, study):
        p = self._features("pois", study, {"shop": True, "amenity": CONSUMER_AMENITIES})
        p = p.copy()
        p["geometry"] = p.geometry.representative_point()
        rows = []
        for key in ["shop", "amenity"]:
            if key in p.columns:
                sel = p[p[key].notna() & (p[key] != "None")]
                if key == "amenity":
                    sel = sel[sel[key].isin(CONSUMER_AMENITIES)]
                rows.append(gpd.GeoDataFrame({"key": key, "value": sel[key].values}, geometry=sel.geometry.values, crs="EPSG:4326"))
        return concat(rows)

    def pop_night(self, study):
        if self.region.get("osm_global", {}).get("population") != "ghsl":
            return None
        from .ghsl import ghsl_population
        return ghsl_population(study, self.raw)
