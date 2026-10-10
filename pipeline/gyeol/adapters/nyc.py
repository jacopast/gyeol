"""뉴욕 어댑터 — NYC Open Data(Socrata)·센서스·CDC 공식 데이터로 레이어를 덮어쓴다.

없는 레이어(POI 등)는 osm_global로 떨어진다. 데이터셋 ID는 2026-10-10에 카탈로그 API로 확인했다.
"""

from __future__ import annotations

import gzip
import re

import geopandas as gpd
import numpy as np
import pandas as pd

from ..fetch import cached, download, log_source, socrata_geo, socrata_rows
from .base import concat, ensure_open_space_schema
from .osm_global import OSMGlobalAdapter

NYC = "data.cityofnewyork.us"
DS = {
    "boroughs": ("gthc-hcne", "the_geom"),
    "parks": ("enfh-gkve", "multipolygon"),
    "plazas": ("k5k6-6jex", "the_geom"),
    "pops": ("rvih-nhyn", None),            # 점(위경도) + 요구 면적 텍스트
    "wpaa": ("388s-pnvc", "the_geom"),
    "schoolyards": ("bbtf-6p3c", "multipolygon"),
    "open_streets": ("uiay-nctu", "the_geom"),
    "sidewalks": ("52n9-sdep", "the_geom"),
    "roadbed": ("i36f-5ih7", "the_geom"),
    "buildings": ("5zhs-2jue", "the_geom"),
    "blocks": ("wmsu-5muw", "the_geom"),
    "tracts": ("63ge-mke6", "the_geom"),
    "centerline": ("inkn-q76z", "the_geom"),
    "pluto": ("64uk-42ks", None),
}
PLACES = ("data.cdc.gov", "yjkw-uj5s", "PLACES 2025 release, census tract (GIS friendly)")
TIGER_BLOCKS = "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_{st}_tabblock20.zip"
LODES_WAC = "https://lehd.ces.census.gov/data/lodes/LODES8/{st_abbr}/wac/{st_abbr}_wac_S000_JT00_{year}.csv.gz"
LODES_YEAR = 2023
ACS_B19013 = "https://www2.census.gov/programs-surveys/acs/summary_file/{y}/table-based-SF/data/5YRData/acsdt5y{y}-b19013.dat"
ACS_YEAR = 2024
PLACES_FIELDS = ["obesity", "depression", "lpa", "mhlth", "bphigh", "diabetes", "phlth"]

# NYC Parks typecategory → (kind, access). 실내 시설·운영 부지는 공공공간에서 뺀다
PARK_KIND = {
    "Flagship Park": ("park", "free"), "Community Park": ("park", "free"), "Neighborhood Park": ("park", "free"),
    "Nature Area": ("nature", "free"), "Garden": ("garden", "conditional"),   # 커뮤니티 가든: 개방 시간 제한 (4.2)
    "Playground": ("playground", "free"), "Jointly Operated Playground": ("playground", "free"),
    "Recreational Field/Courts": ("playground", "free"), "Triangle/Plaza": ("plaza", "free"),
    "Mall": ("greenway", "free"), "Strip": ("greenway", "free"), "Parkway": ("greenway", "free"),
    "Waterfront Facility": ("waterfront", "free"), "Historic House Park": ("park", "conditional"),
    "Managed Sites": ("park", "conditional"), "Cemetery": ("nature", "conditional"), "Golf Course": ("park", "conditional"),
    "Undeveloped": ("other", "restricted"), "Buildings/Institutions": ("other", "restricted"),
    "Operations": ("other", "restricted"), "Lot": ("other", "restricted"), "Retired N/A": ("other", "restricted"),
}
SQFT = 0.09290304

# PLUTO landuse 코드 → 이름 (용도 혼합 엔트로피용)
PLUTO_LANDUSE = {
    "1": "res_1_2fam", "2": "res_multi_walkup", "3": "res_multi_elevator", "4": "mixed_res_com", "5": "commercial_office",
    "6": "industrial", "7": "transport_utility", "8": "public_institution", "9": "open_space_recreation",
    "10": "parking", "11": "vacant",
}


