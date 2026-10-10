// 설계안 업로드 (SPEC 9.6, M6): 검증 → 대상지 안을 설계안으로 교체 → 대상지+버퍼 재계산 → 전후 비교
import { cellToBoundary, cellToLatLng, latLngToCell } from 'h3-js';
import { accessColumns, cloneCells, maxReach, type SpaceRec, spaceCellDist } from './access';
import { aggregate, type Cells, edgeKey, type Lens, type Meta, type Metrics, type Network, type NetMod } from './engine';

export interface DesignResult {
  errors: string[];
  warnings?: string[];
  before?: Metrics;
  after?: Metrics;
  beforeBuffer?: Metrics;
  afterBuffer?: Metrics;
  siteCells?: number;
  bufferCells?: number;
  geo?: any;
  bounds?: number[];
}

const LAYERS: Record<string, string[]> = {
  boundary: ['Polygon', 'MultiPolygon'], open_space: ['Polygon', 'MultiPolygon'], entrance: ['Point'],
  sidewalk: ['Polygon', 'MultiPolygon'], roadway: ['Polygon', 'MultiPolygon'], building: ['Polygon', 'MultiPolygon'],
  ped_link: ['LineString', 'MultiLineString'], barrier: ['LineString', 'MultiLineString'], frontage: ['LineString', 'MultiLineString'],
};

const isNum = (v: unknown) => typeof v === 'number' && Number.isFinite(v);

/** 9.6 스키마 검증. 오류 = 한 줄씩 (어느 피처의 어느 속성). */
export function validateDesign(fc: any, meta?: Meta): { errors: string[]; warnings: string[] } {
  const errors: string[] = [];
  const warnings: string[] = [];
  if (!fc || fc.type !== 'FeatureCollection' || !Array.isArray(fc.features)) return { errors: ['GeoJSON FeatureCollection이 아닙니다 (type, features 확인).'], warnings };
  const osIds = new Set<string>();
  fc.features.forEach((f: any) => { if (f?.properties?.layer === 'open_space' && f.properties.id != null) osIds.add(String(f.properties.id)); });
  let nb = 0;
  fc.features.forEach((f: any, i: number) => {
    const p = f?.properties ?? {};
    const tag = `피처 ${i + 1}${p.layer ? ` (${p.layer})` : ''}`;
    if (!p.layer) { errors.push(`${tag}: layer 속성 없음 (${Object.keys(LAYERS).join(' / ')})`); return; }
    if (!LAYERS[p.layer]) { errors.push(`${tag}: 알 수 없는 layer "${p.layer}"`); return; }
    if (!f.geometry || !LAYERS[p.layer].includes(f.geometry.type)) { errors.push(`${tag}: 도형은 ${LAYERS[p.layer].join(' 또는 ')}이어야 함 (지금 ${f.geometry?.type ?? '없음'})`); return; }
    if (!coordsOk(f.geometry.coordinates)) errors.push(`${tag}: 좌표가 WGS84 경위도가 아님 (경도 -180~180, 위도 -90~90) — README의 좌표 변환 참고`);
    switch (p.layer) {
      case 'boundary': nb++; break;
      case 'open_space':
        if (!['free', 'conditional', 'restricted'].includes(p.access)) errors.push(`${tag}: access 없음 또는 잘못됨 (free / conditional / restricted)`);
        if (!p.kind || typeof p.kind !== 'string') errors.push(`${tag}: kind 없음 (park, plaza, playground, garden …)`);
        if (!isNum(p.green_ratio) || p.green_ratio < 0 || p.green_ratio > 1) errors.push(`${tag}: green_ratio 없음 또는 범위 밖 (0~1 숫자)`);
        break;
      case 'entrance':
        if (p.serves == null) errors.push(`${tag}: serves 없음 (open_space의 id)`);
        else if (!osIds.has(String(p.serves))) errors.push(`${tag}: serves "${p.serves}"와 같은 id의 open_space가 없음`);
        break;
      case 'sidewalk':
        if (p.clear_width_m != null && (!isNum(p.clear_width_m) || p.clear_width_m <= 0)) errors.push(`${tag}: clear_width_m은 0보다 큰 숫자`);
        break;
      case 'roadway':
        if (!Number.isInteger(p.lanes) || p.lanes < 0) errors.push(`${tag}: lanes 없음 (0 이상 정수)`);
        if (!['car', 'bus', 'bike', 'loading'].includes(p.use)) errors.push(`${tag}: use 없음 또는 잘못됨 (car / bus / bike / loading)`);
        break;
      case 'building':
        if (!isNum(p.height_m) || p.height_m <= 0) errors.push(`${tag}: height_m 없음 (0보다 큰 숫자, 미터)`);
        if (!p.ground_use || typeof p.ground_use !== 'string') errors.push(`${tag}: ground_use 없음 (예: residential, retail, office)`);
        for (const k of ['units', 'jobs']) if (p[k] != null && (!isNum(p[k]) || p[k] < 0)) errors.push(`${tag}: ${k}는 0 이상 숫자`);
        break;
      case 'frontage':
        if (!isNum(p.doors_per_100m) || p.doors_per_100m < 0) errors.push(`${tag}: doors_per_100m 없음 (0 이상 숫자)`);
        if (!isNum(p.transparency) || p.transparency < 0 || p.transparency > 1) errors.push(`${tag}: transparency 없음 (0~1 숫자)`);
        break;
    }
  });
  if (nb !== 1) errors.push(`boundary 피처가 정확히 1개여야 함 (지금 ${nb}개)`);
  if (meta && !errors.length) {
    const b = fc.features.find((f: any) => f.properties.layer === 'boundary');
    const [w, s, e, n] = bbox(b.geometry.coordinates);
    const [W, S, E, N] = meta.bounds;
    if (e < W || w > E || n < S || s > N) errors.push(`boundary가 이 지역(${meta.name}) 범위 밖에 있음`);
  }
  return { errors, warnings };
}

