import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { designRecompute, validateDesign } from '../src/design';
import { aggregate, Cells, type Meta, Network, walkshedCells } from '../src/engine';

const dir = resolve(__dirname, '../public/data/regions/manhattan');
const buf = (f: string) => { const b = readFileSync(resolve(dir, f)); return b.buffer.slice(b.byteOffset, b.byteOffset + b.byteLength); };
const meta: Meta = JSON.parse(readFileSync(resolve(dir, 'meta.json'), 'utf8'));
const example = JSON.parse(readFileSync(resolve(__dirname, '../../templates/design_template.geojson'), 'utf8'));

describe('design validation', () => {
  it('accepts the template', () => {
    expect(validateDesign(example, meta).errors).toEqual([]);
  });
  it('reports missing attributes line by line', () => {
    const bad = {
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', properties: { layer: 'open_space', kind: 'park' }, geometry: { type: 'Polygon', coordinates: [[[-73.99, 40.76], [-73.989, 40.76], [-73.989, 40.761], [-73.99, 40.76]]] } },
        { type: 'Feature', properties: { layer: 'roadway', lanes: 2 }, geometry: { type: 'Point', coordinates: [-73.99, 40.76] } },
        { type: 'Feature', properties: { layer: 'entrance', serves: 'nope' }, geometry: { type: 'Point', coordinates: [-73.99, 40.76] } },
        { type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [-73.99, 40.76] } },
      ],
    };
    const e = validateDesign(bad, meta).errors;
    expect(e).toContain('피처 1 (open_space): access 없음 또는 잘못됨 (free / conditional / restricted)');
    expect(e).toContain('피처 1 (open_space): green_ratio 없음 또는 범위 밖 (0~1 숫자)');
    expect(e.some((x) => x.startsWith('피처 2 (roadway): 도형은'))).toBe(true);
    expect(e).toContain('피처 3 (entrance): serves "nope"와 같은 id의 open_space가 없음');
    expect(e.some((x) => x.startsWith('피처 4: layer 속성 없음'))).toBe(true);
    expect(e).toContain('boundary 피처가 정확히 1개여야 함 (지금 0개)');
  });
});

describe('design recompute on the example', () => {
  it('recomputes site and buffer, pocket park raises public share', () => {
    const S = {
      meta,
      net: new Network(buf('network.bin'), meta.network.n_nodes, meta.network.n_entries),
      cells: new Cells(buf('cells.bin'), meta.columns, meta.n_cells),
      poiRows: JSON.parse(readFileSync(resolve(dir, 'pois.json'), 'utf8')).rows,
      spaces: JSON.parse(readFileSync(resolve(dir, 'spaces.json'), 'utf8')),
      target: [],
      h3: JSON.parse(readFileSync(resolve(dir, 'cells_h3.json'), 'utf8')),
    };
    const lens = { definition: 'with_plaza_playground', decay: 'gaussian', alpha: 1, beta: 0.25 };
    const r = designRecompute(S as any, example, lens);
    expect(r.errors).toEqual([]);
    expect(r.siteCells).toBeGreaterThan(0);
    expect(r.bufferCells).toBeGreaterThan(r.siteCells!);
    expect(r.after!.nolli_ratio as number).toBeGreaterThan(r.before!.nolli_ratio as number);
    // 기존 공간은 설계안에서 다시 그려지며 출입구를 경계 샘플로 새로 찾으므로 아주 작은 차이가 날 수 있다
    expect(Math.abs((r.after!.os_gravity as number) / (r.before!.os_gravity as number) - 1)).toBeLessThan(0.01);
    expect(r.after!.lane_share as number).toBeLessThan(r.before!.lane_share as number);
    expect(r.after!.frontage_permeability).toBe(8);
    // Peer comparisons must use actual network walksheds, never the site polygon.
    const cmp = r.comparison!;
    const start = S.net.nearest(...cmp.point);
    for (const minutes of [5, 10]) {
      const w = cmp.results[minutes];
      const expected = walkshedCells(S.net, S.cells.col('node')!, start, minutes, meta.params.walk.speed_mps);
      expect(w.beforeCells).toEqual(expected);
      expect(w.afterCells.length).toBeGreaterThan(r.siteCells!);
      const baseline = aggregate(expected, S.cells, S.poiRows, lens, meta);
      expect(w.before.nolli_ratio).toBe(baseline.nolli_ratio);
      expect(Math.abs((w.before.os_gravity as number) / (baseline.os_gravity as number) - 1)).toBeLessThan(0.005);
      expect(Object.keys(w.after).some((k) => k.startsWith('places_'))).toBe(false);
    }
    console.log(JSON.stringify({ site: r.siteCells, buf: r.bufferCells, warnings: r.warnings,
      before: { nolli: r.before!.nolli_ratio, grav: r.before!.os_gravity, lane: r.before!.lane_share, sw: r.before!.sidewalk_width },
      after: { nolli: r.after!.nolli_ratio, grav: r.after!.os_gravity, lane: r.after!.lane_share, sw: r.after!.sidewalk_width } }));
  }, 60000);
});
