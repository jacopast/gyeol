// 계산 엔진 — DOM 없음. 웹 워커와 테스트(교차 검증)가 같이 쓴다.
// Python 기준 구현 pipeline/gyeol/sample.py 와 같은 알고리즘이어야 한다 (SPEC 9.8).

export interface Meta {
  id: string;
  name: string;
  name_en?: string;
  bounds: [number, number, number, number];
  center: [number, number];
  units_display: string;
  run_id: string;
  params_hash: string;
  params: any;
  n_cells: number;
  columns: string[];
  network: { n_nodes: number; n_entries: number };
  lu_columns: string[];
  label_columns: string[];
  missing_layers: string[];
}

export interface Lens {
  definition: string;
  decay: string;
  alpha: number;
  beta: number;
}

export type Metrics = Record<string, number | number[] | null>;

export class Network {
  lon: Float32Array;
  lat: Float32Array;
  indptr: Int32Array;
  indices: Int32Array;
  weights: Float32Array;
  n: number;

  constructor(buf: ArrayBuffer, nNodes: number, nEntries: number) {
    let o = 0;
    this.lon = new Float32Array(buf, o, nNodes); o += nNodes * 4;
    this.lat = new Float32Array(buf, o, nNodes); o += nNodes * 4;
    this.indptr = new Int32Array(buf, o, nNodes + 1); o += (nNodes + 1) * 4;
    this.indices = new Int32Array(buf, o, nEntries); o += nEntries * 4;
    this.weights = new Float32Array(buf, o, nEntries);
    this.n = nNodes;
  }

  /** 가장 가까운 노드 (등장방형 근사 — 도시 규모에서 충분). */
  nearest(lon: number, lat: number): number {
    const k = Math.cos((lat * Math.PI) / 180);
    let best = -1;
    let bd = Infinity;
    for (let i = 0; i < this.n; i++) {
      const dx = (this.lon[i] - lon) * k;
      const dy = this.lat[i] - lat;
      const d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = i; }
    }
    return best;
  }

  /** 여러 출발점 다익스트라, limit 밖은 Infinity. extra 간선(설계안 ped_link)과 끊긴 간선(barrier)을 받을 수 있다. */
  dijkstra(sources: number[], limit: number, mod?: NetMod): Float64Array {
    const n = this.n + (mod?.extraNodes ?? 0);
    const dist = new Float64Array(n).fill(Infinity);
    const heap = new Heap();
    for (const s of sources) { dist[s] = 0; heap.push(0, s); }
    while (heap.size) {
      const [d, u] = heap.pop();
      if (d > dist[u]) continue;
      const relax = (v: number, w: number) => {
        const nd = d + w;
        if (nd <= limit && nd < dist[v]) { dist[v] = nd; heap.push(nd, v); }
      };
      if (u < this.n) {
        for (let e = this.indptr[u]; e < this.indptr[u + 1]; e++) {
          const v = this.indices[e];
          if (mod?.blocked && mod.blocked.has(edgeKey(u, v))) continue;
          relax(v, this.weights[e]);
        }
      }
      const ex = mod?.extra.get(u);
      if (ex) for (const [v, w] of ex) relax(v, w);
    }
    return dist;
  }
}

export interface NetMod {
  extra: Map<number, [number, number][]>;
  blocked: Set<string>;
  extraNodes: number;
}

export function edgeKey(a: number, b: number): string {
  return a < b ? `${a}-${b}` : `${b}-${a}`;
}

class Heap {
  private k: number[] = [];
  private v: number[] = [];
  get size() { return this.k.length; }
  push(key: number, val: number) {
    const k = this.k, v = this.v;
    k.push(key); v.push(val);
    let i = k.length - 1;
    while (i > 0) {
      const p = (i - 1) >> 1;
      if (k[p] <= k[i]) break;
      [k[p], k[i]] = [k[i], k[p]]; [v[p], v[i]] = [v[i], v[p]];
      i = p;
    }
  }
  pop(): [number, number] {
    const k = this.k, v = this.v;
    const top: [number, number] = [k[0], v[0]];
    const lk = k.pop()!, lv = v.pop()!;
    if (k.length) {
      k[0] = lk; v[0] = lv;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < k.length && k[l] < k[m]) m = l;
        if (r < k.length && k[r] < k[m]) m = r;
        if (m === i) break;
        [k[m], k[i]] = [k[i], k[m]]; [v[m], v[i]] = [v[i], v[m]];
        i = m;
      }
    }
    return top;
  }
}

