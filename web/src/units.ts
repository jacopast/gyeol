// 단위 변환. 내부는 미터법, 화면은 거리=보행 분, 폭=ft 기본 + m 토글 (SPEC 9.1)
export const M_PER_FT = 0.3048;

export function metersToMinutes(m: number, speedMps: number): number {
  return m / speedMps / 60;
}

export function formatWidth(m: number | null, unit: 'ft' | 'm'): string {
  if (m === null || !Number.isFinite(m)) return '데이터 없음';
  return unit === 'ft' ? `${(m / M_PER_FT).toFixed(1)} ft` : `${m.toFixed(1)} m`;
}
