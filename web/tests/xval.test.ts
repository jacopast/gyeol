// 교차 검증 (SPEC 9.8): 무작위 20지점에서 웹 계산이 Python 기준 구현과 허용 오차 안에서 일치해야 한다.
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { aggregate, Cells, type Meta, Network, walkshedCells } from '../src/engine';

const dir = resolve(__dirname, '../public/data/regions/manhattan');
const buf = (f: string) => { const b = readFileSync(resolve(dir, f)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const meta: Meta = JSON.parse(readFileSync(resolve(dir, 'meta.json'), 'utf8'));
const xval = JSON.parse(readFileSync(resolve(dir, 'xval.json'), 'utf8'));
const pois = JSON.parse(readFileSync(resolve(dir, 'pois.json'), 'utf8'));
const net = new Network(buf('network.bin'), meta.network.n_nodes, meta.network.n_entries);
const cells = new Cells(buf('cells.bin'), meta.columns, meta.n_cells);

function close(a: unknown, b: unknown, tol: number): boolean {
  if (a === null || b === null) return a === b;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => close(x, b[i], tol));
  const x = a as number, y = b as number;
  return Math.abs(x - y) <= tol * Math.max(Math.abs(y), 1e-9) || Math.abs(x - y) < 1e-9;
}

describe('cross-validation vs Python reference', () => {
  it(`has ${xval.points.length} walksheds (20 points × 5·10 min)`, () => {
    expect(xval.points.length).toBe(40);
  });
  for (const [k, p] of xval.points.entries()) {
    it(`point ${k}: start ${p.start_node}, ${p.minutes} min`, () => {
      const idx = walkshedCells(net, cells.col('node')!, p.start_node, p.minutes, meta.params.walk.speed_mps);
      expect(idx).toEqual(p.cells);
      const m = aggregate(idx, cells, pois.rows, xval.lens, meta);
      const bad = Object.keys(p.metrics).filter((key) => !close(m[key], p.metrics[key], xval.tolerance));
      expect(bad.map((key) => `${key}: web ${JSON.stringify(m[key])} py ${JSON.stringify(p.metrics[key])}`)).toEqual([]);
    });
  }
});
