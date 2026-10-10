// 표본 라이브러리: 브라우저 저장소 + JSON 내보내기/불러오기 (SPEC 9.1, 9.5)
import type { Lens, Metrics } from './engine';

export interface Sample {
  id: string;
  name: string;
  region: string;
  point: [number, number];
  walk_minutes: number;
  walkshed: { type: string; coordinates: unknown };
  created: string;
  params_hash: string;
  lens: Lens;
  metrics: Metrics;
  context: Metrics;
  labels: Record<string, number | null>;
  notes: string;
  demo?: boolean;
}

const KEY = 'gyeol.library.v1';

export function loadLibrary(): Sample[] {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? (JSON.parse(raw) as Sample[]) : [];
  } catch {
    return [];
  }
}

export function saveLibrary(lib: Sample[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(lib.filter((s) => !s.demo)));
  } catch {
    /* 저장소를 못 쓰면 이번 세션 메모리에만 남는다 */
  }
}

export function nextId(lib: Sample[], now = new Date()): string {
  const d = now.toISOString().slice(0, 10).replace(/-/g, '');
  const pre = `s_${d}_`;
  const used = lib.filter((s) => s.id.startsWith(pre)).map((s) => parseInt(s.id.slice(pre.length), 10));
  const n = (used.length ? Math.max(...used) : 0) + 1;
  return pre + String(n).padStart(3, '0');
}

/** 지표 묶음을 9.5 구조(metrics / context / labels)로 나눈다. */
export function splitMetrics(m: Metrics): { metrics: Metrics; context: Metrics; labels: Record<string, number | null> } {
  const metrics: Metrics = {}, context: Metrics = {}, labels: Record<string, number | null> = {};
  for (const [k, v] of Object.entries(m)) {
    if (k.startsWith('ctx_')) context[k] = v;
    else if (k.startsWith('places_')) labels[k] = v as number | null;
    else metrics[k] = v;
  }
  return { metrics, context, labels };
}

export function exportJSON(lib: Sample[]): string {
  return JSON.stringify({ format: 'gyeol-library', version: 1, samples: lib.filter((s) => !s.demo) }, null, 1);
}

export function importJSON(text: string): Sample[] {
  const d = JSON.parse(text);
  const arr = Array.isArray(d) ? d : d.samples;
  if (!Array.isArray(arr)) throw new Error('표본 목록(samples)이 없습니다');
  return arr.filter((s: any) => s && typeof s.id === 'string' && Array.isArray(s.point)) as Sample[];
}

/** 동류 집단 필터: 줄마다 "ctx_density 100 400" 또는 "ctx_density 100-400". */
export function parsePeerFilter(text: string): { key: string; lo: number; hi: number }[] {
  const out: { key: string; lo: number; hi: number }[] = [];
  for (const line of text.split(/[\n;]/)) {
    const m = line.trim().match(/^([a-z_0-9]+)\s+(-?[\d.]+)\s*(?:-|–|~|\s)\s*(-?[\d.]+)$/i);
    if (m) out.push({ key: m[1], lo: parseFloat(m[2]), hi: parseFloat(m[3]) });
  }
  return out;
}

export function passesPeer(s: Sample, rules: { key: string; lo: number; hi: number }[]): boolean {
  return rules.every((r) => {
    const v = (s.context[r.key] ?? s.metrics[r.key] ?? s.labels[r.key]) as number | null | undefined;
    return typeof v === 'number' && v >= r.lo && v <= r.hi;
  });
}
