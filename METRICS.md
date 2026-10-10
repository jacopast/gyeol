# METRICS — 지표 정의

화면에 보이는 모든 숫자는 이 문서의 ID로 추적된다 (원칙 1.2-5). 파라미터 값은 `config/params.yaml`에서만 읽는다(아래 `p.` 접두어).
코드: 셀 단위 계산 `pipeline/gyeol/build.py`·`metrics/`, 권역 집계 `pipeline/gyeol/sample.py` = 웹 `web/src/engine.ts`.

## 공통 규칙

- **셀**: H3 해상도 `p.grid.h3_resolution`(10, 한 칸 약 0.015 km²). 셀마다 대표 보행 노드 = 셀 중심에서 가장 가까운 노드(`p.grid.max_node_snap_m` 밖이면 보행망 밖 → 데이터 없음).
- **권역(표본)**: 클릭 지점의 최근접 보행 노드에서 다익스트라, 대표 노드까지의 네트워크 거리 ≤ 분 × 60 × `p.walk.speed_mps`인 셀들. 5분 ≈ 360 m, 10분 ≈ 720 m.
- **가산 통계**: 셀마다 면적·픽셀 수·이웃 쌍 수·길이·인구를 저장하고, 권역 지표는 이것들을 **합한 뒤** 비율을 낸다(비율의 평균이 아님). 그래서 어떤 크기의 권역이든 같은 정의가 된다.
- **렌즈**: 접근성 지표는 공간 정의(`green_only` / `with_plaza_playground` / `with_pops`) × 감쇠(`gaussian`/`step`) × α × β의 모든 조합을 미리 계산한다. 화면 기본값 = `p.access.default_*`, 다른 렌즈를 고르면 "임시 실행" 표시.
- **없는 값**: 분모가 0이거나 데이터가 없으면 null → 화면 "데이터 없음". 0으로 채우지 않는다.

## 공공공간

| ID | 정의 | 단위 | 계산 | 데이터 | 알려진 한계 |
| --- | --- | --- | --- | --- | --- |
| `os_gravity` | 공공공간 중력 접근성 | m^(2α) | 셀 i: Σ_j S_j^α · f(d_ij; R_j). R_j = clip(`r0`·(S_j/`s0`)^β, `r_min`, `r_max`). 가우시안 f = (e^(−½(d/R)²) − e^(−½))/(1 − e^(−½)) (d ≤ R). 단계형: scale = R/`r0`, d ≤ `step_inner`·scale → 1, ≤ `step_outer`·scale → `step_mid`. d = 출입구 노드까지 보행망 최단 거리. 권역 = 셀 값의 단순 평균 | 공간 면, 보행망 | 출입구는 경계 샘플(50 m 간격, 40 m 스냅) 근사. 셀→노드 스냅 거리 미가산. 단위가 α마다 달라 α끼리 절댓값 비교 금지 |
| `os_g2sfca_night`, `os_g2sfca_day` | 1인당 공공공간 (혼잡 반영) | m²/인 | 공간 j 비율 = S_j / Σ_k P_k f(d_kj; R_j), 셀 i 값 = Σ_j 비율_j · f(d_ij; R_j). P = 야간 인구 / 일자리. 닿는 인구가 0인 공간은 비율 0. 권역 = 셀 값 평균 | + 인구 | 주간 수요 = 일자리만(방문객 없음). 버퍼 밖 수요는 없음 |
| `os_cover_5`, `os_cover_10` | 보행 5·10분 안에 공공공간이 있는 인구 비율 | 0–1 | 셀 i = 1 if 어떤 공간(면적 ≥ `p.open_space.min_area_m2`)까지 d ≤ 분×60×속도. 권역 = Σ 야간인구·값 / Σ 야간인구 (인구 0이면 null) | + 인구 | 크기 무시(버퍼 방식의 한계, SPEC 2.3) |
| `os_greenness` | 권역 안 조건 없는 열린 공간의 식생 비율 | 0–1 | Σ(클래스 1 픽셀 중 NDVI ≥ `p.greenness.ndvi_threshold`) / Σ(클래스 1 픽셀). `with_pops`면 POPS(클래스 6) 포함 | Sentinel-2 NDVI 10 m | 공간 정의 `green_only`를 따로 걸러내지 않음(정의상 자명해지므로). 수관 아래 포장면 구분 못 함 |

