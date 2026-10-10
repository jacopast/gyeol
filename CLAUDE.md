# 결 (Gyeol) — 작업 지침 요약

전체 명세는 [SPEC.md](SPEC.md). 이 파일은 매 세션 자동으로 읽히는 요약이다. 앱 화면의 제목은 "결".

## 무엇
같은 총 면적의 공공공간을 크게 모을지 작게 흩을지, **어떤 조건에서** 어느 쪽이 나은지 보여주는 도구.
오프라인 Python 파이프라인(기준 구현, `pipeline/`) + 정적 웹앱(`web/`, TypeScript·Vite·MapLibre).
1차 지역은 맨해튼이지만 구조는 전 세계 도시용이다: 지역 설정은 `config/regions/<id>.yaml`,
데이터 소스는 어댑터(`osm_global` 기본, `nyc` 덮어쓰기), 웹 산출물은 `web/public/data/regions/<id>/`.

## 설계 원칙 (모든 결정의 기준, SPEC 1.2)
1. **대칭성** — 집중형/분산형(거친 결/촘촘한 결) 모두 가장 강한 형태로. 한쪽 유리한 가정엔 반대쪽 가정도.
   예: 면적 체감 α와 서비스권 규모 연동 β는 반대 방향으로 작용하므로 둘 다 민감도 대상.
2. **사전 고정** — 파라미터·공간 정의·정규화·군집 수 규칙은 결과 보기 전에 `config/params.yaml`에 커밋.
   결과 본 뒤 바꾸면 `run_id`를 올리고 이전 결과를 남긴다.
3. **반증 가능성** — 어떤 결과가 어떤 가설을 약화시키는지 `HYPOTHESES.md`에 미리.
4. **판단은 열어둔다** — 단일 종합 점수를 기본 노출하지 않는다. 조건별 결과와 거리만.
5. **숨은 가중치 금지** — 화면의 모든 숫자는 `METRICS.md` 정의로 추적 가능해야.

## 룩앤필 (SPEC 9.2)
- 최대한 미니멀. 아이콘·그림자·그라디언트·둥근 카드·배지·장식색 금지. 구분은 `--line`과 여백만.
- 폰트 Gowun Batang 하나. 본문 16px/1.5, 제목 15px 700, 보조 13px `--muted`. `word-break: keep-all`.
- Day `--bg #ecebe6 --fg #33322f --muted #8a8882 --line #b4b1a9 --cell-bg #f4f3ef`;
  Night `--bg #2c2d30 --fg #d9d7d1 --muted #8e8d89 --line #57585d --cell-bg #343538`. 시스템 설정 따름.
- 지도가 주인. 오른쪽(모바일은 아래) 얇은 패널 하나. 상단 바·사이드 메뉴·모달·토스트 없음.
- 단계 구분도는 `--fg` 단색 농도 5~7단계(무지개 금지). 표본=실선, 설계안=점선. 강조색은 하나만(DECISIONS.md).
- 숫자는 표, 분포는 스트립 차트. 레이더 차트 금지.

## 작업 규칙 (SPEC 10부)
- 질문하지 말고 원칙에 맞는 가장 단순한 선택 → `DECISIONS.md`에 한 줄.
- 데이터를 지어내지 않는다. 없는 값은 비우고 화면에 "데이터 없음".
- 결과를 보고 가설 쪽으로 파라미터를 조정하지 않는다. 문헌 수치는 하드코딩하지 않는다(파라미터 + "확인 필요").
- 유료 키·계정·결제 단계는 건너뛰고 `REPORT.md`에 남긴다.
- 파일은 프로젝트 안에서만. 임시 파일은 `tmp/`(git 제외). 원본 데이터 `data/raw/`(git 제외), 가공 `data/processed/`.
- 커밋 메시지는 마일스톤 번호로 시작 (`M2: ...`). 마일스톤마다 테스트 통과 후 커밋·푸시.
- 진행 기록은 ag-bridge `projects/gyeol/CURRENT_TASK.md`에도 append (자매 통신용 로그).

## 명령
- `make setup` — Python(uv)·웹(npm) 의존성
- `make lint` / `make test` — ruff+pytest, 웹 타입체크+vitest
- `make data REGION=manhattan` — 다운로드→정제→보행망→격자→지표→웹 산출물
- `make scenarios` — 추상 격자 도시 시나리오 실험실 → `reports/scenarios.md`
- `make web` / `make build` — 개발 서버 / 정적 빌드