function coordsOk(c: any): boolean {
  if (typeof c[0] === 'number') return Math.abs(c[0]) <= 180 && Math.abs(c[1]) <= 90;
  return Array.isArray(c) && c.every(coordsOk);
}

function flat(c: any, out: number[][] = []): number[][] {
  if (typeof c[0] === 'number') out.push(c);
  else for (const x of c) flat(x, out);
  return out;
}

function bbox(c: any): number[] {
  const pts = flat(c);
  return [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))];
}

// ---------------------------------------------------------------- 지역 미터 좌표 (대상지 규모에서 충분한 등장방형 근사)
class Local {
  kx: number; ky = 110540;
  constructor(public lon0: number, public lat0: number) { this.kx = 111320 * Math.cos((lat0 * Math.PI) / 180); }
  xy(lon: number, lat: number): [number, number] { return [(lon - this.lon0) * this.kx, (lat - this.lat0) * this.ky]; }
  ll(x: number, y: number): [number, number] { return [this.lon0 + x / this.kx, this.lat0 + y / this.ky]; }
}

type Ring = [number, number][];
type Poly = Ring[]; // 바깥 + 구멍

function polys(geom: any, L: Local): Poly[] {
  const cs = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;
  return cs.map((p: number[][][]) => p.map((r) => r.map(([lo, la]) => L.xy(lo, la)) as Ring));
}
function lines(geom: any, L: Local): Ring[] {
  const cs = geom.type === 'LineString' ? [geom.coordinates] : geom.coordinates;
  return cs.map((r: number[][]) => r.map(([lo, la]) => L.xy(lo, la)) as Ring);
}
function inRing(x: number, y: number, r: Ring): boolean {
  let c = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i], [xj, yj] = r[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}
function inPoly(x: number, y: number, p: Poly): boolean { return inRing(x, y, p[0]) && !p.slice(1).some((h) => inRing(x, y, h)); }
function ringArea(r: Ring): number { let a = 0; for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[j][0] + r[i][0]) * (r[j][1] - r[i][1]); return Math.abs(a / 2); }
function polyArea(p: Poly): number { return ringArea(p[0]) - p.slice(1).reduce((s, h) => s + ringArea(h), 0); }
function lineLen(r: Ring): number { let s = 0; for (let i = 1; i < r.length; i++) s += Math.hypot(r[i][0] - r[i - 1][0], r[i][1] - r[i - 1][1]); return s; }
function segX(a: number[], b: number[], c: number[], d: number[]): boolean {
  const o = (p: number[], q: number[], r: number[]) => Math.sign((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]));
  return o(a, b, c) !== o(a, b, d) && o(c, d, a) !== o(c, d, b);
}

