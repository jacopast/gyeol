import { describe, expect, it } from 'vitest';
import { comparisonMismatch, type ComparisonBasis } from '../src/comparison';

const basis: ComparisonBasis = {
  region: 'manhattan', params_hash: 'run-a', walk_minutes: 10,
  lens: { definition: 'with_plaza_playground', decay: 'gaussian', alpha: 1, beta: 0.25 },
};

describe('compatible peer measurements', () => {
  it('accepts the same protocol even with differently ordered lens keys', () => {
    expect(comparisonMismatch({ ...basis, lens: { beta: 0.25, alpha: 1, decay: 'gaussian', definition: 'with_plaza_playground' } }, basis)).toBeNull();
  });
  it.each([
    { region: 'seongdong' }, { params_hash: 'run-b' }, { walk_minutes: 5 },
    ...['definition', 'decay', 'alpha', 'beta'].map((key) => ({ lens: { ...basis.lens, [key]: 'different' } })),
    { lens: undefined }, { walk_minutes: undefined }, { params_hash: undefined },
  ])('excludes incompatible or legacy measurements: %j', (change) => {
    expect(comparisonMismatch({ ...basis, ...change }, basis)).not.toBeNull();
  });
});

import { stripChart } from '../src/charts';
import { METRICS } from '../src/metrics';
it('does not invent a 105% endpoint when all coverage measurements equal 100%', () => {
  const def = METRICS.find((m) => m.id === 'os_cover_10')!;
  const html = stripChart(def, [{ v: 1, name: 'same' }], 1, { width: 'm' }, false);
  expect(html).not.toContain('105%');
  expect(html).toContain('cx="50%"');
  expect(html).not.toContain('NaN');
});
