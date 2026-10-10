import { describe, expect, it } from 'vitest';
import { nextId, parsePeerFilter, passesPeer, splitMetrics, type Sample } from '../src/library';
import { quantileBreaks } from '../src/charts';

describe('library', () => {
  it('numbers sample ids per day', () => {
    const lib = [{ id: 's_20261010_001' }, { id: 's_20261010_007' }] as Sample[];
    expect(nextId(lib, new Date('2026-10-10T12:00:00Z'))).toBe('s_20261010_008');
    expect(nextId([], new Date('2026-10-11T12:00:00Z'))).toBe('s_20261011_001');
  });
  it('splits metrics into 9.5 structure', () => {
    const p = splitMetrics({ os_gravity: 1, ctx_density: 2, places_obesity: 3 });
    expect(p.metrics).toEqual({ os_gravity: 1 });
    expect(p.context).toEqual({ ctx_density: 2 });
    expect(p.labels).toEqual({ places_obesity: 3 });
  });
  it('parses and applies peer filters', () => {
    const r = parsePeerFilter('ctx_density 100 400\nctx_income 50000-90000');
    expect(r).toEqual([{ key: 'ctx_density', lo: 100, hi: 400 }, { key: 'ctx_income', lo: 50000, hi: 90000 }]);
    const s = { context: { ctx_density: 200, ctx_income: 60000 }, metrics: {}, labels: {} } as unknown as Sample;
    expect(passesPeer(s, r)).toBe(true);
    expect(passesPeer({ ...s, context: { ctx_density: 50 } } as unknown as Sample, r)).toBe(false);
  });
  it('quantile breaks', () => {
    expect(quantileBreaks([1, 2, 3, 4, 5, 6], 3)).toEqual([3, 5]);
  });
});