interface WS { meta: Meta; net: Network; cells: Cells; poiRows: number[][]; spaces: SpaceRec[]; target: number[] }

export function designRecompute(S: WS, fc: any, lens: Lens): DesignResult {
  const { errors, warnings } = validateDesign(fc, S.meta);
  if (errors.length) return { errors, warnings };
  const prm = S.meta.params;
  const res: number = prm.raster.resolution_m;
  const feats = fc.features as any[];
  const bf = feats.find((f) => f.properties.layer === 'boundary');
  const [bw, bs, be, bn] = bbox(bf.geometry.coordinates);
  const L = new Local((bw + be) / 2, (bs + bn) / 2);
  const bnd = polys(bf.geometry, L);
  const inB = (x: number, y: number) => bnd.some((p) => inPoly(x, y, p));
  const byLayer = (l: string) => feats.filter((f) => f.properties.layer === l);

  // ---- 1. 대상지 안 5 m 래스터 (설계안이 전부를 정한다; 지정 없는 땅은 사적)
  const [x0, y0] = L.xy(bw, bs);
  const [x1, y1] = L.xy(be, bn);
  const W = Math.ceil((x1 - x0) / res), H = Math.ceil((y1 - y0) / res);
  const cls = new Uint8Array(W * H); // 0 = 대상지 밖
  const spaceOf = new Int32Array(W * H).fill(-1);
  const cellOf = new Int32Array(W * H).fill(-1);
  const h3Index = new Map<string, number>();
  const cellsH3 = (S as any).h3 as string[] | undefined;
  if (!cellsH3) throw new Error('셀 H3 목록 없음');
  cellsH3.forEach((h, i) => h3Index.set(h, i));
  const osFeats = byLayer('open_space');
  const osPolys = osFeats.map((f) => polys(f.geometry, L));
  const sw = byLayer('sidewalk').map((f) => polys(f.geometry, L));
  const rw = byLayer('roadway').map((f) => polys(f.geometry, L));
  const bl = byLayer('building').map((f) => polys(f.geometry, L));
  const hit = (ps: Poly[][], x: number, y: number) => ps.findIndex((pp) => pp.some((p) => inPoly(x, y, p)));
  for (let r = 0; r < H; r++) {
    for (let c = 0; c < W; c++) {
      const x = x0 + (c + 0.5) * res, y = y0 + (r + 0.5) * res;
      if (!inB(x, y)) continue;
      const k = r * W + c;
      const [lo, la] = L.ll(x, y);
      const ci = h3Index.get(latLngToCell(la, lo, 10));
      if (ci === undefined) continue; // 셀 밖(물 등)
      cellOf[k] = ci;
      let v = 3;
      if (hit(rw, x, y) >= 0) v = 2;
      if (hit(sw, x, y) >= 0) v = 4;
      if (hit(bl, x, y) >= 0) v = 3;
      const oi = hit(osPolys, x, y);
      if (oi >= 0) {
        const acc = osFeats[oi].properties.access;
        const kind = osFeats[oi].properties.kind;
        v = acc === 'free' ? (kind === 'pops' ? 6 : 1) : acc === 'conditional' ? (kind === 'pops' ? 6 : 5) : 3;
        spaceOf[k] = oi;
      }
      cls[k] = v;
    }
  }
  const site = new Map<number, number>(); // 셀 → 대상지 안 픽셀 수
  for (let k = 0; k < cls.length; k++) if (cellOf[k] >= 0) site.set(cellOf[k], (site.get(cellOf[k]) ?? 0) + 1);
  if (!site.size) return { errors: ['boundary 안에 이 지역의 셀이 없습니다 (물 위이거나 범위 밖).'], warnings };

  // ---- 2. 셀 가산 통계 교체: 셀의 대상지 밖 몫(1−f)은 기존 값을 비례로, 안쪽은 새로 센 값
  const after = cloneCells(S.cells);
  const col = (c: Cells, k: string) => c.col(k)!;
  const frac = new Map<number, number>();
  for (const [ci, n] of site) {
    const ground = col(S.cells, `g_base_${res}_nP`)[ci] + col(S.cells, `g_base_${res}_nQ`)[ci] + col(S.cells, `g_base_${res}_nV`)[ci];
    frac.set(ci, ground > 0 ? Math.min(1, n / ground) : 1);
  }
  // 가로 중심선 길이는 바꾸지 않는다: 스키마에 중심선 레이어가 없고, 차로 면적으로 길이를 추정하면 차로를 줄일 때 길이가 늘어나는 왜곡이 생긴다
  const scaleCols = S.meta.columns.filter((k) => /^(g_|a_|bldg_street_)/.test(k));
  for (const [ci, f] of frac) for (const k of scaleCols) col(after, k)[ci] *= 1 - f;
  const PUBLIC: Record<string, number[]> = { base: [1, 4], pops: [1, 4, 6] };
  const PRIVATE: Record<string, number[]> = { base: [3, 5, 6], pops: [3, 5] };
  for (const variant of ['base', 'pops']) {
    for (const r of prm.raster.multiscale_m as number[]) {
      const f = Math.round(r / res);
      const { c: cc, l: ll, w: ww, h: hh } = coarsen(cls, cellOf, W, H, f);
      const add = (k: string, ci: number, v = 1) => { if (ci >= 0) col(after, `g_${variant}_${r}_${k}`)[ci] += v; };
      const isP = (v: number) => PUBLIC[variant].includes(v), isQ = (v: number) => PRIVATE[variant].includes(v);
      for (let y = 0; y < hh; y++) for (let x = 0; x < ww; x++) {
        const k = y * ww + x, v = cc[k], ci = ll[k];
        if (!v || ci < 0) continue;
        if (isP(v)) add('nP', ci); else if (isQ(v)) add('nQ', ci); else if (v === 2) add('nV', ci);
        for (const k2 of [x + 1 < ww ? k + 1 : -1, y + 1 < hh ? k + ww : -1]) {
          if (k2 < 0 || !cc[k2]) continue;
          const a = cc[k], b = cc[k2];
          if (isP(a) && isP(b)) add('PP', ci); else if ((isP(a) && isQ(b)) || (isQ(a) && isP(b))) add('PQ', ci); else if (isQ(a) && isQ(b)) add('QQ', ci);
        }
      }
    }
  }
  const px = res * res;
  const codeName: Record<number, string> = { 1: 'open_free', 2: 'roadway', 3: 'private', 4: 'sidewalk', 5: 'open_cond', 6: 'pops' };
  for (let k = 0; k < cls.length; k++) {
    const ci = cellOf[k], v = cls[k];
    if (ci < 0 || !v) continue;
    col(after, `a_${codeName[v]}_m2`)[ci] += px;
    if ((v === 1 || v === 6) && spaceOf[k] >= 0) col(after, `a_${codeName[v]}_green_m2`)[ci] += px * osFeats[spaceOf[k]].properties.green_ratio;
  }
  for (const [i, f] of byLayer('building').entries()) {
    const p = bl[i];
    const a = p.reduce((s, q) => s + polyArea(q), 0);
    const [cx, cy] = centroid(p[0][0]);
    const [lo, la] = L.ll(cx, cy);
    const ci = h3Index.get(latLngToCell(la, lo, 10));
    if (ci === undefined) continue;
    col(after, 'bldg_street_a_m2')[ci] += a;
    col(after, 'bldg_street_ha_m3')[ci] += a * f.properties.height_m;
  }
  // 인구: units·jobs가 있는 건물이 하나라도 있으면 대상지 몫을 설계안 값으로 바꾼다
  const ppu: number = prm.design?.persons_per_unit ?? NaN;
  const hasUnits = byLayer('building').some((f) => f.properties.units != null);
  const hasJobs = byLayer('building').some((f) => f.properties.jobs != null);
  if (hasUnits) for (const [ci, f] of frac) col(after, 'pop_night')[ci] *= 1 - f;
  if (hasJobs) for (const [ci, f] of frac) col(after, 'pop_day')[ci] *= 1 - f;
  byLayer('building').forEach((f, i) => {
    const [cx, cy] = centroid(bl[i][0][0]);
    const [lo, la] = L.ll(cx, cy);
    const ci = h3Index.get(latLngToCell(la, lo, 10));
    if (ci === undefined) return;
    if (hasUnits && f.properties.units != null && Number.isFinite(ppu)) col(after, 'pop_night')[ci] += f.properties.units * ppu;
    if (hasJobs && f.properties.jobs != null) col(after, 'pop_day')[ci] += f.properties.jobs;
  });
  if (hasUnits && !Number.isFinite(ppu)) warnings.push('params.design.persons_per_unit가 없어 units를 인구로 바꾸지 못했습니다.');
  // 최대 패치: 대상지 안 열린 공간 패치 (대상지 밖과 이어지는지는 모름 → 기존 값과 큰 쪽)
  for (const variant of ['base', 'pops']) {
    const codes = variant === 'pops' ? [1, 6] : [1];
    const areas = patches(cls, W, H, codes);
    const pc = col(after, `patch_${variant}_max_m2`);
    for (const [ci, f] of frac) if (f >= 0.999) pc[ci] = 0;
    for (let k = 0; k < cls.length; k++) if (areas.id[k] > 0 && cellOf[k] >= 0) pc[cellOf[k]] = Math.max(pc[cellOf[k]], areas.area[areas.id[k]] * px);
  }

  // ---- 3. 보행망 수정: ped_link 추가, barrier가 끊는 링크 제거
  const mod: NetMod = { extra: new Map(), blocked: new Set(), extraNodes: 0 };
  const net = S.net;
  const nodeXY = (i: number) => L.xy(net.lon[i], net.lat[i]);
  const near = (x: number, y: number, maxd: number) => {
    let best = -1, bd = maxd;
    for (let i = 0; i < net.n; i++) { const [nx, ny] = nodeXY(i); const d = Math.hypot(nx - x, ny - y); if (d < bd) { bd = d; best = i; } }
    return [best, bd] as const;
  };
  const addEdge = (a: number, b: number, w: number) => {
    for (const [u, v] of [[a, b], [b, a]]) { const l = mod.extra.get(u) ?? []; l.push([v, w]); mod.extra.set(u, l); }
  };
  for (const f of byLayer('ped_link')) for (const ln of lines(f.geometry, L)) {
    const [a, da] = near(ln[0][0], ln[0][1], 120);
    const [b, db] = near(ln[ln.length - 1][0], ln[ln.length - 1][1], 120);
    if (a < 0 || b < 0) { warnings.push('ped_link 끝점 120 m 안에 보행 노드가 없어 연결하지 못한 링크가 있습니다.'); continue; }
    addEdge(a, b, lineLen(ln) + da + db);
  }
  for (const f of byLayer('barrier')) for (const ln of lines(f.geometry, L)) {
    const [lx0, ly0, lx1, ly1] = [Math.min(...ln.map((p) => p[0])) - 1, Math.min(...ln.map((p) => p[1])) - 1, Math.max(...ln.map((p) => p[0])) + 1, Math.max(...ln.map((p) => p[1])) + 1];
    for (let u = 0; u < net.n; u++) {
      const pu = nodeXY(u);
      for (let e = net.indptr[u]; e < net.indptr[u + 1]; e++) {
        const v = net.indices[e];
        if (v < u) continue;
        const pv = nodeXY(v);
        if (Math.max(pu[0], pv[0]) < lx0 || Math.min(pu[0], pv[0]) > lx1 || Math.max(pu[1], pv[1]) < ly0 || Math.min(pu[1], pv[1]) > ly1) continue;
        for (let s = 1; s < ln.length; s++) if (segX(pu, pv, ln[s - 1], ln[s])) { mod.blocked.add(edgeKey(u, v)); break; }
      }
    }
  }

  // ---- 4. 공간 교체: 대표점이 대상지 안인 기존 공간은 빼고 설계안 공간을 넣는다
  const os = prm.open_space;
  const kept = S.spaces.filter((s) => { const [x, y] = L.xy(s.pt[0], s.pt[1]); return !inB(x, y); });
  const added: SpaceRec[] = osFeats.map((f, i) => {
    const p = f.properties;
    const area = osPolys[i].reduce((s, q) => s + polyArea(q), 0);
    const free = p.access === 'free' && p.kind !== 'pops';
    const defs: string[] = [];
    if (free && os.green_kinds.includes(p.kind) && p.green_ratio >= os.green_only_min_green_ratio) defs.push('green_only');
    if (free || p.kind === 'schoolyard') defs.push('with_plaza_playground');
    if (free || p.kind === 'schoolyard' || p.kind === 'pops') defs.push('with_pops');
    const ents = byLayer('entrance').filter((e) => String(e.properties.serves) === String(p.id))
      .map((e) => near(...L.xy(e.geometry.coordinates[0], e.geometry.coordinates[1]), 1e9)[0]);
    const entrances = ents.length ? ents : boundaryEntrances(osPolys[i], nodeXY, net.n, os.entrance.boundary_spacing_m, os.entrance.snap_max_m);
    const [cx, cy] = centroid(osPolys[i][0][0]);
    return { id: `design_${p.id ?? i}`, kind: p.kind, access: p.access, area_m2: area, defs, entrances: [...new Set(entrances)], pt: L.ll(cx, cy), green_ratio: p.green_ratio };
  }).filter((s) => s.area_m2 >= os.min_area_m2);
  const newSpaces = [...kept, ...added];

  // ---- 5. 접근성: 대상지+버퍼 셀만 다시 계산 (전후 모두 같은 TS 엔진으로)
  const buf: number = prm.region.boundary_buffer_m;
  const siteR = Math.hypot(x1 - x0, y1 - y0) / 2;
  const affected: number[] = [];
  const node = col(S.cells, 'node');
  for (let i = 0; i < S.cells.n; i++) {
    if (node[i] < 0) continue;
    const [la, lo] = cellToLatLng(cellsH3[i]);
    const [x, y] = L.xy(lo, la);
    if (Math.hypot(x, y) <= siteR + buf) affected.push(i);
  }
  const extra = Math.max(...prm.access.cover_minutes) * 60 * prm.walk.speed_mps;
  const relevant = (sp: SpaceRec) => { const [x, y] = L.xy(sp.pt[0], sp.pt[1]); return Math.hypot(x, y) <= maxReach(sp.area_m2, prm.access, extra) + siteR + buf; };
  const before = cloneCells(S.cells);
  const recompute = (spaces: SpaceRec[], cells: Cells, m?: NetMod) => {
    const sp = spaces.filter(relevant);
    const dists = sp.map((s) => spaceCellDist(net, s, node, prm.access, extra, m));
    const cols = accessColumns(affected, sp, dists, col(cells, 'pop_night'), col(cells, 'pop_day'), S.meta);
    for (const [k, v] of cols) { const c = col(cells, k); affected.forEach((ci, t) => { c[ci] = v[t]; }); }
  };
  recompute(S.spaces, before);
  recompute(newSpaces, after, mod);

  const siteIdx = [...site.keys()];
  const fr = byLayer('frontage').map((f) => ({ f, len: lines(f.geometry, L).reduce((s, l) => s + lineLen(l), 0) }));
  const frontage = fr.length ? fr.reduce((s, x) => s + x.f.properties.doors_per_100m * x.len, 0) / fr.reduce((s, x) => s + x.len, 0) : null;
  const agg = (c: Cells, idx: number[]) => aggregate(idx, c, S.poiRows, lens, S.meta);
  const a1 = agg(after, siteIdx);
  a1.frontage_permeability = frontage;
  const geo = {
    type: 'FeatureCollection',
    features: [
      ...feats.map((f) => ({ ...f, properties: { ...f.properties, role: f.properties.layer } })),
      ...siteIdx.map((ci) => ({ type: 'Feature', properties: { role: 'cell' }, geometry: { type: 'Polygon', coordinates: [cellToBoundary(cellsH3[ci], true)] } })),
    ],
  };
  if (mod.blocked.size) warnings.push(`barrier가 보행 링크 ${mod.blocked.size}개를 끊었습니다.`);
  if (added.length < osFeats.length) warnings.push(`최소 면적(${os.min_area_m2} m²)보다 작은 open_space ${osFeats.length - added.length}개는 공간으로 세지 않았습니다.`);
  return {
    errors: [], warnings, before: agg(before, siteIdx), after: a1, beforeBuffer: agg(before, affected), afterBuffer: agg(after, affected),
    siteCells: siteIdx.length, bufferCells: affected.length, geo, bounds: [bw, bs, be, bn],
  };
}

