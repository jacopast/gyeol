// '실험' 칸: 같은 면적의 공원을 모을 때와 흩을 때 (시나리오 실험실 결과를 직접 만져 보기)
import { loadClassImage, paint, palette } from './ground';
import type { Tokens } from './mapstyle';

interface Row {
  layout: string; alpha: number; beta: number; congestion: boolean; opportunity_cost: boolean; barrier: boolean;
  access_mean: number; access_p10: number; os_cover_5: number;
}
export interface LabState {
  data: { layouts: Record<string, { n_spaces: number; total_ha: number; largest_patch_ha: number }>; rows: Row[]; city: any } | null;
  alpha: number; beta: number; congestion: boolean; opportunity_cost: boolean; barrier: boolean;
}

const ORDER = ['concentrated', 'medium', 'dispersed', 'mixed'];
const NAME: Record<string, string> = { concentrated: '한 곳에 모음', medium: '네 곳', dispersed: '100곳에 흩음', mixed: '섞음' };
const ALPHA: [number, string][] = [[0.3, '조금만'], [0.5, '반쯤'], [0.7, '꽤'], [1, '면적만큼']];
const BETA: [number, string][] = [[0, '아니, 똑같이'], [0.25, '조금 더'], [0.5, '꽤 멀리서'], [0.75, '더 멀리서'], [1, '아주 멀리서']];

function pick(s: LabState): Row[] {
  return s.data!.rows.filter((r) => r.alpha === s.alpha && r.beta === s.beta && r.congestion === s.congestion
    && r.opportunity_cost === s.opportunity_cost && r.barrier === s.barrier);
}

export function renderLab(s: LabState): string {
  const rows = pick(s);
  const by = Object.fromEntries(rows.map((r) => [r.layout, r]));
  const measures: [keyof Row, string][] = [['access_mean', '주민 평균 접근성'], ['access_p10', '가장 불리한 10%의 접근성'], ['os_cover_5', '5분 안에 공원 있는 주민']];
  const max = (k: keyof Row) => Math.max(...rows.map((r) => r[k] as number));
  const top = (k: keyof Row) => {
    const m = max(k);
    if (!(m > 0)) return [];
    const w = ORDER.filter((l) => by[l] && Math.abs((by[l][k] as number) - m) <= 1e-6 * m);
    return w.length === ORDER.length ? [] : w; // 모두 같으면 '차이 없음'
  };
  const head = `<div></div>${ORDER.map((l) => `<figure><canvas data-lab-img="${l}"></canvas><div>${NAME[l]}</div><div class="muted">${s.data!.layouts[l].n_spaces}곳</div></figure>`).join('')}`;
  const body = measures.map(([k, label]) => {
    const m = max(k);
    const tops = top(k);
    return `<div class="lab-label">${label}</div>${ORDER.map((l) => {
      const v = by[l] ? (by[l][k] as number) : NaN;
      const pct = m > 0 ? (v / m) * 100 : 0;
      const tip = k === 'os_cover_5' ? `${(v * 100).toFixed(0)}%` : v.toPrecision(3);
      return `<div class="lab-cell ${tops.includes(l) ? 'top' : ''}" title="${tip}">${Math.round(pct)}<div class="bar" style="width:${Math.max(pct, 1)}%"></div></div>`;
    }).join('')}`;
  }).join('');
  const sentence = measures.map(([k, label]) => {
    const t = top(k);
    return t.length ? `${label} 기준으로는 <b>${t.map((l) => NAME[l]).join(', ')}</b>` : `${label} 기준으로는 배치 사이 차이가 없습니다`;
  }).join(', ');
  const btn = (key: string, val: unknown, label: string, on: boolean) => `<button class="link" data-lab="${key}" data-val="${val}" aria-pressed="${on}">${label}</button>`;
  const city = s.data!.city;
  return `<section><h2>실험: 큰 공원 하나 vs 작은 공원 여럿</h2>
    <p class="small">가상의 도시(${city.city_size_blocks}×${city.city_size_blocks} 블록)에 같은 면적(블록 면적의 ${Math.round(city.open_space_share * 100)}%)의 공원을 배치만 바꿔 넣었습니다. 아래 두 질문의 답을 고르면 결과가 바뀝니다.</p>
    <p class="small" style="margin-top:8px">① 공원이 두 배 크면 두 배 좋은가? (α)</p>
    <p class="list">${ALPHA.map(([v, l]) => btn('alpha', v, l, s.alpha === v)).join('')}</p>
    <p class="small">② 큰 공원은 더 멀리서도 찾아가나? (β)</p>
    <p class="list">${BETA.map(([v, l]) => btn('beta', v, l, s.beta === v)).join('')}</p>
    <p class="list small">${btn('congestion', !s.congestion, `붐빔 반영 ${s.congestion ? '켬' : '끔'}`, s.congestion)}
      ${btn('barrier', !s.barrier, `공원이 길을 막음 ${s.barrier ? '켬' : '끔'}`, s.barrier)}
      ${btn('opportunity_cost', !s.opportunity_cost, `공원 자리만큼 집이 줄어듦 ${s.opportunity_cost ? '켬' : '끔'}`, s.opportunity_cost)}</p>
    <div class="lab-grid">${head}${body}</div>
    <p class="small">숫자 = 각 줄에서 가장 큰 값을 100으로 둔 상대값. 굵은 글씨가 그 줄의 가장 큰 값.</p>
    <p class="lead">이 조건에서 값이 가장 큰 배치: ${sentence}.</p>
    ${s.congestion ? '<p class="small">붐빔을 반영하면 평균은 어떤 배치든 같아집니다(공원 총면적 ÷ 인구). 차이는 누가 덜 받느냐(10%)에서만 납니다.</p>' : ''}
    <details><summary class="small">무엇을 셌나</summary><p class="small">
      '접근성'은 걸어서 닿는 공원들의 면적을 거리로 깎아 더한 값입니다. ①에서 '조금만'을 고르면 공원이 커져도 가치가 덜 늘고, ②에서 '멀리서'를 고르면 큰 공원의 영향 범위가 넓어집니다.
      답에 따라 결과가 뒤집히는 지점이 이 실험의 결과입니다 — ①이 '면적만큼'에 가까울수록, ②가 '멀리서'에 가까울수록 모으는 배치의 값이 커집니다.
      전체 표는 <a href="https://github.com/jacopast/gyeol/blob/main/reports/scenarios.md" target="_blank" rel="noopener">reports/scenarios.md</a>.</p></details></section>`;
}

const imgs = new Map<string, ImageData>();
const loading = new Set<string>();
const BASE = import.meta.env.BASE_URL;

export function paintLab(root: HTMLElement, _s: LabState, t: Tokens): void {
  const pal = palette(t, true);
  root.querySelectorAll<HTMLCanvasElement>('canvas[data-lab-img]').forEach((c) => {
    const l = c.dataset.labImg!;
    const im = imgs.get(l);
    if (im) { paint(c, im, pal); return; }
    if (loading.has(l)) return;
    loading.add(l);
    loadClassImage(`${BASE}data/scenarios/${l}.png`).then((d) => {
      imgs.set(l, d);
      root.querySelectorAll<HTMLCanvasElement>(`canvas[data-lab-img="${l}"]`).forEach((cc) => paint(cc, d, pal));
    }).catch(() => loading.delete(l));
  });
}
