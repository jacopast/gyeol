// 스트립 차트 (SPEC 9.2): 라이브러리 표본 = 점, 현재 대상 = 선. 레이더 차트 금지
import { fmtValue, type MetricDef, type Units } from './metrics';

export function quantileBreaks(vals: number[], k: number): number[] {
  const v = [...vals].sort((a, b) => a - b);
  if (!v.length) return [];
  const out: number[] = [];
  for (let i = 1; i < k; i++) out.push(v[Math.min(v.length - 1, Math.floor((i * v.length) / k))]);
  return out;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

export function stripChart(def: MetricDef, pts: { v: number | null; name: string }[], target: number | null, u: Units, dashed: boolean): string {
  const vals = pts.map((p) => p.v).filter((x): x is number => typeof x === 'number' && Number.isFinite(x));
  const all = target !== null && Number.isFinite(target) ? [...vals, target] : vals;
  const missing = pts.length - vals.length;
  if (!all.length) {
    return `<div class="strip"><div class="lbl"><span>${esc(def.label)}</span><span class="muted">데이터 없음</span></div></div>`;
  }
  const lo = Math.min(...all), hi = Math.max(...all);
  // Equal values have no observed spread; do not invent endpoints such as 105% coverage.
  const x = (v: number) => lo === hi ? 50 : 4 + ((v - lo) / (hi - lo)) * 92;
  const dots = pts.filter((p) => typeof p.v === 'number' && Number.isFinite(p.v))
    .map((p) => `<circle cx="${x(p.v as number)}%" cy="13" r="3.2" fill="var(--fg)" fill-opacity="0.45"><title>${esc(p.name)}: ${fmtValue(def, p.v, u)}</title></circle>`).join('');
  const line = target !== null && Number.isFinite(target)
    ? `<line x1="${x(target)}%" x2="${x(target)}%" y1="1" y2="25" stroke="var(--fg)" stroke-width="2.5" ${dashed ? 'stroke-dasharray="3 2"' : ''}><title>${fmtValue(def, target, u)}</title></line>` : '';
  // 현재 대상의 위치: 표본 중 몇 개가 더 작은가 (순위만, 평가 아님)
  const rank = target !== null && vals.length ? ` · 표본 ${vals.length}개 중 ${vals.filter((v) => v < target).length}개가 더 작음` : '';
  return `<div class="strip"><div class="lbl"><span>${esc(def.label)}</span><span class="muted">${target !== null ? fmtValue(def, target, u) : ''}${rank}</span></div>
    <svg role="img" aria-label="${esc(def.label)}"><line x1="4%" x2="96%" y1="13" y2="13" stroke="var(--line)" stroke-width="1"/>${dots}${line}</svg>
    <div class="lbl small"><span>${fmtValue(def, lo, u)}</span>${missing ? `<span>데이터 없음 ${missing}</span>` : ''}<span>${fmtValue(def, hi, u)}</span></div></div>`;
}
