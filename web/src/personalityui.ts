// 성격 모드 패널 (SPEC 9.10): 유형 A·B·C… 프로필(평균·범위)과 현재 대상의 유형 거리. 평가 형용사 없음
import type { Metrics } from './engine';
import { fmtValue, METRICS, type Units } from './metrics';

export interface PersonalityModel {
  features: string[];
  standardize: string;
  mean: number[] | null;
  std: number[] | null;
  pca_components: number[][];
  pca_mean: number[];
  pca_explained: number[];
  k: number;
  silhouette: Record<string, number>;
  centers: Record<string, number[]>;
  profiles: Record<string, Record<string, { mean: number; min: number; max: number }> & { n: number }>;
  n_samples: number;
  n_clustered: number;
  rule: string;
}

export interface PersonalityState { model: PersonalityModel | null; targetType: string | null }

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!);

/** 현재 값 → 표준화 → 주성분 좌표 → 각 유형 중심까지 거리. 지표가 하나라도 없으면 null. */
export function typeDistances(m: PersonalityModel, metrics: Metrics): Record<string, number> | null {
  if (m.standardize !== 'zscore' || !m.mean || !m.std) return null;
  const x = m.features.map((f) => metrics[f]);
  if (x.some((v) => typeof v !== 'number' || !Number.isFinite(v))) return null;
  const z = (x as number[]).map((v, j) => (v - m.mean![j]) / m.std![j] - m.pca_mean[j]);
  const p = m.pca_components.map((comp) => comp.reduce((s, c, j) => s + c * z[j], 0));
  const out: Record<string, number> = {};
  for (const [t, c] of Object.entries(m.centers)) out[t] = Math.sqrt(c.reduce((s, v, i) => s + (v - p[i]) ** 2, 0));
  return out;
}

export function renderPersonality(s: { personality: PersonalityState; units: Units; current: { name: string; metrics: Metrics } | null }): string {
  const m = s.personality.model;
  if (!m) return '';
  const def = (f: string) => METRICS.find((d) => d.id === f)!;
  const types = Object.keys(m.profiles).sort();
  const sil = Object.entries(m.silhouette).map(([k, v]) => `${k}: ${v.toFixed(2)}`).join(', ');
  const profileTable = (t: string) => `<table><tr><th>지표</th><th>평균</th><th>범위</th></tr>${m.features.map((f) => {
    const p = m.profiles[t][f];
    return `<tr><td>${esc(def(f).label)}</td><td>${fmtValue(def(f), p.mean, s.units)}</td><td>${fmtValue(def(f), p.min, s.units)} ~ ${fmtValue(def(f), p.max, s.units)}</td></tr>`;
  }).join('')}</table>`;
  let cur = '';
  if (s.current) {
    const d = typeDistances(m, s.current.metrics);
    if (!d) cur = `<p class="small">${esc(s.current.name)}: 지문 지표 중 데이터 없는 값이 있어 유형 거리를 계산하지 않습니다.</p>`;
    else {
      const order = Object.entries(d).sort((a, b) => a[1] - b[1]);
      cur = `<p class="small">${esc(s.current.name)} — 유형 중심까지 거리 (표준화 주성분 공간): ${order.map(([t, v]) => `${t} ${v.toFixed(2)}`).join(' · ')}</p>`;
    }
    const tt = s.personality.targetType;
    cur += `<p class="small">목표 유형 고르기: ${types.map((t) => `<button class="link" data-ptype="${t}" aria-pressed="${t === tt}">${t}</button>`).join(' ')}</p>`;
    if (tt && m.profiles[tt]) {
      cur += `<table><tr><th>지표</th><th>현재</th><th>유형 ${tt} 평균</th><th>유형 범위 안?</th></tr>${m.features.map((f) => {
        const v = s.current!.metrics[f] as number | null;
        const p = m.profiles[tt][f];
        const inside = typeof v === 'number' ? (v >= p.min && v <= p.max ? '안' : v < p.min ? '아래' : '위') : '';
        return `<tr><td>${esc(def(f).label)}</td><td>${fmtValue(def(f), v, s.units)}</td><td>${fmtValue(def(f), p.mean, s.units)}</td><td>${inside}</td></tr>`;
      }).join('')}</table>
      <p class="small">'아래/위'는 유형 ${tt} 표본들의 범위 밖이라는 뜻일 뿐, 그만큼 넣으라는 처방이 아닙니다.</p>`;
    }
  }
  return `<section><h2>성격 (유형)</h2>
    <p class="small">시연 표본 ${m.n_samples}개 중 ${m.n_clustered}개를 지표 ${m.features.length}개로 묶은 유형입니다. 좋고 나쁨이 아니라 지문의 비슷함입니다.
    이름은 첫 주성분 순서로 붙인 기호입니다. 규칙(실행 전 고정): ${esc(m.rule)}. 실루엣 ${sil} → k = ${m.k}.</p>
    ${cur}
    ${types.map((t) => `<details><summary class="small">유형 ${t} · 표본 ${m.profiles[t].n}개</summary>${profileTable(t)}</details>`).join('')}
    <p class="small">어떤 지표를 넣고 어떻게 표준화하고 몇 개로 나눌지가 결과를 정합니다. 이 선택도 사전 고정 대상입니다(SPEC 8.2).</p></section>`;
}
