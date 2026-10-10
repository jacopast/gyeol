import 'maplibre-gl/dist/maplibre-gl.css';
import './style.css';
import { cellsToMultiPolygon, cellToBoundary } from 'h3-js';
import * as maplibregl from 'maplibre-gl';
import type { GeoJSONSource, MapMouseEvent } from 'maplibre-gl';
import mlWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import type { Lens, Meta, Metrics } from './engine';
import {
  exportJSON, importJSON, loadLibrary, nextId, parsePeerFilter, passesPeer, type Sample, saveLibrary, splitMetrics,
} from './library';
import { baseStyle, readTokens, repaint } from './mapstyle';
import { fmtValue, labelDefs, type MetricDef, METRICS, type Units } from './metrics';
import { quantileBreaks, stripChart } from './charts';
import { renderDesign, type DesignState } from './designui';
import { renderPersonality, type PersonalityState } from './personalityui';
import { importLabelCSV } from './labels';

const BASE = import.meta.env.BASE_URL;
// MapLibre v6는 타일 워커를 별도 모듈로 띄운다 — 번들러가 경로를 잃지 않게 직접 지정
maplibregl.setWorkerUrl(mlWorkerUrl);

// ---------------------------------------------------------------- 워커 RPC
const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
let rpcId = 0;
const pending = new Map<number, { res: (v: any) => void; rej: (e: Error) => void }>();
worker.onmessage = (ev) => {
  const p = pending.get(ev.data.id);
  if (!p) return;
  pending.delete(ev.data.id);
  if (ev.data.error) p.rej(new Error(ev.data.error));
  else p.res(ev.data.result);
};
export function rpc<T = any>(op: string, args: any = {}): Promise<T> {
  const id = ++rpcId;
  return new Promise((res, rej) => { pending.set(id, { res, rej }); worker.postMessage({ id, op, args }); });
}

// ---------------------------------------------------------------- 상태
interface SampleView { point: [number, number]; results: Record<number, { cells: number[]; metrics: Metrics }> }
export interface AppState {
  regions: { id: string; name: string; name_en?: string; center: [number, number] }[];
  region: string;
  meta: Meta | null;
  h3: string[];
  target: number[];
  lens: Lens;
  defaultLens: Lens;
  metric: string;
  breaks: number[];
  units: Units;
  sample: SampleView | null;
  addMinutes: number;
  library: Sample[];
  compare: Set<string>;
  peer: string;
  design: DesignState;
  personality: PersonalityState;
  busy: string;
  notice: string;
}

const S: AppState = {
  regions: [], region: '', meta: null, h3: [], target: [],
  lens: { definition: 'with_plaza_playground', decay: 'gaussian', alpha: 1, beta: 0.25 },
  defaultLens: { definition: 'with_plaza_playground', decay: 'gaussian', alpha: 1, beta: 0.25 },
  metric: 'os_gravity', breaks: [], units: { width: 'ft' }, sample: null, addMinutes: 10,
  library: loadLibrary(), compare: new Set(), peer: '', design: { result: null, errors: [], name: '' },
  personality: { model: null, targetType: null }, busy: '', notice: '',
};

const panel = document.getElementById('panel')!;
let map: maplibregl.Map;

// ---------------------------------------------------------------- 시작
async function start() {
  S.regions = await fetch(`${BASE}data/regions.json`).then((r) => r.json());
  const want = new URLSearchParams(location.search).get('r');
  S.region = S.regions.find((r) => r.id === want)?.id ?? S.regions[0]?.id ?? '';
  S.busy = '데이터를 읽는 중';
  render();
  const { meta, target } = await rpc<{ meta: Meta; target: number[] }>('load', { base: BASE, region: S.region });
  S.meta = meta;
  S.target = target;
  S.h3 = await fetch(`${BASE}data/regions/${S.region}/cells_h3.json`).then((r) => r.json());
  const a = meta.params.access;
  S.defaultLens = { definition: meta.params.open_space.default_definition, decay: a.default_decay, alpha: a.default_alpha, beta: a.default_beta };
  S.lens = { ...S.defaultLens };
  S.units.width = meta.units_display === 'imperial' ? 'ft' : 'm';
  await loadDemo();
  try {
    const r = await fetch(`${BASE}data/regions/${S.region}/personality.json`);
    if (r.ok) S.personality.model = await r.json();
  } catch { /* 성격 모드 데이터 없음 */ }
  initMap(meta);
}