공간 정의(`p.open_space`): `green_only` = access free · kind ∈ `green_kinds` · 공간 녹지비율 ≥ `green_only_min_green_ratio`. `with_plaza_playground` = access free 전부 + 학교 운동장(conditional). `with_pops` = 위 + POPS. 공간 녹지비율 = 공간 안 NDVI 식생 픽셀 비율.

## 결 (공공-사적 혼재)

지상층 래스터 `p.raster.resolution_m`(5 m). 클래스: 1 조건 없는 열린 공간, 2 차로, 3 사적, 4 보도, 5 조건부 열린 공간, 6 POPS. **공공 P = {1,4}** (`with_pops`면 +6), **사적 Q = {3,5,6}** (`with_pops`면 {3,5}), 차량 V = {2}는 따로.

| ID | 정의 | 단위 | 계산 | 알려진 한계 |
| --- | --- | --- | --- | --- |
| `nolli_ratio` | 공공 접근 면적 비율 (놀리 지도) | 0–1 | nP / (nP + nQ + nV), 5 m | 지상층만. 건물 내부 공공 공간(로비, 역) 없음 |
| `edge_density` | 공공-사적 경계 밀도 | m/ha | (4-이웃 P–Q 쌍 수 × 5 m) / ((nP+nQ+nV) × 25 m² / 10⁴) | 래스터 계단 효과로 대각선 경계가 길게 잡힘 |
| `interspersion` | 혼재도 | 무차원 | 4-이웃 쌍 중 P–Q 비율 ÷ 무작위 기대값 2p(1−p), p = nP/(nP+nQ). 1 = 무작위로 섞임, 0 = 완전히 분리, >1 = 무작위보다 촘촘히 교차. 5 m | FRAGSTATS IJI는 3개 이상 클래스용이라 2-클래스 정규화 혼합 비율로 대체(경관생태학 PLADJ·aggregation index 계열). 해상도에 강하게 좌우 → `grain_multiscale` |
| `grain_multiscale` | 다중 스케일 결 | 벡터 | `interspersion`을 `p.raster.multiscale_m`(5·10·20·40 m)에서. 저해상도 = f×f 블록 최빈값(동점이면 왼쪽 위 픽셀) | 최빈값 재표본은 좁은 보도(2–5 m)를 큰 해상도에서 지운다 — 의도된 "결의 크기" 효과 |
| `largest_public_patch` | 최대 공공 패치 (H0 쪽 지표) | m² | 열린 공간(클래스 1, `with_pops`면 +6, **보도 제외**)의 4-연결 패치 중 권역 셀에 닿는 가장 큰 패치의 **전체** 면적 | 가로가 패치를 끊는다(4-연결). 그린웨이로 이어진 공원은 하나로 셈 |

## 가로

| ID | 정의 | 단위 | 계산 | 알려진 한계 |
| --- | --- | --- | --- | --- |
| `sidewalk_width` | 보도 폭 (근사) | m (화면 ft) | Σ 보도 면적 / (Σ 가로 중심선 길이 × `p.streets.sides`) | **유효폭 아님**: 가로시설·가로수·카페 좌석을 뺄 데이터 없음. 보도 없는 쪽도 2면으로 나눔 |
| `sidewalk_adequacy` | 보도 적정성 | m / (인/ha) | `sidewalk_width` / ((야간 인구 + 일자리) / 땅 면적 ha) | 보행량 대신 **대리값**(인구 밀도). 통과 보행·관광 보행 없음 |
| `lane_share` | 차로 비율 | 0–1 | Σ 차로 면적 / (Σ 차로 + Σ 보도 면적) | 주차 차로·자전거 차로·버스 차로 구분 없음 (노면 전체) |
| `enclosure` | 위요감 (가로 폭 : 건물 높이) | 무차원 | ((Σ 차로 + Σ 보도) / Σ 중심선 길이) / (가로변 건물 높이의 면적 가중 평균). 가로변 = 중심선에서 `p.streets.building_search_m` 안. **값이 클수록 트여 있음** | 높이 없는 건물 제외. 공원 변 가로는 건물이 없어 분모가 작아짐 |
| `frontage_permeability` | 전면 투과성 | 출입구/100 m | **1차 버전 비워둠** — 정리된 공개 데이터 없음. 설계안 `frontage` 레이어와 CSV 라벨로만 입력 가능 | — |

