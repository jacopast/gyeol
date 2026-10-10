"""어댑터 레지스트리. 새 도시는 config/regions/<id>.yaml의 adapter 이름으로 고른다."""

from .nyc import NYCAdapter
from .osm_global import OSMGlobalAdapter

ADAPTERS = {"osm_global": OSMGlobalAdapter, "nyc": NYCAdapter}


def get_adapter(region: dict, params: dict, raw_dir):
    return ADAPTERS[region.get("adapter", "osm_global")](region, params, raw_dir)