async function loadDemo() {
  try {
    const r = await fetch(`${BASE}data/regions/${S.region}/demo_library.json`);
    if (!r.ok) return;
    const d = await r.json();
    const demo = (d.samples as Sample[]).map((s) => ({ ...s, demo: true }));
    S.library = [...S.library.filter((s) => !s.demo), ...demo];
  } catch { /* 데모 라이브러리 없음 */ }
}

function initMap(meta: Meta) {
  const t = readTokens();
  map = new maplibregl.Map({
    container: 'map', style: baseStyle(t), center: meta.center, zoom: 11.6,
    attributionControl: { compact: false }, dragRotate: false, pitchWithRotate: false,
  });
  map.touchZoomRotate.disableRotation();
  map.on('load', async () => {
    const feats = S.target.map((i) => ({
      type: 'Feature' as const, id: i, properties: { i, c: -1 },
      geometry: { type: 'Polygon' as const, coordinates: [cellToBoundary(S.h3[i], true)] },
    }));
    map.addSource('cells', { type: 'geojson', data: { type: 'FeatureCollection', features: feats } });
    map.addLayer({
      id: 'cells-fill', type: 'fill', source: 'cells',
      paint: {
        'fill-color': t.fg,
        'fill-opacity': ['match', ['get', 'c'], 0, 0.04, 1, 0.12, 2, 0.22, 3, 0.34, 4, 0.48, 5, 0.64, 0],
        'fill-antialias': false,
      },
    }, 'place');
    map.addSource('spaces', { type: 'geojson', data: `${BASE}data/regions/${S.region}/spaces.geojson` });
    map.addLayer({ id: 'spaces-line', type: 'line', source: 'spaces', minzoom: 13, paint: { 'line-color': t.muted, 'line-width': 0.5 } }, 'place');
    for (const id of ['library', 'sample', 'design', 'point']) map.addSource(id, { type: 'geojson', data: empty() });
    map.addLayer({ id: 'library-line', type: 'line', source: 'library', paint: { 'line-color': t.muted, 'line-width': 1 } });
    map.addLayer({ id: 'sample-10', type: 'line', source: 'sample', filter: ['==', ['get', 'm'], 10], paint: { 'line-color': t.fg, 'line-width': 1.6 } });
    map.addLayer({ id: 'sample-5', type: 'line', source: 'sample', filter: ['==', ['get', 'm'], 5], paint: { 'line-color': t.fg, 'line-width': 0.8 } });
    map.addLayer({ id: 'design-boundary', type: 'line', source: 'design', filter: ['==', ['get', 'role'], 'boundary'], paint: { 'line-color': t.fg, 'line-width': 1.6, 'line-dasharray': [3, 2] } });
    map.addLayer({ id: 'design-line', type: 'line', source: 'design', filter: ['!', ['in', ['get', 'role'], ['literal', ['boundary', 'cell', 'entrance']]]], paint: { 'line-color': t.fg, 'line-width': 0.8, 'line-dasharray': [2, 2] } });
    map.addLayer({ id: 'sample-point', type: 'circle', source: 'point', paint: { 'circle-radius': 4, 'circle-color': t.accent } });
    map.on('click', (e: MapMouseEvent) => takeSample(e.lngLat.lng, e.lngLat.lat));
    map.getCanvas().style.cursor = 'crosshair';
    S.busy = '';
    await refreshChoropleth();
    drawLibrary();
  });
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => repaint(map, readTokens()));
}

const empty = () => ({ type: 'FeatureCollection' as const, features: [] as any[] });

// ---------------------------------------------------------------- 지도
async function refreshChoropleth() {
  if (!S.meta) return;
  S.busy = '지도 계산 중';
  render();
  const v: Float64Array = await rpc('cellValues', { metric: S.metric, lens: S.lens });
  const vals = S.target.map((i) => v[i]).filter((x) => Number.isFinite(x));
  S.breaks = quantileBreaks(vals, 6);
  const cls = (x: number) => {
    if (!Number.isFinite(x)) return -1;
    let k = 0;
    while (k < S.breaks.length && x > S.breaks[k]) k++;
    return Math.min(k, 5);
  };
  const feats = S.target.map((i) => ({
    type: 'Feature' as const, id: i, properties: { i, c: cls(v[i]) },
    geometry: { type: 'Polygon' as const, coordinates: [cellToBoundary(S.h3[i], true)] },
  }));
  (map.getSource('cells') as GeoJSONSource).setData({ type: 'FeatureCollection', features: feats });
  S.busy = '';
  render();
}

