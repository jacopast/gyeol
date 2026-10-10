import { describe, expect, it } from 'vitest';
import { importLabelCSV, parseCSV } from '../src/labels';
import type { Sample } from '../src/library';

const mk = (id: string, point: [number, number]) => ({ id, point, labels: {}, metrics: {}, context: {} }) as unknown as Sample;

describe('label CSV', () => {
  it('parses quoted CSV', () => {
    expect(parseCSV('a,b\n"x, y",2\n')).toEqual([['a', 'b'], ['x, y', '2']]);
  });
  it('attaches by id and by nearest coordinate', () => {
    const lib = [mk('s_1', [-73.98, 40.75]), mk('s_2', [-73.95, 40.78])];
    const msg = importLabelCSV('sample_id,count\ns_1,12\n', lib);
    expect(lib[0].labels.csv_count).toBe(12);
    expect(msg).toContain('1줄');
    importLabelCSV('lon,lat,stay rate\n-73.9501,40.7801,0.4\n-70,40,1\n', lib);
    expect(lib[1].labels.csv_stay_rate).toBe(0.4);
  });
  it('turns pairwise comparisons into win rates', () => {
    const lib = [mk('a', [0, 0]), mk('b', [0, 0])];
    importLabelCSV('sample_a,sample_b,question,winner\na,b,safety,a\na,b,safety,tie\n', lib);
    expect(lib[0].labels.pairwise_safety).toBe(0.75);
    expect(lib[1].labels.pairwise_safety).toBe(0.25);
  });
});
