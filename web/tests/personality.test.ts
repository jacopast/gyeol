// 웹의 유형 거리 계산이 Python k-평균 배정과 맞는지 (시연 표본에서 가장 가까운 중심 = 배정된 유형)
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { type PersonalityModel, typeDistances } from '../src/personalityui';

const dir = resolve(__dirname, '../public/data/regions/manhattan');
const model: PersonalityModel = JSON.parse(readFileSync(resolve(dir, 'personality.json'), 'utf8'));
const demo = JSON.parse(readFileSync(resolve(dir, 'demo_library.json'), 'utf8')).samples;

describe('personality', () => {
  it('has at least 30 stratified demo samples', () => {
    expect(demo.length).toBeGreaterThanOrEqual(30);
  });
  it('nearest center in the web equals the Python assignment', () => {
    for (const s of demo) {
      const d = typeDistances(model, s.metrics);
      if (s.type === null) { expect(d).toBeNull(); continue; }
      const nearest = Object.entries(d!).sort((a, b) => a[1] - b[1])[0][0];
      expect(nearest).toBe(s.type);
    }
  });
  it('type names carry no evaluative words', () => {
    for (const t of Object.keys(model.profiles)) expect(t).toMatch(/^[A-Z]$/);
  });
});
