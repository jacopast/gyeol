// 웹 워커: 데이터를 들고 다익스트라·집계를 한다 (SPEC 9.8)
import { aggregate, cellValues, Cells, type Lens, type Meta, Network, walkshedCells } from './engine';
import { designRecompute, type DesignResult } from './design';

interface State {
  meta: Meta;
  net: Network;
  cells: Cells;
  poiRows: number[][];
  spaces: any[];
  target: number[];
  base: string;
  h3: string[];
}
let S: State | null = null;

async function load(base: string, region: string) {
  const dir = `${base}data/regions/${region}/`;
  const [meta, net, cells, pois, spaces, h3] = await Promise.all([
    fetch(dir + 'meta.json').then((r) => r.json()),
    fetch(dir + 'network.bin').then((r) => r.arrayBuffer()),
    fetch(dir + 'cells.bin').then((r) => r.arrayBuffer()),
    fetch(dir + 'pois.json').then((r) => r.json()),
    fetch(dir + 'spaces.json').then((r) => r.json()),
    fetch(dir + 'cells_h3.json').then((r) => r.json()),
  ]);
  const m = meta as Meta;
  const c = new Cells(cells, m.columns, m.n_cells);
  const it = c.col('in_target')!;
  const node = c.col('node')!;
  const target: number[] = [];
  for (let i = 0; i < m.n_cells; i++) if (it[i] > 0 && node[i] >= 0) target.push(i);
  S = { meta: m, net: new Network(net, m.network.n_nodes, m.network.n_entries), cells: c, poiRows: pois.rows, spaces, target, base, h3 };
  return { meta: m, target };
}

function sample(lon: number, lat: number, lens: Lens, minutes: number[]) {
  const s = S!;
  const start = s.net.nearest(lon, lat);
  const out: Record<number, { cells: number[]; metrics: any }> = {};
  for (const mins of minutes) {
    const idx = walkshedCells(s.net, s.cells.col('node')!, start, mins, s.meta.params.walk.speed_mps);
    out[mins] = { cells: idx, metrics: aggregate(idx, s.cells, s.poiRows, lens, s.meta) };
  }
  return { start, point: [s.net.lon[start], s.net.lat[start]], results: out };
}

self.onmessage = async (ev: MessageEvent) => {
  const { id, op, args } = ev.data;
  try {
    let result: any;
    if (op === 'load') result = await load(args.base, args.region);
    else if (op === 'cellValues') {
      const v = cellValues(args.metric, S!.cells, S!.poiRows, args.lens, S!.meta, S!.target);
      result = v;
    } else if (op === 'sample') result = sample(args.lon, args.lat, args.lens, args.minutes);
    else if (op === 'design') result = designRecompute(S!, args.fc, args.lens) as DesignResult;
    else throw new Error(`unknown op ${op}`);
    (self as any).postMessage({ id, result });
  } catch (e) {
    (self as any).postMessage({ id, error: String((e as Error)?.message ?? e) });
  }
};
