import type { Lens } from './engine';

/** A hash identifies the precomputed run, not the selected lens or walkshed. */
export interface ComparisonBasis {
  region: string;
  params_hash: string;
  walk_minutes: number;
  lens: Lens;
}

export function sameLens(a: Lens | undefined, b: Lens | undefined): boolean {
  return !!a && !!b && a.definition === b.definition && a.decay === b.decay
    && a.alpha === b.alpha && a.beta === b.beta;
}

export function comparisonMismatch(sample: Partial<ComparisonBasis>, basis: ComparisonBasis): string | null {
  if (sample.region !== basis.region) return '지역이 다름';
  if (sample.params_hash !== basis.params_hash) return '계산 버전이 다르거나 없음';
  if (sample.walk_minutes !== basis.walk_minutes) return '보행 시간이 다르거나 없음';
  if (!sameLens(sample.lens, basis.lens)) return '공간 정의·감쇠·α·β가 다르거나 없음';
  return null;
}