function centroid(r: Ring): [number, number] {
  let x = 0, y = 0;
  for (const p of r) { x += p[0]; y += p[1]; }
  return [x / r.length, y / r.length];
}

function boundaryEntrances(ps: Poly[], nodeXY: (i: number) => [number, number], n: number, spacing: number, snap: number): number[] {
  const out = new Set<number>();
  for (const p of ps) {
    const r = p[0];
    const len = lineLen([...r, r[0]]);
    const k = Math.max(1, Math.floor(len / spacing));
    const pts: [number, number][] = [];
    for (let t = 0; t < k; t++) pts.push(along([...r, r[0]], (t * len) / k));
    for (const [x, y] of pts) {
      let best = -1, bd = snap;
      for (let i = 0; i < n; i++) { const [nx, ny] = nodeXY(i); const d = Math.hypot(nx - x, ny - y); if (d < bd) { bd = d; best = i; } }
      if (best >= 0) out.add(best);
    }
  }
  if (!out.size) {
    const [cx, cy] = centroid(ps[0][0]);
    let best = 0, bd = Infinity;
    for (let i = 0; i < n; i++) { const [nx, ny] = nodeXY(i); const d = Math.hypot(nx - cx, ny - cy); if (d < bd) { bd = d; best = i; } }
    out.add(best);
  }
  return [...out];
}

