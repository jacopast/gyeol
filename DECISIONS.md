# DECISIONS — 결정 기록

한 줄 = 한 결정. `[M#] 결정 — 근거`. 사용자 결정은 (사용자)로 표시.

## 2026-10-10 시작 시점 (사용자에게 받은 답)
- [M0] (사용자) 독립 리포 `jacopast/gyeol`, **public**, GitHub Pages 배포 — SPEC 10.3의 "원격 없으면 만들지 않음"을 사용자가 직접 해제.
- [M0] (사용자) ag-bridge에 `projects/gyeol/` 진행 로그를 두고 README 디렉터리 표와 PROJECT_CONTINUITY.md에도 등록.
- [M0] (사용자) 데이터는 **가볍게** — 원본 다운로드 합계 1GB 이하 목표. 무거운 레이어는 대체 출처로 단순화하고 여기에 기록.
- [M0] (사용자) 맨해튼에서 시작하되 **전 세계 도시로 확장 가능한 구조**: 방법 파라미터(`config/params.yaml`)와 지역 설정(`config/regions/<id>.yaml`)을 분리, 데이터는 어댑터(`osm_global` 기본 + `nyc` 덮어쓰기), 웹 산출물은 `regions/<id>/`.
- [M0] 로컬 위치 `~/AG/git/gyeol` — ag-bridge `CODE_STORAGE_POLICY.md`(코드는 `~/AG/git/<project>`).

## M0
- [M0] Python 3.12 고정(uv) — 시스템 3.14에선 지리 패키지 휠이 불안정할 수 있음.
- [M0] 방법 파라미터는 지역과 무관하게 하나 — 도시 간 비교가 같은 정의 위에서만 성립(유니버설 프로토콜, SPEC 6.3).
- [M0] 미터 좌표계는 지역 설정에 없으면 중심점 UTM 자동 — 전 세계 어디서나 미터 단위 계산.

## 데이터 출처 (M1에서 확정, 버전은 data/REPORT_data.md)
- [M1] Census API가 2026년 현재 키를 요구 → 키 없는 경로로 대체: 인구 = TIGER 2020 tabblock20의 POP20, 소득 = ACS 5년 테이블 파일(acsdt5y2024-b19013.dat). 키를 받으면 쓸 수 있게 하지는 않음(불필요).
- [M1] LODES8 최신 연도 2023 사용 (2024는 아직 없음).
- [M1] PLACES 2025 release (yjkw-uj5s) 사용.
