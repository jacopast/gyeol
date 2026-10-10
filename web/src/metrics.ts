// 화면에 보이는 지표 — ID는 METRICS.md와 같다 (원칙 1.2-5: 숨은 가중치 금지)
import { M_PER_FT } from './units';

export interface MetricDef {
  id: string;
  label: string;
  group: '공공공간' | '결' | '가로' | '근접성' | '맥락' | '라벨';
  unit: string;
  fmt: (v: number, u: Units) => string;
  map?: boolean; // 단계 구분도로 그릴 수 있는가
}

export interface Units { width: 'ft' | 'm' }

const n = (d: number) => (v: number) => v.toLocaleString('ko-KR', { maximumFractionDigits: d, minimumFractionDigits: d });
const big = (v: number) => (Math.abs(v) >= 1e6 ? `${(v / 1e6).toFixed(2)}M` : Math.abs(v) >= 1e3 ? `${(v / 1e3).toFixed(1)}k` : v.toFixed(1));
const pct = (v: number) => `${(v * 100).toFixed(0)}%`;
const width = (v: number, u: Units) => (u.width === 'ft' ? `${(v / M_PER_FT).toFixed(1)} ft` : `${v.toFixed(1)} m`);
const ha = (v: number) => `${(v / 1e4).toFixed(2)} ha`;

export const METRICS: MetricDef[] = [
  { id: 'os_gravity', label: '중력 접근성', group: '공공공간', unit: 'm^2α', fmt: big, map: true },
  { id: 'os_g2sfca_night', label: '1인당 공공공간 (야간 인구)', group: '공공공간', unit: 'm²/인', fmt: n(1), map: true },
  { id: 'os_g2sfca_day', label: '1인당 공공공간 (일자리)', group: '공공공간', unit: 'm²/인', fmt: n(1), map: true },
  { id: 'os_cover_5', label: '5분 안 공공공간 인구 비율', group: '공공공간', unit: '', fmt: pct, map: true },
  { id: 'os_cover_10', label: '10분 안 공공공간 인구 비율', group: '공공공간', unit: '', fmt: pct, map: true },
  { id: 'os_greenness', label: '공공공간 식생 비율', group: '공공공간', unit: '', fmt: pct, map: true },
  { id: 'nolli_ratio', label: '공공 접근 면적 비율', group: '결', unit: '', fmt: pct, map: true },
  { id: 'edge_density', label: '공공-사적 경계 밀도', group: '결', unit: 'm/ha', fmt: n(0), map: true },
  { id: 'interspersion', label: '혼재도 (5 m)', group: '결', unit: '', fmt: n(2), map: true },
  { id: 'largest_public_patch', label: '닿는 최대 공공 패치', group: '결', unit: 'ha', fmt: ha, map: true },
  { id: 'sidewalk_width', label: '보도 폭 (근사)', group: '가로', unit: '', fmt: width, map: true },
  { id: 'sidewalk_adequacy', label: '보도 적정성 (대리값)', group: '가로', unit: 'm/(인/ha)', fmt: n(3), map: true },
  { id: 'lane_share', label: '차로 비율', group: '가로', unit: '', fmt: pct, map: true },
  { id: 'enclosure', label: '가로 폭 : 건물 높이', group: '가로', unit: '', fmt: n(2), map: true },
  { id: 'frontage_permeability', label: '전면 투과성', group: '가로', unit: '', fmt: n(1) },
  { id: 'amenity_daily', label: '식료품·약국 둘 다 (먼 쪽)', group: '근접성', unit: '분', fmt: (v) => `${v.toFixed(1)}분`, map: true },
  { id: 'amenity_diversity', label: '편의시설 다양성', group: '근접성', unit: 'nat', fmt: n(2), map: true },
  { id: 'ctx_density', label: '인구 밀도', group: '맥락', unit: '인/ha', fmt: n(0), map: true },
  { id: 'ctx_landuse_mix', label: '용도 혼합', group: '맥락', unit: '', fmt: n(2), map: true },
  { id: 'ctx_daytime_ratio', label: '일자리 / 야간 인구', group: '맥락', unit: '', fmt: n(2), map: true },
  { id: 'ctx_income', label: '중위 가구소득', group: '맥락', unit: '', fmt: (v) => `${(v / 1000).toFixed(0)}k`, map: true },
];

export const LABELS: Record<string, string> = {
  places_obesity: '비만', places_depression: '우울', places_lpa: '여가 신체활동 없음', places_mhlth: '정신건강 나쁜 날 14일+',
  places_bphigh: '고혈압', places_diabetes: '당뇨', places_phlth: '신체건강 나쁜 날 14일+',
};

export function labelDefs(cols: string[]): MetricDef[] {
  return cols.map((c) => ({ id: c, label: `${LABELS[c] ?? c} (PLACES)`, group: '라벨', unit: '%', fmt: n(1), map: true }));
}

export function fmtValue(def: MetricDef, v: unknown, u: Units): string {
  if (v === null || v === undefined || (typeof v === 'number' && !Number.isFinite(v))) return '데이터 없음';
  if (Array.isArray(v)) return v.map((x) => (x === null ? '–' : (x as number).toFixed(2))).join(' / ');
  return def.fmt(v as number, u);
}