/** 셀 열 묶음 (열 우선 Float32). */
export class Cells {
  cols: Map<string, Float32Array> = new Map();
  n: number;
  constructor(buf: ArrayBuffer, columns: string[], n: number) {
    this.n = n;
    columns.forEach((c, i) => this.cols.set(c, new Float32Array(buf, i * n * 4, n)));
  }
  col(name: string): Float32Array | undefined {
    return this.cols.get(name);
  }
}

export function lensKey(kind: string, d: string, decay = '', alpha: number | null = null, beta: number | null = null, demand = ''): string {
  const parts = [kind, d];
  if (decay) parts.push(decay);
  if (alpha !== null) parts.push(`a${fmt(alpha)}`);
  if (beta !== null) parts.push(`b${fmt(beta)}`);
  if (demand) parts.push(demand);
  return parts.join('|');
}

// Python str(float): 1.0 → "1.0", 0.25 → "0.25", 0 → "0.0"
function fmt(x: number): string {
  return Number.isInteger(x) ? x.toFixed(1) : String(x);
}

export function walkshedCells(net: Network, cellNode: Float32Array, start: number, minutes: number, speed: number, mod?: NetMod): number[] {
  const lim = minutes * 60 * speed;
  const d = net.dijkstra([start], lim, mod);
  const out: number[] = [];
  for (let i = 0; i < cellNode.length; i++) {
    const nd = cellNode[i];
    if (nd >= 0 && d[nd] <= lim) out.push(i);
  }
  return out;
}

const div = (a: number | null, b: number | null): number | null =>
  a === null || b === null || b === 0 || !Number.isFinite(b) || !Number.isFinite(a) ? null : a / b;

export function entropy(counts: number[]): number | null {
  const c = counts.filter((x) => x > 0);
  const s = c.reduce((a, b) => a + b, 0);
  if (s === 0) return null;
  let h = 0;
  for (const x of c) { const p = x / s; h -= p * Math.log(p); }
  return h;
}

export function interspersion(nP: number, nQ: number, PP: number, PQ: number, QQ: number): number | null {
  const tot = nP + nQ;
  const pairs = PP + PQ + QQ;
  if (tot === 0 || pairs === 0) return null;
  const p = nP / tot;
  const exp = 2 * p * (1 - p);
  if (exp === 0) return null;
  return PQ / pairs / exp;
}