function outline(cells: number[]) {
  const mp = cellsToMultiPolygon(cells.map((i) => S.h3[i]), true);
  return { type: 'MultiPolygon' as const, coordinates: mp };
}

async function takeSample(lon: number, lat: number) {
  if (!S.meta) return;
  S.busy = '권역 계산 중';
  render();
  const r = await rpc('sample', { lon, lat, lens: S.lens, minutes: S.meta.params.walk.sample_minutes });
  S.sample = { point: r.point, results: r.results };
  const feats = Object.entries(r.results as Record<string, { cells: number[] }>).map(([m, x]) => ({
    type: 'Feature' as const, properties: { m: Number(m) }, geometry: outline(x.cells),
  }));
  (map.getSource('sample') as GeoJSONSource).setData({ type: 'FeatureCollection', features: feats });
  (map.getSource('point') as GeoJSONSource).setData({ type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: r.point } }] });
  S.busy = '';
  render();
}

function drawLibrary() {
  if (!map?.getSource('library')) return;
  const feats = S.library.filter((s) => s.region === S.region && (S.compare.has(s.id) || !s.demo)).map((s) => ({
    type: 'Feature' as const, properties: { id: s.id }, geometry: s.walkshed as any,
  }));
  (map.getSource('library') as GeoJSONSource).setData({ type: 'FeatureCollection', features: feats });
}

export function setDesignGeo(fc: any) {
  (map.getSource('design') as GeoJSONSource)?.setData(fc ?? empty());
}

// ---------------------------------------------------------------- 패널
export function allDefs(): MetricDef[] {
  // 불러온 CSV·쌍대 비교 라벨도 비교 차트에 나온다 (지도에는 없음)
  const extra = new Set<string>();
  for (const s of S.library) for (const k of Object.keys(s.labels ?? {})) if (k.startsWith('csv_') || k.startsWith('pairwise_')) extra.add(k);
  const extraDefs = [...extra].sort().map((k) => ({ ...labelDefs([k])[0], label: k, unit: '', map: false }));
  return [...METRICS, ...labelDefs(S.meta?.label_columns ?? []), ...extraDefs];
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);
const lensIsDefault = () => JSON.stringify(S.lens) === JSON.stringify(S.defaultLens);

export function render() {
  const m = S.meta;
  const h: string[] = [];
  h.push(`<section><h1>결</h1>
    <p class="small">${m ? esc(m.name) : ''}${S.regions.length > 1 ? ' · ' + S.regions.filter((r) => r.id !== S.region).map((r) => `<a href="?r=${r.id}">${esc(r.name)}</a>`).join(' · ') : ''}</p>
    <p class="small">지도를 누르면 그 자리에서 걸어서 5분·10분 권역의 지표를 보여 줍니다. 무엇이 좋은지는 판단하지 않습니다.</p>
    ${S.busy ? `<p class="small">${S.busy}…</p>` : ''}${S.notice ? `<p class="small">${esc(S.notice)}</p>` : ''}</section>`);
  if (m) {
    h.push(renderMapSection());
    h.push(renderSampleSection());
    h.push(renderLibrarySection());
    h.push(renderCompareSection());
    h.push(renderDesign(S));
    h.push(renderPersonality({ personality: S.personality, units: S.units, current: currentTarget() }));
    h.push(renderFooter());
  }
  panel.innerHTML = h.join('');
}

function renderMapSection(): string {
  const groups = new Map<string, MetricDef[]>();
  for (const d of allDefs().filter((d) => d.map)) groups.set(d.group, [...(groups.get(d.group) ?? []), d]);
  const lists = [...groups.entries()].map(([g, ds]) => `<div class="group">${g}</div><div class="list">${ds
    .map((d) => `<button class="link" data-metric="${d.id}" aria-pressed="${d.id === S.metric}">${esc(d.label)}</button>`).join('')}</div>`).join('');
  const def = allDefs().find((d) => d.id === S.metric)!;
  const legend = S.breaks.length
    ? `<div class="legend">${[0, 1, 2, 3, 4, 5].map((k) => `<span style="border-top-color: color-mix(in srgb, var(--fg) ${[4, 12, 22, 34, 48, 64][k]}%, transparent)">${k === 0 ? '' : fmtValue(def, S.breaks[k - 1], S.units)}</span>`).join('')}</div>
       <p class="small">셀 하나 기준, 대상 지역 분위수 6단계. 칠하지 않은 셀 = 데이터 없음.</p>`
    : '';
  return `<section><h2>지도</h2>${lists}${legend}</section>`;
}

