# 결 (Gyeol)

공원 접근성에서 도시 공공공간의 결까지 — **같은 총 면적의 공공공간을 크게 모을지 작게 흩을지, 어떤 조건에서 어느 쪽의 값이 큰지**를 지도 위에서 보여 주는 도구. 결론은 내리지 않는다. 단일 종합 점수도 없다.

- 웹: https://jacopast.github.io/gyeol/ (GitHub Pages)
- 명세 [SPEC.md](SPEC.md) · 계획 [PLAN.md](PLAN.md) · 결정 기록 [DECISIONS.md](DECISIONS.md) · 가설과 반증 조건 [HYPOTHESES.md](HYPOTHESES.md) · 지표 정의 [METRICS.md](METRICS.md) · 결과 보고 [REPORT.md](REPORT.md)
- 시나리오 실험실 결과 [reports/scenarios.md](reports/scenarios.md) · 데이터 보고서 [data/REPORT_data.md](data/REPORT_data.md)

## 처음 쓰는 사람을 위한 안내

패널 맨 위의 세 화면 중 하나를 고른다. 주소 끝에 `#question`, `#city`, `#design`을 붙이면 그 화면으로 바로 열린다.

| 화면 | 이런 질문에 | 해 볼 것 |
| --- | --- | --- |
| **질문** `#question` | 같은 면적의 공원을 한 곳에 모을까, 여러 곳에 흩을까? | ①·② 두 질문에 답을 바꿔 가며 네 배치 중 어느 쪽 값이 커지는지 본다. '지금까지 알게 된 것' 표가 결론이 뒤집히는 지점이다 |
| **도시 읽기** `#city` | 실제 도시에서 공원은 어디 있고, 여기서 걸어서 얼마나 걸리나? | 지도를 누른다 → 가장 가까운 공원 / 1 ha 이상 / 10 ha 이상 공원까지 걸어서 몇 분인지 문장으로 나온다. 눈여겨볼 곳은 '라이브러리에 추가' |
| **설계 검토** `#design` | 이 설계안은 기존보다 무엇이 달라지고, 다른 동네들 사이에서 어디쯤인가? | '예제 설계안'을 눌러 본다 → 기존·설계안 표. 아래 '비교'에서 라이브러리 동네들(점)과 설계안(선)을 지표별로 본다 |

지도 색: 초록 = 누구나 들어갈 수 있는 공원·광장, 옅은 초록 = 시간제·사유 공개공지, 옅은 띠 = 보도, 바탕 육각형이 진할수록 공원까지 멀다.

이 도구는 어느 배치가 좋다고 말하지 않는다. 조건(①·②에 대한 판단)에 따라 결과가 어떻게 뒤집히는지를 보여 주고, 판단은 쓰는 사람에게 남긴다.

## 무엇을 하나

1. **지도** — 격자(H3 해상도 10) 단위 지표를 단계 구분도로 본다. 지표는 텍스트 목록에서 고른다.
2. **표본** — 지도를 누르면 그 자리에서 걸어서 5·10분 보행망 권역을 계산하고(브라우저 웹 워커, 다익스트라) 지표 표를 보여 준다.
3. **라이브러리** — 표본을 모으고(브라우저 저장소), JSON으로 내보내고 불러온다. 맥락별로 층화 추출한 시연 표본 36개가 들어 있다.
4. **비교** — 고른 표본들(점)과 현재 대상(선, 설계안이면 점선)을 지표별 스트립 차트로. 맥락 변수로 동류 집단을 거른다.
5. **설계안** — GeoJSON 하나를 올리면 검증하고, 대상지 안을 교체해 대상지·버퍼를 다시 계산하고, 전후 변화를 표로 보여 준다. [templates/](templates/)
6. **성격 모드** — 지표 묶음을 지문으로 보고 유형 A·B·C…로 묶는다. 현재 대상이 각 유형에서 얼마나 떨어져 있는지 본다.
7. **외부 라벨** — CDC PLACES 건강 지표(자동), 관찰·설문 CSV와 쌍대 비교 결과 불러오기. [docs/labels.md](docs/labels.md)
8. **시나리오 실험실** — 추상 격자 도시에서 집중·중간·분산·혼합 배치를 α·β·감쇠·혼잡·기회비용·공원 장벽 조합 320가지로 돌려 **결론이 뒤집히는 경계**를 낸다.

화면 아래의 렌즈(공간 정의, 감쇠, α, β)를 바꾸면 미리 계산한 다른 조합을 보여 주고 "임시 실행"으로 표시한다.

## 실행

