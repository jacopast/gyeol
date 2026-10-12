import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';
import { renderLab, type LabState } from '../src/lab';

const data = JSON.parse(readFileSync(resolve(__dirname, '../public/data/scenarios/scenarios.json'), 'utf8'));
const state: LabState = { data, alpha: 1, beta: 0.25, congestion: true, opportunity_cost: true, barrier: false };

it('explains the population condition and disables alpha when congestion replaces gravity', () => {
  const html = renderLab(state);
  expect(html).toContain('α를 적용하지 않습니다');
  expect(html).toContain('평균도 달라질 수 있습니다');
  expect(html.match(/data-lab="alpha"[^>]*disabled/g)).toHaveLength(4);
  expect(html).not.toContain('공원에서 가장 먼 주민');
});

it('shows coverage as an actual percent, not a row-normalized score', () => {
  const html = renderLab({ ...state, congestion: false, opportunity_cost: false });
  expect(html).toMatch(/>30%<div class="bar"/);
  expect(html).toContain('실제 주민 비율(%)');
  expect(html).not.toMatch(/data-lab="alpha"[^>]*disabled/);
});
