import { describe, expect, it } from 'vitest';
import { formatWidth, metersToMinutes } from '../src/units';

describe('units', () => {
  it('converts walking distance to minutes', () => {
    expect(metersToMinutes(360, 1.2)).toBeCloseTo(5);
  });
  it('formats missing width as 데이터 없음', () => {
    expect(formatWidth(null, 'ft')).toBe('데이터 없음');
    expect(formatWidth(3.048, 'ft')).toBe('10.0 ft');
  });
});
