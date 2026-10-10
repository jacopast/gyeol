# PLAN — 마일스톤별 작업 계획

SPEC 10.1의 마일스톤을 순서대로. 각 항목은 수용 기준을 모두 통과해야 끝. 상태(2026-10-10 기준 전부 완료, REPORT.md): `[ ]` 예정 · `[~]` 진행 · `[x]` 완료 · `[-]` 단순화하여 완료(DECISIONS.md 참고).

## 구조 (전 세계 확장 전제)

```
config/params.yaml            방법 파라미터 (모든 지역 공통 — 비교가 성립하려면 같아야 함)
config/regions/<id>.yaml      지역: 경계, 어댑터, 좌표계, 표시 단위
pipeline/gyeol/
  config.py                   파라미터 로드 + params_hash
  adapters/base.py            레이어 계약(스키마): open_space, sidewalk, roadway, building, population_night/day, poi, labels …
  adapters/osm_global.py      전 세계 기본 어댑터 (OSM + 전지구 인구) — 어떤 도시든 이걸로 시작
  adapters/nyc.py             뉴욕 공식 데이터로 레이어 덮어쓰기 (없는 레이어는 osm_global로)
  network.py                  보행망 (OSMnx walk) → CSR 그래프, 다익스트라
  grid.py                     H3 격자, 셀↔노드 매핑
  raster.py                   지상층 공공/차량/사적 분류 래스터
  metrics/access.py           os_gravity, os_g2sfca, os_cover_*, os_greenness
  metrics/grain.py            nolli_ratio, edge_density, interspersion, grain_multiscale, largest_public_patch
  metrics/streets.py          sidewalk_width, sidewalk_adequacy, lane_share, enclosure, frontage_permeability(빈칸)
  metrics/amenity.py          amenity_daily, amenity_diversity
  metrics/context.py          ctx_*
  sample.py                   권역(walkshed) + 셀 통계 집계 = 표본 (웹 워커와 같은 알고리즘)
  scenarios.py                추상 격자 도시 실험실
  personality.py              표준화 → PCA → k-평균 (성격 모드)
  labels.py                   CDC PLACES 등 외부 라벨
  export.py                   웹 산출물 (regions/<id>/…)
web/                          TypeScript + Vite + MapLibre GL, 계산은 웹 워커
web/public/data/regions.json  지역 목록 → 웹은 지역을 고를 수 있다
```

## M0 리포 골격
- [x] SPEC.md, CLAUDE.md, PLAN.md, DECISIONS.md, HYPOTHESES.md, METRICS.md(목차), config/params.yaml
- [x] uv(Python 3.12) + ruff + pytest, web npm 골격 + tsc + vitest, Makefile(`lint`, `test`)
- [x] GitHub `jacopast/gyeol`(public)

## M1 [x] 데이터 파이프라인
- 어댑터 계약 + nyc 어댑터: NYC Open Data(Socrata) 레이어를 맨해튼+버퍼 bbox로 받아 자르기
- 인구: 2020 TIGER tabblock20(POP20), LODES8 WAC 2023, ACS 5년 B19013(테이블 파일)
- 보행망: OSMnx walk, 출입구(경계 샘플점 → 보행 노드)
- 녹지성: Sentinel-2 L2A NDVI(Earth Search STAC, 키 없음), 실패 시 OSM 녹지 태그
- H3 res 10 격자, 5m 지상층 분류 래스터
- `make data` 한 명령, `data/REPORT_data.md`(레이어별 피처 수·면적 합), 레이어 PNG

## M2 [x] 지표 엔진
- 9.4 지표 전부(투과성 제외). 셀 단위 "가산 통계"로 저장 → 어떤 권역이든 합산으로 지표 재구성
- METRICS.md 완성, 합성 데이터 단위 테스트

## M3 [x] 시나리오 실험실
- 격자 도시, 집중/중간/분산/혼합 × α·β·감쇠·혼잡·기회비용 스윕
- 뒤집히는 경계 표 + 그림 → `reports/scenarios.md`, 성질 테스트

## M4 [x] 웹 골격 + 룩앤필
- 토큰, 라이트/다크, OpenFreeMap 무채색 베이스맵, 격자 단계 구분도, 지표 텍스트 목록

## M5 [x] 표본 + 라이브러리 + 비교
- 클릭 → 워커 다익스트라 → 5·10분 권역 → 지표 표. 라이브러리(localStorage + JSON 입출력). 스트립 차트 비교, 동류 집단 필터
- 교차 검증: Python 기준 구현과 20지점 2% 이내 (vitest가 같은 산출물로 검사)

## M6 [x] 설계안 업로드
- templates/design_template.geojson + README, 검증 오류 한 줄씩, 대상지+버퍼 재계산, 변화표

## M7 [x] 성격 모드
- 층화 추출 표본 36개 데모 라이브러리, 표준화→PCA→k(실루엣), 유형 A·B·C 프로필, 설계안-유형 거리

## M8 [x] 외부 라벨
- PLACES 트랙트 → 셀 → 권역 면적 가중, CSV 불러오기(표본 ID 또는 좌표)

## M9 [x] 마무리
- README, 정적 빌드, GitHub Pages 워크플로, REPORT.md