## 근접성 (별도 축 — 가까울수록 좋다고 가정하지 않음)

| ID | 정의 | 단위 | 계산 | 알려진 한계 |
| --- | --- | --- | --- | --- |
| `amenity_daily` | 일상 필수 시설 근접성 | 분 | 셀마다 범주(`p.amenity.daily_categories`: 식료품, 약국)별 가장 가까운 곳까지 보행 분 → 두 범주 중 **먼 쪽**(둘 다 갖추는 데 드는 시간), `daily_cutoff_minutes`에서 자름. 권역 = 셀 평균 | OSM POI 완결성에 좌우 |
| `amenity_diversity` | 편의시설 다양성 | nat | 권역 안 POI 범주(`shop=*`, 소비형 `amenity=*`)별 개수의 섀넌 엔트로피 −Σ p ln p | 체인 여부·가격대 구분 없음 |

## 맥락 (비교 집단을 정하는 데만 — 평가 지표로 내세우지 않음)

| ID | 계산 |
| --- | --- |
| `ctx_density` | Σ 야간 인구 / Σ 땅 면적 (인/ha) |
| `ctx_landuse_mix` | 필지 용도 범주별 대지면적 합의 섀넌 엔트로피 / ln(범주 수). NYC = PLUTO landuse 11범주, osm_global = OSM landuse |
| `ctx_daytime_ratio` | Σ 일자리 / Σ 야간 인구 |
| `ctx_income` | 셀 중심이 든 트랙트의 ACS 중위 가구소득, 야간 인구 가중 평균 (osm_global: 데이터 없음) |

## 외부 라벨 (평가 모드)

| ID | 계산 | 한계 |
| --- | --- | --- |
| `places_obesity`, `places_depression`, `places_lpa`, `places_mhlth`, `places_bphigh`, `places_diabetes`, `places_phlth` | CDC PLACES 2025 트랙트 조유병률(%) → 셀(중심이 든 트랙트) → 권역은 땅 면적 가중 평균 | 모델 추정치, 인구 특성에 크게 좌우. 횡단 비교 = 증거 강도 최하 |
| CSV 라벨 | 사용자가 불러온 열 그대로 (표본 ID 또는 좌표로 연결) | 관찰·설문 프로토콜은 사용자 책임 |

## 시나리오 실험실 대리 지표 (M3, 결과 보기 전 고정)

격자 도시에서만 계산. 인구 가중 = 셀 인구로 가중. 렌즈(α, β, 감쇠)는 스윕 값.

| ID | 혜택 경로 | 계산 |
| --- | --- | --- |
| `proxy_activity` | 신체 활동 | 면적 ≥ `p.scenarios.proxies.activity_min_area_m2` 인 공간만으로 계산한 `os_gravity`(혼잡 켜면 `os_g2sfca`)의 인구 가중 평균 |
| `proxy_restoration` | 정신적 회복 | 면적 ≥ `restoration_min_area_m2` 인 공간까지 보행 `restoration_reach_m` 안에 사는 인구 비율 |
| `proxy_social` | 사회적 연결 | 보행 `social_reach_m`(5분) 안에 닿는 서로 다른 공간 수의 인구 가중 평균 |
| `proxy_environment` | 환경 서비스 | 공간 경계에서 `environment_edge_m` 이상 떨어진 핵심 면적 합 (ha) |
| `proxy_equity` | 공정성 | 셀 `os_gravity`(혼잡 켜면 `os_g2sfca`)의 인구 가중 10분위수(하위 10%가 받는 값) |

대리 지표는 정의에 따라 결론이 거의 정해지는 것이 있다(예: `proxy_environment`는 연속 면적에 유리, `proxy_social`은 개수에 유리). REPORT에서 이 점을 구분해 적는다.