필요: [uv](https://docs.astral.sh/uv/) (Python 3.12을 알아서 받음), Node 20.19+ / npm.

```bash
make setup                  # Python·웹 의존성
make data REGION=manhattan  # 다운로드 → 정제 → 보행망 → 격자 → 래스터 → 지표 → 웹 산출물 (처음 약 5분)
make xval                   # 교차 검증 기준값 (Python)
make demo                   # 시연 라이브러리 + 성격 모드 군집
make scenarios              # 시나리오 실험실 → reports/scenarios.md
make test                   # pytest + vitest (교차 검증 포함)
make web                    # 개발 서버 http://localhost:5173
make build                  # 정적 빌드 → web/dist (base /gyeol/)
```

원본 데이터는 `data/raw/`(git 제외), 가공본은 `data/processed/`(git 제외, `make data`로 재현), 앱이 읽는 결과물만 `web/public/data/`에 커밋된다.

## 새 도시 추가하기

방법 파라미터(`config/params.yaml`)는 모든 도시에 같고, 도시마다 `config/regions/<id>.yaml` 하나만 쓴다.

```yaml
id: seongdong
name: 서울 성동구
adapter: osm_global          # 전 세계 공통 (OSM + GHSL 인구 + Sentinel-2)
target:
  osm_query: "Seongdong-gu, Seoul, South Korea"
units_display: metric
osm_global:
  population: ghsl
```

```bash
make data REGION=seongdong
```

`osm_global`만으로 보행망·공공공간·건물·POI·녹지성·야간 인구까지 나온다. 일자리·소득·건강 라벨은 없으면 "데이터 없음"으로 남는다. 공식 데이터가 있는 도시는 `pipeline/gyeol/adapters/`에 `nyc.py` 같은 어댑터를 만들어 레이어를 덮어쓰면 된다(레이어 계약은 `adapters/base.py`). 웹은 `web/public/data/regions.json`에 등록된 지역을 고를 수 있게 보여 준다(`?r=<id>`).

## 데이터 출처 (1차, 맨해튼)

| 레이어 | 출처 | 버전·날짜 |
| --- | --- | --- |
| 보행망, POI, 보충 공공공간 | OpenStreetMap (OSMnx / Overpass) | 2026-10-10 받음 |
| 공원 | NYC Open Data `enfh-gkve` Parks Properties | 2026-09-16 갱신본 |
| 보행 광장 | NYC DOT `k5k6-6jex` | 2026-10-01 |
| POPS | NYC `rvih-nhyn` | 2025-10-14 |
| 수변 공공 접근 | NYC `388s-pnvc` WPAA | 2023-11-01 |
| 학교 운동장 개방 | NYC `bbtf-6p3c` Schoolyard to Playgrounds | 2026-09-15 |
| Open Streets | NYC DOT `uiay-nctu` | 2026-10-01 |
| 보도·차로 면 | NYC Planimetric `52n9-sdep`, `i36f-5ih7` | 2024-04-24 |
| 가로 중심선 | NYC `inkn-q76z` Centerline (CSCL) | 2026-10-10 |
| 건물 외곽·높이 | NYC `5zhs-2jue` BUILDING | 2026-10-05 |
| 필지 용도 | NYC `64uk-42ks` PLUTO | 2026-08-24 |
| 보로·트랙트 경계 | NYC `gthc-hcne`, `63ge-mke6` | 2026-05-26 |
| 야간 인구 | US Census TIGER/Line 2020 TABBLOCK20 (POP20, HOUSING20) | 2020 센서스 |
| 주간 인구 | LEHD LODES8 WAC S000 JT00 | 2023 |
| 소득 | ACS 5년 B19013 (테이블 요약 파일) | 2024 |
| 건강 라벨 | CDC PLACES `yjkw-uj5s` 트랙트 | 2025 release |
| 녹지성 | Sentinel-2 L2A (Earth Search STAC) | 2025-08-22 장면 |
| 베이스맵 | OpenFreeMap 벡터 타일 | 2026-10-04 타일셋 |
| 인구 (osm_global) | GHSL GHS-POP E2025 R2023A 100 m | — |

모든 다운로드는 스크립트로 재현되며 `data/raw/<region>/sources.json`에 받은 시각이 남는다.

## 한계 (자세한 것은 METRICS.md와 DECISIONS.md)

- **실증이 아니다.** 표본 비교와 PLACES 라벨은 동네 간 횡단 비교 = 증거 강도 최하(SPEC 6.1). 시나리오 실험실은 모델 안의 정합성 확인이다.
- 출입구는 데이터가 없어 공간 경계 샘플로 근사한다. 셀→보행 노드 스냅 거리는 더하지 않는다.
- 보도 폭은 유효폭이 아니라 보도 면적 ÷ 중심선 길이의 근사, 보도 적정성의 보행량은 인구 밀도 대리값이다.
- 녹지성은 10 m 위성 NDVI — 수관 아래 포장면을 구분하지 못한다.
- 전면 투과성은 정리된 공개 데이터가 없어 비워 두었다(설계안 `frontage`와 CSV 라벨로만 입력).
- POPS는 점 + 요구 면적 텍스트뿐이라 같은 면적의 원으로 그린다.
- 혼재도는 2-클래스 정규화 혼합 비율이다(FRAGSTATS IJI는 3개 이상 클래스용).
- 설계안 재계산은 경계를 걸친 셀을 면적 비례로 근사한다([templates/README.md](templates/README.md)).

## 배포

`main`에 `web/**`이 바뀌면 GitHub Actions(`.github/workflows/pages.yml`)가 테스트 → 빌드 → Pages 배포를 한다. 직접 하려면 `make build` 후 `web/dist`를 아무 정적 호스팅에 올리면 된다(경로 `/gyeol/` 기준, 바꾸려면 `web/vite.config.ts`의 base).

## 라이선스와 출처 표기

코드는 아직 라이선스를 정하지 않았다(사용자 결정 항목). 데이터는 각 출처의 이용 조건을 따른다 — OpenStreetMap © OpenStreetMap contributors (ODbL), NYC Open Data, US Census, CDC, Copernicus Sentinel-2, JRC GHSL.