def _bbox(study: gpd.GeoDataFrame):
    return tuple(study.to_crs("EPSG:4326").total_bounds)


class NYCAdapter(OSMGlobalAdapter):
    def _soc(self, key: str, study, where=None, select=None):
        ds, col = DS[key]
        g = cached(self.raw / f"nyc_{key}.parquet", lambda: socrata_geo(NYC, ds, col, _bbox(study), where, select))
        log_source(self.raw, f"nyc_{key}", source=f"NYC Open Data {ds}", url=f"https://{NYC}/d/{ds}")
        return g

    @property
    def cfg(self):
        return self.region["nyc"]

    # ---- 필수 ----
    def target(self):
        boro = self.region["target"]["nyc_borocode"]

        def build():
            ds, col = DS["boroughs"]
            from ..fetch import _get
            r = _get(f"https://{NYC}/resource/{ds}.geojson", {"borocode": boro})
            return gpd.GeoDataFrame.from_features(r.json()["features"], crs="EPSG:4326")[["geometry"]]

        g = cached(self.raw / "target.parquet", build)
        log_source(self.raw, "target", source=f"NYC Open Data {DS['boroughs'][0]} (shoreline-clipped)", borocode=boro)
        return g

    def land(self, study):
        # 버퍼 안의 뉴욕 땅 (해안선으로 잘린 보로 경계). 버퍼가 닿는 뉴저지는 데이터가 없어 땅에서 빠진다 → 한계
        g = self._soc("boroughs", study)
        poly = g.geometry.union_all().intersection(study.to_crs("EPSG:4326").geometry.union_all())
        return gpd.GeoDataFrame(geometry=[poly], crs="EPSG:4326")

    def open_spaces(self, study):
        frames = []
        parks = self._soc("parks", study, select="gispropnum,signname,typecategory,multipolygon")
        km = parks["typecategory"].map(lambda t: PARK_KIND.get(t, ("other", "restricted")))
        frames.append(gpd.GeoDataFrame({
            "id": "park_" + parks["gispropnum"].astype(str) + "_" + parks.index.astype(str),
            "name": parks["signname"], "kind": km.str[0], "access": km.str[1], "area_m2": None, "source": "nyc_parks",
        }, geometry=parks.geometry, crs="EPSG:4326"))

        plazas = self._soc("plazas", study)
        frames.append(gpd.GeoDataFrame({
            "id": "plaza_" + plazas["objectid"].astype(str), "name": plazas["plazaname"], "kind": "plaza",
            "access": "free", "area_m2": None, "source": "nyc_dot_plazas",
        }, geometry=plazas.geometry, crs="EPSG:4326"))

        wpaa = self._soc("wpaa", study)
        frames.append(gpd.GeoDataFrame({
            "id": "wpaa_" + wpaa["wpaa_id"].astype(str), "name": wpaa["name"], "kind": "waterfront",
            "access": "free", "area_m2": None, "source": "nyc_wpaa",
        }, geometry=wpaa.geometry, crs="EPSG:4326"))

        sy = self._soc("schoolyards", study)
        frames.append(gpd.GeoDataFrame({
            "id": "schoolyard_" + sy["gispropnum"].astype(str) + "_" + sy.index.astype(str), "name": sy["location"],
            "kind": "schoolyard", "access": "conditional", "area_m2": None, "source": "nyc_schoolyards_to_playgrounds",
        }, geometry=sy.geometry, crs="EPSG:4326"))

        frames.append(self._pops(study))
        # 공식 데이터에 없는 공공공간(주립 Hudson River Park, Battery Park City, Governors Island 등)은
        # OSM으로 보충한다. 겹침 정리는 layers.dedupe_open_spaces가 출처 순서(공식 먼저)로 한다
        frames.append(super().open_spaces(study))
        out = concat(frames)
        out = out[out.geometry.notna() & ~out.geometry.is_empty]
        return ensure_open_space_schema(out)

    def _pops(self, study):
        w, s, e, n = _bbox(study)

        def build():
            df = socrata_rows(NYC, DS["pops"][0],
                              f"latitude between {s} and {n} AND longitude between {w} and {e}")
            df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
            df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
            df = df.dropna(subset=["latitude", "longitude"])
            return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs="EPSG:4326")

        p = cached(self.raw / "nyc_pops.parquet", build)
        log_source(self.raw, "nyc_pops", source=f"NYC Open Data {DS['pops'][0]}")
        # 요구 면적 텍스트("Plaza 5879.50 sf; Arcade 2761.00 sf")의 합. 실내형(arcade 등)도 포함 — 한계로 기록
        area = p.get("size_required", pd.Series(None, index=p.index)).fillna("").map(
            lambda t: sum(float(x) for x in re.findall(r"([\d.]+)\s*sf", t)) * SQFT)
        return gpd.GeoDataFrame({
            "id": "pops_" + p["pops_number"].astype(str), "name": p.get("building_name"), "kind": "pops",
            "access": "conditional", "area_m2": area.replace(0, np.nan), "source": "nyc_pops",
        }, geometry=p.geometry, crs="EPSG:4326")

    # ---- 선택 ----
    def temporary_spaces(self, study):
        return self._soc("open_streets", study, select="appronstre,apprdayswe,the_geom")

    def sidewalks(self, study):
        return self._soc("sidewalks", study, select="the_geom")

    def roadways(self, study):
        return self._soc("roadbed", study, select="the_geom")

    def centerlines(self, study):
        # 보도가 딸린 가로만: rw_type 1(Street), 10(Alley). 고속도로·램프·교량·보행로는 제외
        c = self._soc("centerline", study, where="rw_type in ('1','10')", select="rw_type,streetwidth,the_geom")
        width = pd.to_numeric(c["streetwidth"], errors="coerce") * 0.3048
        return gpd.GeoDataFrame({"width_m": width}, geometry=c.geometry, crs="EPSG:4326")

    def buildings(self, study):
        b = self._soc("buildings", study, select="height_roof,ground_elevation,the_geom")
        h = pd.to_numeric(b["height_roof"], errors="coerce") * 0.3048
        return gpd.GeoDataFrame({"height_m": h.where(h > 0)}, geometry=b.geometry, crs="EPSG:4326")

    def _blocks(self, study):
        """2020 센서스 블록: TIGER tabblock20 (POP20 포함) — Census API가 키를 요구해서 대체."""
        st = self.cfg["state_fips"]
        counties = self.cfg["county_fips"]

        def build():
            z = download(TIGER_BLOCKS.format(st=st), self.raw / f"tl_2020_{st}_tabblock20.zip")
            g = gpd.read_file(f"zip://{z}", where=f"COUNTYFP20 IN ({','.join(repr(c) for c in counties)})")
            g = g.to_crs("EPSG:4326")
            g = g[g.intersects(study.to_crs("EPSG:4326").geometry.union_all())]
            return g[["GEOID20", "POP20", "HOUSING20", "ALAND20", "geometry"]]

        g = cached(self.raw / "census_blocks.parquet", build)
        z = self.raw / f"tl_2020_{st}_tabblock20.zip"
        if z.exists():
            z.unlink()   # 325MB 원본은 필요한 카운티만 뽑은 뒤 지운다 (가벼운 데이터 원칙)
        log_source(self.raw, "census_blocks", source="US Census TIGER/Line 2020 TABBLOCK20 (POP20)",
                   url=TIGER_BLOCKS.format(st=st))
        return g

    def pop_night(self, study):
        b = self._blocks(study)
        return gpd.GeoDataFrame({"pop": b["POP20"].astype(float)}, geometry=b.geometry, crs="EPSG:4326")

    def pop_day(self, study):
        b = self._blocks(study)
        abbr = self.cfg.get("state_abbr", "ny")

        def build():
            f = download(LODES_WAC.format(st_abbr=abbr, year=LODES_YEAR), self.raw / f"{abbr}_wac_{LODES_YEAR}.csv.gz")
            with gzip.open(f, "rt") as fh:
                df = pd.read_csv(fh, usecols=["w_geocode", "C000"], dtype={"w_geocode": str})
            return df

        w = cached(self.raw / f"lodes_wac_{LODES_YEAR}.parquet", build)
        log_source(self.raw, "lodes_wac", source=f"LEHD LODES8 WAC S000 JT00 {LODES_YEAR}",
                   url=LODES_WAC.format(st_abbr=abbr, year=LODES_YEAR))
        m = b.merge(w, left_on="GEOID20", right_on="w_geocode", how="left")
        return gpd.GeoDataFrame({"jobs": m["C000"].fillna(0).astype(float)}, geometry=m.geometry, crs="EPSG:4326")

    def _tracts(self, study):
        return self._soc("tracts", study, select="geoid,the_geom")

    def income(self, study):
        t = self._tracts(study)

        def build():
            f = download(ACS_B19013.format(y=ACS_YEAR), self.raw / f"acs5_{ACS_YEAR}_b19013.dat")
            df = pd.read_csv(f, sep="|", dtype=str)
            df = df[df["GEO_ID"].str.startswith("1400000US" + self.cfg["state_fips"])]
            return pd.DataFrame({"geoid": df["GEO_ID"].str[-11:],
                                 "income": pd.to_numeric(df["B19013_E001"], errors="coerce")})

        inc = cached(self.raw / f"acs5_{ACS_YEAR}_b19013.parquet", build)
        f = self.raw / f"acs5_{ACS_YEAR}_b19013.dat"
        if f.exists():
            f.unlink()
        log_source(self.raw, "acs_income", source=f"ACS 5-year {ACS_YEAR} B19013 table-based summary file",
                   url=ACS_B19013.format(y=ACS_YEAR))
        m = t.merge(inc, on="geoid", how="left")
        # ACS 결측 코드(음수)는 데이터 없음
        m["income"] = m["income"].where(m["income"] > 0)
        return gpd.GeoDataFrame({"geoid": m["geoid"], "income": m["income"]}, geometry=m.geometry, crs="EPSG:4326")

    def landuse(self, study):
        w, s, e, n = _bbox(study)

        def build():
            df = socrata_rows(NYC, DS["pluto"][0],
                              f"latitude between {s} and {n} AND longitude between {w} and {e}",
                              select="bbl,landuse,lotarea,latitude,longitude")
            for c in ["lotarea", "latitude", "longitude"]:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=["latitude", "longitude"])
            return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs="EPSG:4326")

        p = cached(self.raw / "nyc_pluto.parquet", build)
        log_source(self.raw, "nyc_pluto", source=f"NYC Open Data {DS['pluto'][0]} (PLUTO)")
        cat = p["landuse"].astype(str).str.replace(r"\.0$", "", regex=True).map(PLUTO_LANDUSE)
        ok = cat.notna()
        return gpd.GeoDataFrame({"category": cat[ok].values, "area_m2": (p.loc[ok, "lotarea"] * SQFT).values},
                                geometry=p.geometry[ok].values, crs="EPSG:4326")

    def labels(self, study):
        t = self._tracts(study)
        dom, ds, desc = PLACES
        counties = ",".join(f"'{self.cfg['state_fips']}{c}'" for c in self.cfg["county_fips"])

        def build():
            sel = "tractfips," + ",".join(f"{f}_crudeprev" for f in PLACES_FIELDS)
            return socrata_rows(dom, ds, f"countyfips in ({counties})", select=sel)

        df = cached(self.raw / "places_2025.parquet", build)
        log_source(self.raw, "places", source=desc, url=f"https://{dom}/d/{ds}")
        out = t.merge(df, left_on="geoid", right_on="tractfips", how="left")
        cols = {f"{f}_crudeprev": f"places_{f}" for f in PLACES_FIELDS}
        out = out.rename(columns=cols)
        for c in cols.values():
            out[c] = pd.to_numeric(out[c], errors="coerce")
        return gpd.GeoDataFrame(out[["geoid", *cols.values()]], geometry=out.geometry, crs="EPSG:4326")

    def versions(self):
        return {
            "census_blocks": "TIGER/Line 2020 TABBLOCK20",
            "lodes": f"LODES8 WAC {LODES_YEAR}",
            "acs_income": f"ACS 5-year {ACS_YEAR} B19013",
            "places": PLACES[2],
        }

