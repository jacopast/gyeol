// 브라우저 접근성 재계산이 Python 셀 값과 같은지 (설계안 재계산의 기준선)
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { accessColumns, type SpaceRec, spaceCellDist } from '../src/access';
import { Cells, type Meta, Network } from '../src/engine';

const dir = resolve(__dirname, '../public/data/regions/manhattan');
const buf = (f: string) => { const b = readFileSync(resolve(dir, f)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const meta: Meta = JSON.parse(readFileSync(resolve(dir, 'meta.json'), 'utf8'));
const spaces: SpaceRec[] = JSON.parse(readFileSync(resolve(dir, 'spaces.json'), 'utf8'));
const net = new Network(buf('network.bin'), meta.network.n_nodes, meta.network.n_entries);
const cells = new Cells(buf('cells.bin'), meta.columns, meta.n_cells);

describe('access port matches Python cell metrics', () => {
  it('all lenses for 25 random target cells within 0.5%', () => {
    const node = cells.col('node')!;
    const it_ = cells.col('in_target')!;
    const cand: number[] = [];
    for (let i = 0; i < meta.n_cells; i++) if (it_[i] > 0 && node[i] >= 0) cand.push(i);
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    const targets = Array.from({ length: 25 }, () => cand[Math.floor(rnd() * cand.length)]);
    const extra = Math.max(...meta.params.access.cover_minutes) * 60 * meta.params.walk.speed_mps;
    const dists = spaces.map((s) => spaceCellDist(net, s, node, meta.params.access, extra));
    const cols = accessColumns(targets, spaces, dists, cells.col('pop_night')!, cells.col('pop_day')!, meta);
    const bad: string[] = [];
    for (const [k, v] of cols) {
      const ref = cells.col(k)!;
      targets.forEach((c, t) => {
        const r = ref[c];
        if (Math.abs(v[t] - r) > 0.005 * Math.max(Math.abs(r), 1e-6) && Math.abs(v[t] - r) > 1e-6) bad.push(`${k} cell ${c}: ts ${v[t]} py ${r}`);
      });
    }
    expect(bad.slice(0, 10)).toEqual([]);
  }, 60000);
});
