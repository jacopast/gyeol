// 설계안 패널 (M6): 올리기 → 검증 오류 한 줄씩 → 대상지·버퍼 전후 표. 라이브러리 대비 위치는 '비교' 절에 점선으로
import type { Metrics } from './engine';
import { fmtValue, METRICS, type Units } from './metrics';

export interface DesignState {
  result: { before: Metrics; after: Metrics; beforeBuffer: Metrics; afterBuffer: Metrics; siteCells: number; bufferCells: number; warnings?: string[]; geo: any; bounds: number[] } | null;
  errors: string[];
  name: string;
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

function diff(a: unknown, b: unknown): string {
  if (typeof a !== 'number' || typeof b !== 'number' || !Number.isFinite(a) || !Number.isFinite(b)) return '';
  if (a === 0) return b === 0 ? '0' : '';
  const r = (b - a) / Math.abs(a);
  if (Math.abs(r) < 0.0005) return '0';
  return `${r > 0 ? '+' : ''}${(r * 100).toFixed(1)}%`;
}

export function renderDesign(s: { design: DesignState; units: Units; meta: any }): string {
  const d = s.design;
  const head = `<section><h2>설계안</h2>
    <p class="small">GeoJSON 하나(9.6 스키마)를 올리면 경계 안을 설계안으로 바꾸고, 대상지와 주변 ${s.meta?.params?.region?.boundary_buffer_m ?? ''} m를 다시 계산합니다.
    설계안은 실선이 아니라 점선으로 그립니다.</p>
    <p class="small"><button class="link" id="design-upload">올리기</button> · <button class="link" id="design-example">예제 설계안</button>${d.result || d.errors.length ? ' · <button class="link" id="design-clear">지우기</button>' : ''}
    · <a href="https://github.com/jacopast/gyeol/tree/main/templates" target="_blank" rel="noopener">템플릿·작성법</a>
    <input type="file" id="design-file" accept=".geojson,.json,application/geo+json,application/json"></p>`;
  if (d.errors.length) {
    return `${head}<div class="errors"><p>${esc(d.name)} — 오류 ${d.errors.length}개</p>${d.errors.map((e) => `<p>${esc(e)}</p>`).join('')}</div></section>`;
  }
  if (!d.result) return `${head}</section>`;
  const r = d.result;
  const rows = (b: Metrics, a: Metrics) => METRICS.filter((m) => m.group !== '맥락').map((m) =>
    `<tr><td>${esc(m.label)}</td><td>${fmtValue(m, b[m.id], s.units)}</td><td>${fmtValue(m, a[m.id], s.units)}</td><td>${diff(b[m.id], a[m.id])}</td></tr>`).join('');
  return `${head}
    <p class="small">${esc(d.name)} · 대상지 셀 ${r.siteCells}개, 버퍼 포함 ${r.bufferCells}개</p>
    ${(r.warnings ?? []).map((w) => `<p class="small">${esc(w)}</p>`).join('')}
    <div class="group">대상지</div>
    <table><tr><th>지표</th><th>기존</th><th>설계안</th><th>변화</th></tr>${rows(r.before, r.after)}</table>
    <details><summary class="small">대상지 + 버퍼</summary>
    <table><tr><th>지표</th><th>기존</th><th>설계안</th><th>변화</th></tr>${rows(r.beforeBuffer, r.afterBuffer)}</table></details>
    <p class="small">변화는 처방이 아닙니다. 같은 차이를 메우는 방법은 여러 가지이고, 지표를 채운다고 성과가 오른다는 보장은 없습니다(SPEC 8.3).</p></section>`;
}