/** 권역(셀 목록)의 지표. Python sample.aggregate와 같은 정의. */
export function aggregate(idx: number[], cells: Cells, poiRows: number[][], lens: Lens, meta: Meta): Metrics {
  const prm = meta.params;
  const d = lens.definition;
  const variant = d === 'with_pops' ? 'pops' : 'base';
  const res: number = prm.raster.resolution_m;
  const out: Metrics = {};
  const sum = (col: string): number => {
    const c = cells.col(col);
    if (!c) return 0;
    let s = 0;
    for (const i of idx) { const v = c[i]; if (Number.isFinite(v)) s += v; }
    return s;
  };
  const has = (col: string) => cells.cols.has(col);
  const mean = (col: string): number | null => {
    const c = cells.col(col);
    if (!c || !idx.length) return null;
    let s = 0;
    for (const i of idx) s += c[i];
    return s / idx.length;
  };

  out.os_gravity = mean(lensKey('os_gravity', d, lens.decay, lens.alpha, lens.beta));
  out.os_g2sfca_night = mean(lensKey('os_g2sfca', d, lens.decay, null, lens.beta, 'night'));
  out.os_g2sfca_day = mean(lensKey('os_g2sfca', d, lens.decay, null, lens.beta, 'day'));
  const pop = cells.col('pop_night')!;
  for (const mins of prm.access.cover_minutes as number[]) {
    const cov = cells.col(lensKey(`os_cover_${mins}`, d));
    let a = 0, b = 0;
    if (cov) for (const i of idx) { const p = Number.isFinite(pop[i]) ? pop[i] : 0; a += p * cov[i]; b += p; }
    out[`os_cover_${mins}`] = div(a, b);
  }
  const green = sum('a_open_free_green_m2') + (variant === 'pops' ? sum('a_pops_green_m2') : 0);
  const opena = sum('a_open_free_m2') + (variant === 'pops' ? sum('a_pops_m2') : 0);
  out.os_greenness = div(green, opena);

  const pre = `g_${variant}_${res}_`;
  const nP = sum(pre + 'nP'), nQ = sum(pre + 'nQ'), nV = sum(pre + 'nV');
  const ground = nP + nQ + nV;
  out.nolli_ratio = div(nP, ground);
  out.edge_density = div(sum(pre + 'PQ') * res, (ground * res * res) / 1e4);
  const ms: (number | null)[] = [];
  for (const r of prm.raster.multiscale_m as number[]) {
    const p = `g_${variant}_${r}_`;
    ms.push(interspersion(sum(p + 'nP'), sum(p + 'nQ'), sum(p + 'PP'), sum(p + 'PQ'), sum(p + 'QQ')));
  }
  out.interspersion = ms[0];
  out.grain_multiscale = ms.every((x) => x !== null) ? (ms as number[]) : null;
  const pc = cells.col(`patch_${variant}_max_m2`);
  let pmax = -Infinity;
  if (pc) for (const i of idx) pmax = Math.max(pmax, pc[i]);
  out.largest_public_patch = idx.length && pc ? pmax : null;

  const sl = has('street_len_m') ? sum('street_len_m') : 0;
  const sw = sum('a_sidewalk_m2'), rw = sum('a_roadway_m2');
  out.sidewalk_width = sl ? div(sw, sl * prm.streets.sides) : null;
  const landHa = sum('land_m2') / 1e4;
  const demand = sum('pop_night') + sum('pop_day');
  const dens = div(demand, landHa);
  out.sidewalk_adequacy = out.sidewalk_width !== null ? div(out.sidewalk_width as number, dens) : null;
  out.lane_share = div(rw, rw + sw);
  const hmean = has('bldg_street_a_m2') ? div(sum('bldg_street_ha_m3'), sum('bldg_street_a_m2')) : null;
  const roww = sl ? div(rw + sw, sl) : null;
  out.enclosure = roww !== null ? div(roww, hmean) : null;
  out.frontage_permeability = null;

  const tcols = meta.columns.filter((c) => c.startsWith('amen_t_'));
  if (tcols.length) {
    let s = 0, ok = true;
    for (const i of idx) {
      let m = -Infinity;
      for (const c of tcols) { const v = cells.col(c)![i]; if (!Number.isFinite(v)) ok = false; m = Math.max(m, v); }
      s += m;
    }
    out.amenity_daily = ok && idx.length ? s / idx.length : null;
  } else out.amenity_daily = null;
  const tot = new Map<number, number>();
  for (const i of idx) {
    const row = poiRows[i];
    for (let k = 0; k < row.length; k += 2) tot.set(row[k], (tot.get(row[k]) ?? 0) + row[k + 1]);
  }
  out.amenity_diversity = entropy([...tot.values()]);

  out.ctx_density = div(sum('pop_night'), landHa);
  const lu = meta.lu_columns;
  if (lu.length) {
    const h = entropy(lu.map(sum));
    out.ctx_landuse_mix = h === null ? null : h / Math.log(lu.length);
  } else out.ctx_landuse_mix = null;
  out.ctx_daytime_ratio = hasData(cells, 'pop_day') ? div(sum('pop_day'), sum('pop_night')) : null;
  const inc = cells.col('income');
  if (inc) {
    let a = 0, b = 0;
    for (const i of idx) { const p = Number.isFinite(pop[i]) ? pop[i] : 0; if (Number.isFinite(inc[i]) && p > 0) { a += inc[i] * p; b += p; } }
    out.ctx_income = div(a, b);
  } else out.ctx_income = null;
  const land = cells.col('land_m2')!;
  for (const col of meta.label_columns) {
    const c = cells.col(col)!;
    let a = 0, b = 0;
    for (const i of idx) if (Number.isFinite(c[i])) { a += c[i] * land[i]; b += land[i]; }
    out[col] = div(a, b);
  }
  return out;
}

const hasDataCache = new WeakMap<Cells, Map<string, boolean>>();
/** 지역 전체에 그 열의 값이 하나라도 있는가 (없으면 그 데이터에 기대는 지표는 데이터 없음). */
export function hasData(cells: Cells, col: string): boolean {
  let m = hasDataCache.get(cells);
  if (!m) { m = new Map(); hasDataCache.set(cells, m); }
  if (!m.has(col)) { const c = cells.col(col); m.set(col, !!c && c.some((v) => Number.isFinite(v))); }
  return m.get(col)!;
}

/** 지도용: 셀 하나짜리 권역으로 각 셀의 지표 값. */
export function cellValues(metric: string, cells: Cells, poiRows: number[][], lens: Lens, meta: Meta, targetIdx: number[]): Float64Array {
  const out = new Float64Array(cells.n).fill(NaN);
  for (const i of targetIdx) {
    const v = aggregate([i], cells, poiRows, lens, meta)[metric];
    out[i] = typeof v === 'number' ? v : NaN;
  }
  return out;
}
