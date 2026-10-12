// 설계안 패널 (M6): 올리기 → 검증 오류 한 줄씩 → 대상지·버퍼 전후 표. 라이브러리 대비 위치는 '비교' 절에 점선으로
import { sameLens } from './comparison';
import type { DesignWalkshed } from './design';
import type { Lens, Metrics } from './engine';
import { fmtValue, METRICS, type Units } from './metrics';

export interface DesignState {
  result: { before: Metrics; after: Metrics; beforeBuffer: Metrics; afterBuffer: Metrics; siteCells: number; bufferCells: number; warnings?: string[]; geo: any; bounds: number[]; comparison: { point: [number, number]; results: Record<number, DesignWalkshed> } } | null;
  errors: string[];
  name: string;
  source?: unknown;
  lens?: Lens;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function diff(a: unknown, b: unknown): string {
  if (typeof a !== 'number' || typeof b !== 'number' || !Number.isFinite(a) || !Number.isFinite(b)) return '';
  if (a === 0) return b === 0 ? '0' : '';
  const r = (b - a) / Math.abs(a);
  if (Math.abs(r) < 0.0005) return '0';
  return `${r > 0 ? '+' : ''}${(r * 100).toFixed(1)}%`;
}

export function renderDesign(s: { design: DesignState; units: Units; meta: any; lens: Lens; addMinutes: number }): string {
  const d = s.design;
  const head = `<section><h2>설계안</h2>
    <p class="small">설계안 GeoJSON 파일 하나를 올리면 경계 안을 설계안으로 바꿔 대상지와 주변 ${s.meta?.params?.region?.boundary_buffer_m ?? ''} m를 다시 계산하고, 기존과 나란히 보여 줍니다. 처음이면 '예제 설계안'을 눌러 보세요. 지도에는 점선으로 그립니다.</p>
    <p class="small"><button class="link" id="design-upload">올리기</button> · <button class="link" id="design-example">예제 설계안</button>${d.result || d.errors.length ? ' · <button class="link" id="design-clear">지우기</button>' : ''}
    · <a href="https://github.com/jacopast/gyeol/tree/main/templates" target="_blank" rel="noopener">템플릿·작성법</a>
    <input type="file" id="design-file" accept=".geojson,.json,application/geo+json,application/json"></p>`;
  if (d.errors.length) {
    return `${head}<div class="errors"><p>${esc(d.name)} — 오류 ${d.errors.length}개</p>${d.errors.map((e) => `<p>${esc(e)}</p>`).join('')}</div></section>`;
  }
  if (!d.result) return `${head}</section>`;
  if (!sameLens(d.lens, s.lens)) return `${head}<p class="small">현재 조건으로 다시 계산 중입니다.</p></section>`;
  const r = d.result;
  const rows = (b: Metrics, a: Metrics) => METRICS.filter((m) => m.group !== '맥락').map((m) =>
    `<tr><td>${esc(m.label)}</td><td>${fmtValue(m, b[m.id], s.units)}</td><td>${fmtValue(m, a[m.id], s.units)}</td><td>${diff(b[m.id], a[m.id])}</td></tr>`).join('');
  const summaryIds = ['os_cover_5', 'nolli_ratio', 'edge_density', 'largest_public_patch', 'sidewalk_width', 'lane_share'];
  const summary = summaryIds.map((id) => {
    const m = METRICS.find((x) => x.id === id)!;
    const a = r.before[id], b = r.after[id];
    const direction = typeof a !== 'number' || typeof b !== 'number' ? '비교할 데이터 없음'
      : fmtValue(m, a, s.units) === fmtValue(m, b, s.units) ? '표시 정밀도에서 같음' : b > a ? '늘어남' : '줄어듦';
    return `<tr><td>${esc(m.label)}</td><td>${fmtValue(m, a, s.units)} → ${fmtValue(m, b, s.units)}</td><td>${direction}</td></tr>`;
  }).join('');
  const w = r.comparison.results[s.addMinutes];
  return `${head}
    <h2>이 설계에서 달라지는 것</h2>
    <p class="small">대상지 기준입니다. 공원에 닿는 정도는 접근성에서, 공공·사적 공간의 섞임은 경계에서, 큰 공간의 연속성은 패치에서 봅니다. 증가·감소 자체를 좋고 나쁨으로 판정하지 않습니다.</p>
    <table><tr><th>살펴볼 축</th><th>기존 → 설계안</th><th>변화</th></tr>${summary}</table>
    <p class="small">${esc(d.name)} · 대상지 셀 ${r.siteCells}개, 버퍼 포함 ${r.bufferCells}개</p>
    ${(r.warnings ?? []).map((w) => `<p class="small">${esc(w)}</p>`).join('')}
    <details><summary class="small">대상지 전체 지표</summary>
    <table><tr><th>지표</th><th>기존</th><th>설계안</th><th>변화</th></tr>${rows(r.before, r.after)}</table></details>
    <details><summary class="small">대상지 + 버퍼</summary>
    <table><tr><th>지표</th><th>기존</th><th>설계안</th><th>변화</th></tr>${rows(r.beforeBuffer, r.afterBuffer)}</table></details>
    <details><summary class="small">동네 비교용 ${s.addMinutes}분 보행권의 전후</summary>
    <p class="small">대상지 경계 상자의 중심에서 가장 가까운 기존 보행 노드를 출발점으로 고정합니다 (${r.comparison.point.map((x) => x.toFixed(5)).join(', ')}). 기존 ${w.beforeCells.length}셀 → 설계안 ${w.afterCells.length}셀. 새 통로·장벽에 따라 닿는 범위는 달라질 수 있습니다. 지도에서 출발점은 점, 기존 보행권은 옅은 실선, 설계 후 보행권은 점선입니다. 이 출발점이 대상지를 대표하는지 확인하세요.</p>
    <table><tr><th>지표</th><th>기존</th><th>설계안</th><th>변화</th></tr>${rows(w.before, w.after)}</table></details>
    <p class="small">변화는 처방이 아닙니다. 같은 차이를 메우는 방법은 여러 가지이고, 지표를 채운다고 성과가 오른다는 보장은 없습니다(SPEC 8.3).</p></section>`;
}
