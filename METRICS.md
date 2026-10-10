# METRICS — 지표 정의

화면에 보이는 모든 숫자는 이 문서의 ID로 추적된다 (원칙 1.2-5). 파라미터 값은 `config/params.yaml`에서만 읽는다.
M2에서 각 항목을 ID · 정의 · 단위 · 계산식 · 사용 데이터 · 알려진 한계로 채운다.

## 목차
- 공공공간: `os_gravity`, `os_g2sfca`, `os_cover_5`, `os_cover_10`, `os_greenness`
- 결: `nolli_ratio`, `edge_density`, `interspersion`, `grain_multiscale`, `largest_public_patch`
- 가로: `sidewalk_width`, `sidewalk_adequacy`, `lane_share`, `enclosure`, `frontage_permeability`
- 근접성 (별도 축): `amenity_daily`, `amenity_diversity`
- 맥락 (비교 집단용, 평가 아님): `ctx_density`, `ctx_landuse_mix`, `ctx_daytime_ratio`, `ctx_income`
- 시나리오 실험실 대리 지표: `proxy_activity`, `proxy_restoration`, `proxy_social`, `proxy_environment`, `proxy_equity`
- 외부 라벨: `places_*`, CSV 라벨
