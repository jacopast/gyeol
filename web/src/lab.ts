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
  const measures: [keyof Row, string][] = [['access_mean', '주민 평균 접근성'], ['access_p10', '접근성 하위 10% 경계값'], ['os_cover_5', '5분 안에 공원 있는 주민']];
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
      return `<div class="lab-cell ${tops.includes(l) ? 'top' : ''}" title="${tip}">${k === 'os_cover_5' ? `${Math.round(v * 100)}%` : Math.round(pct)}<div class="bar" style="width:${Math.max(k === 'os_cover_5' ? v * 100 : pct, 1)}%"></div></div>`;
    }).join('')}`;
  }).join('');
  const sentence = measures.map(([k, label]) => {
    const t = top(k);
    return t.length ? `${label} 기준으로는 <b>${t.map((l) => NAME[l]).join(', ')}</b>` : `${label} 기준으로는 배치 사이 차이가 없습니다`;
  }).join(', ');
  // 이 가상도시에서 결과가 바뀌는 조건: 기본 조건(붐빔·장벽·기회비용 끔)에서 ①의 답마다, ②를 어디까지 올리면 '한 곳에 모음'이 '100곳에 흩음'을 앞서는가
  const base = s.data!.rows.filter((r) => !r.congestion && !r.barrier && !r.opportunity_cost);
  const flips = ALPHA.map(([a, al]) => {
    const b = BETA.find(([bv]) => {
      const c = base.find((r) => r.alpha === a && r.beta === bv && r.layout === 'concentrated');
      const d = base.find((r) => r.alpha === a && r.beta === bv && r.layout === 'dispersed');
      return c && d && c.access_mean >= d.access_mean;
    });
    return `<tr><td>${al}</td><td>${b ? (b[0] === 0 ? '처음부터 (②와 상관없이)' : `'${b[1]}'부터`) : '끝까지 흩는 쪽이 큼'}</td></tr>`;
  }).join('');
  const learned = `<details open><summary class="small">이 가상도시에서 결과가 바뀌는 조건</summary>
    <p class="small">주민 평균 접근성으로 보면, ①의 답에 따라 ②를 어디까지 올려야 '한 곳에 모음'이 '100곳에 흩음'보다 커지는지가 정해집니다 (붐빔·장벽·집 줄어듦은 끈 상태).</p>
    <table><tr><th>① 공원이 두 배 크면</th><th>② 모으는 쪽이 커지는 지점</th></tr>${flips}</table>
    <p class="small">즉 '큰 공원은 작은 공원과 다르다'고 볼수록(①·② 모두) 모으는 쪽이, 면적 체감이 크고 규모별 서비스권 차이가 작다고 가정할수록 흩는 쪽이 커집니다. 이 표는 가정에 따른 모델 결과입니다. 실제 도시에서의 방문·회복·건강 효과나 어느 배치가 더 좋은지를 입증하지 않습니다.</p></details>`;
  const btn = (key: string, val: unknown, label: string, on: boolean) => `<button class="link" data-lab="${key}" data-val="${val}" aria-pressed="${on}" ${key === 'alpha' && s.congestion ? 'disabled' : ''}>${label}</button>`;
  const city = s.data!.city;
  return `<section><h2>실험: 큰 공원 하나 vs 작은 공원 여럿</h2>
    <p class="small">가상의 도시(${city.city_size_blocks}×${city.city_size_blocks} 블록, 한 블록 ${city.block_m} m)에 같은 면적(블록 면적의 ${Math.round(city.open_space_share * 100)}%)의 공원을 배치만 바꿔 넣었습니다. 답을 고르면 아래 표가 바뀝니다.</p>
    <p class="small" style="margin-top:8px">① 면적이 두 배일 때 접근성 계산에서 얼마나 더 반영할까? (α)</p>
    <p class="list">${ALPHA.map(([v, l]) => btn('alpha', v, `${l} (${(2 ** v).toFixed(2)}배)`, s.alpha === v)).join('')}</p>
    <p class="small">② 큰 공원의 서비스권을 얼마나 넓게 가정할까? (β)</p>
    <p class="list">${BETA.map(([v, l]) => btn('beta', v, `${l} (${(2 ** v).toFixed(2)}배)`, s.beta === v)).join('')}</p>
    <p class="small">괄호는 면적이 두 배일 때의 배수입니다. β는 반경 상·하한 적용 전 값입니다. 두 가정은 실측으로 확정한 현실 범위가 아닙니다.</p>
    <p class="list small">${btn('congestion', !s.congestion, `붐빔 반영 ${s.congestion ? '켬' : '끔'}`, s.congestion)}
      ${btn('barrier', !s.barrier, `공원이 길을 막음 ${s.barrier ? '켬' : '끔'}`, s.barrier)}
      ${btn('opportunity_cost', !s.opportunity_cost, `공원 자리만큼 집이 줄어듦 ${s.opportunity_cost ? '켬' : '끔'}`, s.opportunity_cost)}</p>
    <div class="lab-grid">${head}${body}</div>
    <p class="small">접근성 두 줄은 각 줄의 최댓값을 100으로 둔 상대값이며 조건 간 절대 비교에는 쓰지 않습니다. 마지막 줄은 실제 주민 비율(%)입니다. 굵은 글씨는 줄 안의 최댓값입니다.</p>
    <p class="lead">이 조건에서 값이 가장 큰 배치: ${sentence}.</p>
    ${learned}
    ${s.congestion ? '<p class="small">붐빔 모형은 면적 ÷ 수요를 쓰므로 α를 적용하지 않습니다. 모든 공간에 닿는 인구가 있으면 평균은 총면적 ÷ 총인구입니다. 집 줄어듦을 켜면 배치별 남은 인구가 달라 평균도 달라질 수 있습니다. 분포 차이는 하위 10% 경계값에서 봅니다.</p>' : ''}
    <details><summary class="small">무엇을 셌나</summary><p class="small">
      '접근성'은 걸어서 닿는 공원들의 면적을 거리로 깎아 더한 값입니다. ①에서 '조금만'을 고르면 공원이 커져도 가치가 덜 늘고, ②에서 '멀리서'를 고르면 큰 공원의 영향 범위가 넓어집니다.
      답에 따라 결과가 뒤집히는 지점이 이 실험의 결과입니다 — ①이 '면적만큼'에 가까울수록, ②가 '멀리서'에 가까울수록 모으는 배치의 값이 커집니다.
      '하위 10% 경계값'은 인구를 접근성 값 순으로 놓았을 때 아래에서 10% 지점의 값이며, 하위 집단 평균이나 거리 순위가 아닙니다, '5분 안에 공원 있는 주민'은 크기와 상관없이 5분 안에 공원이 있는 주민 비율입니다. 전체 표는 <a href="https://github.com/jacopast/gyeol/blob/main/reports/scenarios.md" target="_blank" rel="noopener">reports/scenarios.md</a>.</p></details></section>`;
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