function renderSampleSection(): string {
  if (!S.sample) return `<section><h2>표본</h2><p class="small">지도를 눌러 표본을 찍으세요. 굵은 선 10분, 가는 선 5분.</p></section>`;
  const mins = Object.keys(S.sample.results).map(Number).sort((a, b) => a - b);
  const rows = allDefs().map((d) => {
    const cells = mins.map((mm) => {
      const v = S.sample!.results[mm].metrics[d.id];
      const t = fmtValue(d, v, S.units);
      return `<td class="${t === '데이터 없음' ? 'na' : ''}">${t}</td>`;
    }).join('');
    return `<tr><td>${esc(d.label)}</td>${cells}</tr>`;
  }).join('');
  const ms = S.sample.results[mins[mins.length - 1]].metrics.grain_multiscale as number[] | null;
  const [lon, lat] = S.sample.point;
  return `<section><h2>표본</h2>
    <p class="small">${lat.toFixed(5)}, ${lon.toFixed(5)} · 셀 ${mins.map((mm) => `${mm}분 ${S.sample!.results[mm].cells.length}개`).join(', ')}</p>
    <table><tr><th>지표</th>${mins.map((mm) => `<th>${mm}분</th>`).join('')}</tr>${rows}
    <tr><td>다중 스케일 결 (${S.meta!.params.raster.multiscale_m.join('/')} m, ${mins[mins.length - 1]}분)</td><td colspan="${mins.length}">${ms ? ms.map((x) => x.toFixed(2)).join(' / ') : '데이터 없음'}</td></tr></table>
    <p style="margin-top:8px"><input type="text" id="sample-name" placeholder="이름 (선택)"></p>
    <p class="row"><span>${mins.map((mm) => `<button class="link" data-addmin="${mm}" aria-pressed="${mm === S.addMinutes}">${mm}분</button>`).join(' · ')}</span>
    <button class="link" id="add-sample">라이브러리에 추가</button></p></section>`;
}

function renderLibrarySection(): string {
  const lib = S.library.filter((s) => s.region === S.region);
  const own = lib.filter((s) => !s.demo);
  const demo = lib.filter((s) => s.demo);
  const row = (s: Sample) => `<div class="lib-row"><input type="checkbox" data-cmp="${s.id}" ${S.compare.has(s.id) ? 'checked' : ''} aria-label="비교">
    <button class="link" data-fly="${s.id}" style="text-align:left">${esc(s.name || s.id)}</button>
    <span class="small">${s.walk_minutes}분 · ${s.created.slice(0, 10)}${s.params_hash !== S.meta!.params_hash ? ' · 다른 파라미터' : ''}</span></div>`;
  return `<section><h2>라이브러리</h2>
    ${own.length ? own.map(row).join('') : '<p class="small">아직 표본이 없습니다.</p>'}
    ${demo.length ? `<div class="group">시연 표본 ${demo.length}개 (맥락별 층화 추출) · <button class="link" id="cmp-demo">모두 비교에 넣기</button> · <button class="link" id="cmp-none">비교 비우기</button></div>
       <details><summary class="small">시연 표본 목록</summary>${demo.map(row).join('')}</details>` : ''}
    <p class="small" style="margin-top:6px"><button class="link" id="lib-export">내보내기</button> · <button class="link" id="lib-import">불러오기</button> · <button class="link" id="lib-csv">라벨 CSV 불러오기</button>
    <input type="file" id="lib-file" accept=".json,application/json"><input type="file" id="csv-file" accept=".csv,text/csv"></p></section>`;
}

/** 비교 대상: 현재 표본 또는 설계안. */
export function currentTarget(): { name: string; metrics: Metrics; dashed: boolean } | null {
  if (S.design.result?.after) return { name: '설계안', metrics: S.design.result.after, dashed: true };
  if (S.sample) return { name: '현재 표본', metrics: S.sample.results[S.addMinutes]?.metrics ?? {}, dashed: false };
  return null;
}

function comparisonSet(): Sample[] {
  const rules = parsePeerFilter(S.peer);
  return S.library.filter((s) => s.region === S.region && S.compare.has(s.id) && passesPeer(s, rules));
}