function along(r: Ring, t: number): [number, number] {
  for (let i = 1; i < r.length; i++) {
    const s = Math.hypot(r[i][0] - r[i - 1][0], r[i][1] - r[i - 1][1]);
    if (t <= s) { const u = s ? t / s : 0; return [r[i - 1][0] + u * (r[i][0] - r[i - 1][0]), r[i - 1][1] + u * (r[i][1] - r[i - 1][1])]; }
    t -= s;
  }
  return r[r.length - 1];
}

/** f×f 최빈값 (동점이면 왼쪽 위) — Python raster.coarsen_mode와 같은 규칙. 래스터는 아래(남)→위 행 순서. */
function coarsen(cls: Uint8Array, lbl: Int32Array, W: number, H: number, f: number) {
  if (f === 1) return { c: cls, l: lbl, w: W, h: H };
  const w = Math.floor(W / f), h = Math.floor(H / f);
  const c = new Uint8Array(w * h), l = new Int32Array(w * h).fill(-1);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const cnt = new Map<number, number>(), lc = new Map<number, number>();
    const tl = cls[(y * f + f - 1) * W + x * f]; // 북쪽 위 행의 서쪽 픽셀 = 왼쪽 위
    const tll = lbl[(y * f + f - 1) * W + x * f];
    for (let dy = 0; dy < f; dy++) for (let dx = 0; dx < f; dx++) {
      const k = (y * f + dy) * W + x * f + dx;
      cnt.set(cls[k], (cnt.get(cls[k]) ?? 0) + 1);
      lc.set(lbl[k], (lc.get(lbl[k]) ?? 0) + 1);
    }
    const pick = (m: Map<number, number>, top: number) => { const best = Math.max(...m.values()); return m.get(top) === best ? top : [...m.entries()].find(([, n]) => n === best)![0]; };
    c[y * w + x] = pick(cnt, tl);
    l[y * w + x] = pick(lc, tll);
  }
  return { c, l, w, h };
}

/** 4-연결 패치 번호와 픽셀 수. */
function patches(cls: Uint8Array, W: number, H: number, codes: number[]) {
  const id = new Int32Array(W * H);
  const area: number[] = [0];
  let n = 0;
  for (let k = 0; k < cls.length; k++) {
    if (id[k] || !codes.includes(cls[k])) continue;
    n++;
    let cnt = 0;
    const stack = [k];
    id[k] = n;
    while (stack.length) {
      const q = stack.pop()!;
      cnt++;
      const x = q % W, y = (q - x) / W;
      for (const r of [x > 0 ? q - 1 : -1, x < W - 1 ? q + 1 : -1, y > 0 ? q - W : -1, y < H - 1 ? q + W : -1]) {
        if (r >= 0 && !id[r] && codes.includes(cls[r])) { id[r] = n; stack.push(r); }
      }
    }
    area.push(cnt);
  }
  return { id, area };
}
