// 설계안 패널 (M6)
import type { Metrics } from './engine';

export interface DesignState { result: { before: Metrics; after: Metrics; geo: any; bounds: number[] } | null; errors: string[]; name: string }

export function renderDesign(_s: { design: DesignState }): string {
  return '';
}