function renderCompareSection(): string {
  const set = comparisonSet();
  const tgt = currentTarget();
  const rules = parsePeerFilter(S.peer);
  const hashes = new Set(set.map((s) => s.params_hash));
  const warn = hashes.size > 1 || [...hashes].some((x) => x !== S.meta!.params_hash)
    ? '<p class="small">경고: 파라미터(params_hash)가 다른 표본이 섞여 있습니다. 같은 정의로 계산된 값이 아닙니다.</p>' : '';
  const charts = set.length || tgt
    ? allDefs().filter((d) => d.group !== '맥락').map((d) => {
      const pts = set.map((s) => ({ v: (s.metrics[d.id] ?? s.labels[d.id] ?? s.context[d.id]) as number | null, name: s.name || s.id }));
      const tv = (tgt?.metrics[d.id] as number | null | undefined) ?? null;
      return stripChart(d, pts, tv, S.units, tgt?.dashed ?? false);
    }).join('')
    : '';
  return `<section><h2>비교</h2>
    <p class="small">점 = 비교에 넣은 라이브러리 표본, 선 = ${tgt ? esc(tgt.name) : '현재 대상 없음'}. 단일 종합 점수는 없습니다.</p>
    <p class="small">동류 집단 필터 (줄마다 <code>ctx_density 100 400</code>)</p>
    <textarea id="peer" rows="2">${esc(S.peer)}</textarea>
    <p class="small">${rules.length ? `필터 ${rules.length}개 · ` : ''}비교 표본 ${set.length}개</p>${warn}${charts}</section>`;
}

function renderFooter(): string {
  const m = S.meta!;
  const a = m.params.access;
  const opt = (key: keyof Lens, vals: (string | number)[]) => vals.map((v) => `<button class="link" data-lens="${key}" data-val="${v}" aria-pressed="${S.lens[key] === v}">${v}</button>`).join(' ');
  return `<section class="footer">
    <p>${lensIsDefault() ? '' : '<span class="temp">임시 실행 — 기본 렌즈와 다릅니다 · <button class="link" id="lens-reset">기본으로</button></span><br>'}
    실행 ${m.run_id} · params_hash <code>${m.params_hash}</code></p>
    <p>공간 정의 ${opt('definition', m.params.open_space.definitions)}</p>
    <p>감쇠 ${opt('decay', a.decays)} · α ${opt('alpha', a.alphas)} · β ${opt('beta', a.betas)}</p>
    <p>보행 ${m.params.walk.speed_mps} m/s · 서비스권 r0 ${a.r0_m} m · 셀 H3 ${10} · 래스터 ${m.params.raster.resolution_m} m</p>
    <p>폭 단위 <button class="link" data-unit="ft" aria-pressed="${S.units.width === 'ft'}">ft</button> <button class="link" data-unit="m" aria-pressed="${S.units.width === 'm'}">m</button></p>
    ${m.missing_layers.length ? `<p>데이터 없음: ${m.missing_layers.join(', ')}</p>` : ''}
    <p><a href="https://github.com/jacopast/gyeol" target="_blank" rel="noopener">지표 정의·출처·한계 (GitHub)</a></p></section>`;
}

// ---------------------------------------------------------------- 이벤트
panel.addEventListener('click', async (e) => {
  const el = (e.target as HTMLElement).closest('button, input[type=checkbox]') as HTMLElement | null;
  if (!el) return;
  const d = el.dataset;
  if (d.metric) { S.metric = d.metric; await refreshChoropleth(); return; }
  if (d.addmin) { S.addMinutes = Number(d.addmin); render(); return; }
  if (d.unit) { S.units.width = d.unit as 'ft' | 'm'; render(); return; }
  if (d.lens) {
    const key = d.lens as keyof Lens;
    (S.lens as any)[key] = key === 'alpha' || key === 'beta' ? Number(d.val) : d.val;
    await refreshChoropleth();
    if (S.sample) await takeSample(S.sample.point[0], S.sample.point[1]);
    return;
  }
  if (el.id === 'lens-reset') { S.lens = { ...S.defaultLens }; await refreshChoropleth(); return; }
  if (d.cmp) { (el as HTMLInputElement).checked ? S.compare.add(d.cmp) : S.compare.delete(d.cmp); drawLibrary(); render(); return; }
  if (d.fly) {
    const s = S.library.find((x) => x.id === d.fly);
    if (s) { map.flyTo({ center: s.point, zoom: 14.5 }); S.compare.add(s.id); drawLibrary(); render(); }
    return;
  }
  if (el.id === 'cmp-demo') { S.library.filter((s) => s.demo).forEach((s) => S.compare.add(s.id)); drawLibrary(); render(); return; }
  if (el.id === 'cmp-none') { S.compare.clear(); drawLibrary(); render(); return; }
  if (el.id === 'add-sample') return addSample();
  if (el.id === 'lib-export') return download('gyeol-library.json', exportJSON(S.library));
  if (el.id === 'lib-import') return (document.getElementById('lib-file') as HTMLInputElement).click();
  if (el.id === 'lib-csv') return (document.getElementById('csv-file') as HTMLInputElement).click();
  await handleDesignClick(el);
});

