# DECISIONS — 결정 기록

한 줄 = 한 결정. `[M#] 결정 — 근거`. 사용자 결정은 (사용자)로 표시.

## 2026-10-10 시작 시점 (사용자에게 받은 답)
- [M0] (사용자) 독립 리포 `jacopast/gyeol`, **public**, GitHub Pages 배포 — SPEC 10.3의 "원격 없으면 만들지 않음"을 사용자가 직접 해제.
- [M0] (사용자) 데이터는 **가볍게** — 원본 다운로드 합계 1GB 이하 목표. 무거운 레이어는 대체 출처로 단순화하고 여기에 기록.
- [M0] (사용자) 맨해튼에서 시작하되 **전 세계 도시로 확장 가능한 구조**: 방법 파라미터(`config/params.yaml`)와 지역 설정(`config/regions/<id>.yaml`)을 분리, 데이터는 어댑터(`osm_global` 기본 + `nyc` 덮어쓰기), 웹 산출물은 `regions/<id>/`.
- [M0] 로컬 위치 `~/AG/git/gyeol` — 사용자의 코드 저장 규칙(코드는 `~/AG/git/<project>`).

## M0
- [M0] Python 3.12 고정(uv) — 시스템 3.14에선 지리 패키지 휠이 불안정할 수 있음.
- [M0] 방법 파라미터는 지역과 무관하게 하나 — 도시 간 비교가 같은 정의 위에서만 성립(유니버설 프로토콜, SPEC 6.3).
- [M0] 미터 좌표계는 지역 설정에 없으면 중심점 UTM 자동 — 전 세계 어디서나 미터 단위 계산.

## 데이터 출처 (M1에서 확정, 버전은 data/REPORT_data.md)
- [M1] Census API가 2026년 현재 키를 요구 → 키 없는 경로로 대체: 인구 = TIGER 2020 tabblock20의 POP20, 소득 = ACS 5년 테이블 파일(acsdt5y2024-b19013.dat). 키를 받으면 쓸 수 있게 하지는 않음(불필요).
- [M1] LODES8 최신 연도 2023 사용 (2024는 아직 없음).
- [M1] PLACES 2025 release (yjkw-uj5s) 사용.
- [M1] 공식 데이터에 없는 공공공간(주립 Hudson River Park, Battery Park City, Governors Island 등)은 OSM(leisure=park/garden/playground…, place=square, highway=pedestrian 면)으로 보충. 겹침은 출처 순서(NYC 공식 → OSM)로 한 번만 센다: 이미 받은 공간과 50% 이상 겹치면 버리고, 덜 겹치면 겹친 부분을 잘라 낸다.
- [M1] 공간 접근 조건: NYC Parks typecategory → kind/access 표(`adapters/nyc.py`). 커뮤니티 가든·역사가옥·골프장 = conditional, 미개발·운영부지·실내시설 = restricted. OSM 정원은 명시적 access=yes 없으면 conditional (사유 중정이 많음). 학교 운동장(Schoolyards to Playgrounds) = conditional.
- [M1] 공간 정의: green_only = free·녹지 종류·녹지비율≥0.5, with_plaza_playground = free 전부 + 학교 운동장, with_pops = 위 + POPS. conditional 정원 등은 어떤 정의에도 넣지 않음. Open Streets는 레이어로만.
- [M1] POPS는 위치 점 + 요구 면적 텍스트(sf 합계)뿐 → 같은 면적의 원으로 근사. 실내형(arcade 등) 면적도 합산됨 — 한계.
- [M1] 녹지성: NYC LiDAR 토지피복(수 GB) 대신 Sentinel-2 L2A NDVI(10m, Earth Search STAC, 키 없음, 전 세계 공통). 2025년 6~8월 구름 10% 미만 장면 중 가장 맑은 것부터 채움. 식생 = NDVI ≥ 0.3.
- [M1] 출입구: 데이터가 없으므로 경계를 50m 간격으로 샘플해 40m 안의 보행 노드. 못 찾으면 대표점 최근접 노드(보고서에 개수).
- [M1] 보행망: OSMnx walk, retain_all=True (보행로가 따로 노는 섬도 유지). 셀 중심에서 250m 안에 보행 노드가 없으면 그 셀은 보행망 밖(데이터 없음). 셀→노드 거리(스냅)는 거리에 더하지 않음 (맨해튼 중앙값 35m).
- [M1] 지상층 래스터 5m, 그리는 순서 = 사적(땅 전체) → 차로 → 보도 → 조건부 공간 → POPS → 조건 없는 공간. 공원 안 건물(박물관 등)도 공원 쪽으로 분류됨 — 한계.
- [M1] 연구 범위 = 맨해튼 + 1km 버퍼. 버퍼가 닿는 뉴저지는 NYC 데이터가 없어 땅·인구에서 빠짐(허드슨강 폭이 대부분 1km 이상이라 영향 작음). OSM 공간·보행망은 뉴저지도 들어오지만 다리가 없어 맨해튼 셀에서 닿지 않음.
- [M1] 인구 = 2020 블록 POP20을 땅 면적 비율로 셀에 배분(블록의 물 부분은 분모에서 뺌). 주간 = LODES WAC 일자리 수(C000)만 — 방문객·학생은 없음.
- [M1] 소득 = ACS 5년 2024 B19013 트랙트 중위 가구소득, 셀 중심이 든 트랙트 값. 라벨(PLACES)도 같은 방식.
- [M1] `data/processed/`(약 70MB)도 git에서 제외 — `make data`로 재현. 웹 산출물(`web/public/data/`, 약 7MB)만 커밋.
