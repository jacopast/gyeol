// 접근성 수식 — pipeline/gyeol/metrics/access.py 의 TypeScript 판 (설계안 재계산용)
import { type Cells, lensKey, type Meta, type Network, type NetMod } from './engine';

const EXP_HALF = Math.exp(-0.5);

export interface SpaceRec {
  id: string;
  kind: string;
  access: string;
  area_m2: number;
  defs: string[];
  entrances: number[];
  pt: [number, number];
  name?: string | null;
  green_ratio?: number | null;
}

export function radius(S: number, beta: number, a: any): number {
  const R = a.r0_m * Math.pow(Math.max(S, 1e-9) / a.s0_m2, beta);
  return Math.min(Math.max(R, a.r_min_m), a.r_max_m);
}

export function decay(d: number, R: number, kind: string, a: any): number {
  if (kind === 'gaussian') return d <= R ? (Math.exp(-0.5 * (d / R) ** 2) - EXP_HALF) / (1 - EXP_HALF) : 0;
  const scale = R / a.r0_m;
  return d <= a.step_inner_m * scale ? 1 : d <= a.step_outer_m * scale ? a.step_mid : 0;
}

export function maxReach(S: number, a: any, extra: number): number {
  const betas: number[] = a.betas;
  const R = radius(S, Math.max(...betas), a);
  return Math.max(R, (a.step_outer_m * R) / a.r0_m, extra);
}

/** 공간 하나에서 모든 셀까지 거리 (셀 인덱스 → 거리). */
export function spaceCellDist(net: Network, sp: SpaceRec, cellNode: Float32Array, a: any, extra: number, mod?: NetMod): Map<number, number> {
  const lim = maxReach(sp.area_m2, a, extra);
  const d = net.dijkstra(sp.entrances, lim, mod);
  const out = new Map<number, number>();
  for (let i = 0; i < cellNode.length; i++) {
    const nd = cellNode[i];
    if (nd >= 0 && Number.isFinite(d[nd])) out.set(i, d[nd]);
  }
  return out;
}

/**
 * 주어진 셀들(targets)의 접근성 렌즈 전부를 다시 계산한다. dists[j] = 공간 j에서 셀까지 거리 (모든 셀).
 * 2SFCA 수요는 모든 셀의 인구로 계산한다 (Python과 같음).
 */
export function accessColumns(targets: number[], spaces: SpaceRec[], dists: Map<number, number>[], popNight: Float32Array, popDay: Float32Array, meta: Meta): Map<string, Float64Array> {
  const prm = meta.params;
  const a = prm.access;
  const out = new Map<string, Float64Array>();
  const tIndex = new Map(targets.map((c, k) => [c, k]));
  const defs: string[] = prm.open_space.definitions;
  const speed = prm.walk.speed_mps;
  const P: Record<string, Float32Array> = { night: popNight, day: popDay };
  const val = (x: number) => (Number.isFinite(x) ? x : 0);
  for (const d of defs) {
    const js = spaces.map((s, j) => (s.defs.includes(d) ? j : -1)).filter((j) => j >= 0);
    for (const dec of a.decays as string[]) {
      for (const beta of a.betas as number[]) {
        const R = js.map((j) => radius(spaces[j].area_m2, beta, a));
        for (const alpha of a.alphas as number[]) {
          const g = new Float64Array(targets.length);
          js.forEach((j, k) => {
            const w = Math.pow(spaces[j].area_m2, alpha);
            for (const [c, dist] of dists[j]) { const t = tIndex.get(c); if (t !== undefined) g[t] += w * decay(dist, R[k], dec, a); }
          });
          out.set(lensKey('os_gravity', d, dec, alpha, beta), g);
        }
        for (const dem of a.demand as string[]) {
          const pop = P[dem];
          const g = new Float64Array(targets.length);
          js.forEach((j, k) => {
            let demand = 0;
            for (const [c, dist] of dists[j]) demand += val(pop[c]) * decay(dist, R[k], dec, a);
            const ratio = demand > 0 ? spaces[j].area_m2 / demand : 0;
            if (!ratio) return;
            for (const [c, dist] of dists[j]) { const t = tIndex.get(c); if (t !== undefined) g[t] += ratio * decay(dist, R[k], dec, a); }
          });
          out.set(lensKey('os_g2sfca', d, dec, null, beta, dem), g);
        }
      }
    }
    for (const m of a.cover_minutes as number[]) {
      const lim = m * 60 * speed;
      const g = new Float64Array(targets.length);
      for (const j of js) {
        if (spaces[j].area_m2 < prm.open_space.min_area_m2) continue;
        for (const [c, dist] of dists[j]) { const t = tIndex.get(c); if (t !== undefined && dist <= lim) g[t] = 1; }
      }
      out.set(lensKey(`os_cover_${m}`, d), g);
    }
  }
  return out;
}

/** 셀 열을 복제해 일부만 바꾼 새 Cells. */
export function cloneCells(cells: Cells): Cells {
  const c = Object.create(Object.getPrototypeOf(cells)) as Cells;
  c.n = cells.n;
  c.cols = new Map();
  for (const [k, v] of cells.cols) c.cols.set(k, new Float32Array(v));
  return c;
}