panel.addEventListener('change', async (e) => {
  const el = e.target as HTMLInputElement;
  if (el.id === 'lib-file' && el.files?.[0]) {
    try {
      const add = importJSON(await el.files[0].text());
      const ids = new Set(S.library.map((s) => s.id));
      S.library.push(...add.filter((s) => !ids.has(s.id)));
      saveLibrary(S.library);
      drawLibrary();
    } catch (err) { alertLine(`불러오기 실패: ${(err as Error).message}`); }
    render();
  }
  if (el.id === 'csv-file' && el.files?.[0]) {
    const msg = importLabelCSV(await el.files[0].text(), S.library.filter((s) => !s.demo));
    saveLibrary(S.library);
    alertLine(msg);
    render();
  }
  if (el.id === 'design-file' && el.files?.[0]) await loadDesign(el.files[0]);
});

panel.addEventListener('input', (e) => {
  const el = e.target as HTMLTextAreaElement;
  if (el.id === 'peer') {
    S.peer = el.value;
    clearTimeout((el as any)._t);
    (el as any)._t = setTimeout(() => { const pos = el.selectionStart; render(); const n = document.getElementById('peer') as HTMLTextAreaElement; n.focus(); n.setSelectionRange(pos, pos); }, 500);
  }
});

function addSample() {
  if (!S.sample || !S.meta) return;
  const r = S.sample.results[S.addMinutes];
  const name = (document.getElementById('sample-name') as HTMLInputElement)?.value.trim() ?? '';
  const parts = splitMetrics(r.metrics);
  const s: Sample = {
    id: nextId(S.library), name, region: S.region, point: S.sample.point, walk_minutes: S.addMinutes,
    walkshed: outline(r.cells), created: new Date().toISOString(), params_hash: S.meta.params_hash, lens: { ...S.lens },
    ...parts, notes: '',
  };
  S.library.push(s);
  S.compare.add(s.id);
  saveLibrary(S.library);
  drawLibrary();
  render();
}

export function alertLine(msg: string) { S.notice = msg; }

function download(name: string, text: string) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

// 설계안 (designui.ts에서 렌더, 여기서 이벤트)
async function loadDesign(file: File) {
  let fc: any;
  try { fc = JSON.parse(await file.text()); } catch { S.design = { result: null, errors: ['GeoJSON을 읽을 수 없습니다 (JSON 형식 오류).'], name: file.name }; render(); return; }
  S.design.name = file.name;
  S.busy = '설계안 재계산 중';
  render();
  try {
    const res = await rpc('design', { fc, lens: S.lens });
    S.design = { result: res.errors?.length ? null : res, errors: res.errors ?? [], name: file.name };
    if (!res.errors?.length) {
      setDesignGeo(res.geo);
      const b = res.bounds;
      if (b) map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 60 });
    }
  } catch (err) { S.design = { result: null, errors: [String((err as Error).message)], name: file.name }; }
  S.busy = '';
  render();
}

async function handleDesignClick(el: HTMLElement) {
  if (el.id === 'design-upload') (document.getElementById('design-file') as HTMLInputElement).click();
  if (el.id === 'design-example') {
    const r = await fetch(`${BASE}data/regions/${S.region}/design_example.geojson`);
    if (r.ok) await loadDesign(new File([await r.text()], 'design_example.geojson'));
  }
  if (el.id === 'design-clear') { S.design = { result: null, errors: [], name: '' }; setDesignGeo(null); render(); }
  if (el.dataset.ptype) { S.personality.targetType = el.dataset.ptype; render(); }
}

export function state() { return S; }
if (import.meta.env.DEV) (window as any).__g = { map: () => map, S };

start().catch((e) => { S.busy = `오류: ${e.message}`; render(); });
