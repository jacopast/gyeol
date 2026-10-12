# 설계안 템플릿

결은 설계안을 **GeoJSON FeatureCollection 하나**로 받는다 (SPEC 9.6). `design_template.geojson`은 맨해튼 Hell's Kitchen의 한 블록을 실제 데이터에서 잘라 만든 예제이며 앱의 "예제 설계안"과 같다(`make_template.py`로 다시 만들 수 있다). 예제의 개입(포켓파크, 블록 중간 통로, 차로 하나 줄이기)은 형식을 보여 주기 위한 것이지 제안이 아니다.

## 규칙

- 좌표계는 **WGS84 경위도**(EPSG:4326), 좌표 순서 `[경도, 위도]`.
- 모든 피처에 `properties.layer`가 있어야 한다.
- `boundary`는 정확히 1개. **경계 안의 기존 데이터는 설계안으로 통째로 바뀐다** — 남길 기존 공간·보도·차로·건물도 설계안에 다시 그려야 한다. 경계 안에서 아무 레이어도 없는 땅은 사적 공간으로 본다.
- 보행망은 경계 안에서도 그대로 두고, `ped_link`로 더하고 `barrier`로 끊는다.

| `layer` | 도형 | 필수 속성 | 선택 속성 | 의미 |
| --- | --- | --- | --- | --- |
| `boundary` | Polygon | — | — | 대상지 경계 |
| `open_space` | Polygon | `access`: `free`/`conditional`/`restricted`, `kind`(park, plaza, playground, garden, schoolyard, pops, greenway, waterfront …), `green_ratio`(0~1) | `id`(출입구가 가리킬 때), `hours` | 공공공간. 면적이 `min_area_m2`(400 m²)보다 작으면 공간으로 세지 않는다 |
| `entrance` | Point | `serves`: open_space의 `id` | — | 출입구. 없으면 경계를 50 m 간격으로 샘플해 40 m 안의 보행 노드를 출입구로 |
| `sidewalk` | Polygon | — | `clear_width_m` | 보도 |
| `roadway` | Polygon | `lanes`(정수), `use`: car/bus/bike/loading | — | 차로 |
| `building` | Polygon | `height_m`, `ground_use` | `units`, `jobs` | 건물. 하나라도 `units`가 있으면 대상지 인구를 `units × 가구당 인원`(센서스 블록의 인구÷주택 수, 맨해튼 1.854)으로 바꾼다. `jobs`도 같은 방식 |
| `ped_link` | LineString | — | — | 새 보행 통로. 양 끝을 120 m 안의 보행 노드에 잇는다 |
| `barrier` | LineString | — | — | 막힌 경로. 가로지르는 보행 링크를 지운다 |
| `frontage` | LineString | `doors_per_100m`, `transparency`(0~1) | — | 건물 전면. 대상지 `frontage_permeability` = 길이 가중 평균 출입구 수 |

검증 오류는 앱 패널에 한 줄씩 나온다(예: `피처 4 (roadway): use 없음 또는 잘못됨 (car / bus / bike / loading)`).

## CAD 레이어 → 스키마

| CAD 레이어 (예) | 결 `layer` | 할 일 |
| --- | --- | --- |
| `SITE`, `PROPERTY LINE` | `boundary` | 닫힌 폴리라인 1개 |
| `LS-PARK`, `PLAZA`, `PLAY` | `open_space` | 해치 경계를 닫힌 폴리라인으로. 속성 `access`, `kind`, `green_ratio`(식재 면적 ÷ 공간 면적) |
| `ENTRY` | `entrance` | 점. `serves`에 공간 id |
| `SIDEWALK`, `CURB` 안쪽 | `sidewalk` | 보도 면 |
| `ROADBED`, `TRAVEL LANE` | `roadway` | 차로 면, `lanes`, `use` |
| `BLDG`, `FOOTPRINT` | `building` | 외곽선 + `height_m`(m), `ground_use` |
| `PATH`, `PASSAGE` | `ped_link` | 중심선 |
| `FENCE`, `WALL` | `barrier` | 중심선 |
| `FACADE`, `STOREFRONT` | `frontage` | 전면선 + `doors_per_100m`, `transparency` |

## 도면 좌표 → WGS84

뉴욕 도면은 보통 NY State Plane Long Island(ft, **EPSG:2263**)이다. 다른 도시는 그 도시의 평면 좌표계 EPSG 번호를 쓴다.

```bash
# DXF/DWG에서 레이어별로 내보낸 뒤 (GDAL)
ogr2ogr -f GeoJSON -s_srs EPSG:2263 -t_srs EPSG:4326 park.geojson drawing.dxf -sql "SELECT * FROM entities WHERE Layer = 'LS-PARK'"
```

QGIS: 레이어 → 다른 이름으로 저장 → GeoJSON, 좌표계 EPSG:4326. 그런 다음 각 피처에 `layer`와 필수 속성을 넣고 한 파일로 합친다. Rhino에서는 GIS 플러그인으로 같은 작업을 할 수 있다.

## 한계 (1차 버전)

- 경계를 걸친 셀은 경계 밖 몫을 기존 값의 면적 비례로 남기고 안쪽만 새로 센다(픽셀 단위 기존 지도는 웹에 없음). 경계에서 이웃 쌍 수가 조금 어긋난다.
- 가로 중심선 길이는 설계안이 바꾸지 않는다(스키마에 중심선 레이어가 없음). 그래서 보도 폭·위요감은 보도·차로 면적과 건물 높이 변화만 반영한다.
- 가로변 건물 높이는 대상지 안 건물 전부를 쓴다(가로에서 25 m 안이라는 조건을 설계안에서는 확인하지 않음).
- 대상지 안 최대 공공 패치는 대상지 밖 공원과 이어지는지 모른다 → 기존 값과 새 값 중 큰 쪽.
- 접근성은 대상지에서 1 km 안 셀만 다시 계산한다(전후 모두 같은 브라우저 엔진으로).


## 동네 표본과 비교할 때 (2026-10-12)

대상지 전후 표와 동네 비교의 범위는 다릅니다. 전후 표는 boundary 내부이고, 동네 비교는 boundary 경계 상자 중심의 최근접 기존 보행 노드에서 시작하는 5분·10분 보행권입니다. 출발점은 전후 고정하며 새 통로·장벽에 따라 도달 범위가 달라질 수 있습니다. 화면의 좌표와 지도 점으로 출발점이 적절한지 확인하세요.

같은 지역·계산 버전·보행 시간·공간 정의·감쇠·α·β의 표본만 비교합니다. 설정을 바꾸면 설계안이 재계산되며 다른 조건의 저장 표본은 제외 이유가 표시됩니다. 설계안의 건강 라벨은 예측하지 않습니다. 구현과 후속 검증은 [개발 재개 안내](../docs/CONTINUATION.md)를 참고하세요.
