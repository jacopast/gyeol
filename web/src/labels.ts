// 외부 라벨 CSV 불러오기 (SPEC 9.11, M8). 형식은 docs/labels.md
// 1) 관찰·설문 값:  sample_id 또는 lon,lat 열 + 숫자 열들 → 표본 labels.csv_<열 이름>
// 2) 쌍대 비교:     sample_a, sample_b, question, winner(a|b|tie) → labels.pairwise_<question> = 승률(무승부 0.5)
import type { Sample } from './library';

export function parseCSV(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [], cell = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch;
    } else if (ch === '"') q = true;
    else if (ch === ',') { row.push(cell); cell = ''; }
    else if (ch === '\n' || ch === '\r') {
      if (ch === '\r' && text[i + 1] === '\n') i++;
      row.push(cell); cell = '';
      if (row.some((c) => c.trim() !== '')) rows.push(row);
      row = [];
    } else cell += ch;
  }
  row.push(cell);
  if (row.some((c) => c.trim() !== '')) rows.push(row);
  return rows;
}

const slug = (s: string) => s.trim().toLowerCase().replace(/[^a-z0-9가-힣]+/g, '_').replace(/^_|_$/g, '');

function haversine(a: [number, number], b: [number, number]): number {
  const R = 6371000, r = Math.PI / 180;
  const dla = (b[1] - a[1]) * r, dlo = (b[0] - a[0]) * r;
  const h = Math.sin(dla / 2) ** 2 + Math.cos(a[1] * r) * Math.cos(b[1] * r) * Math.sin(dlo / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

/** lib를 직접 고친다. 사람이 읽는 결과 한 줄을 돌려준다. maxDist: 좌표로 붙일 때 허용 거리(m). */
export function importLabelCSV(text: string, lib: Sample[], maxDist = 150): string {
  const rows = parseCSV(text);
  if (rows.length < 2) return 'CSV에 머리글과 값 줄이 필요합니다.';
  const head = rows[0].map(slug);
  const col = (n: string) => head.indexOf(n);
  if (col('sample_a') >= 0 && col('sample_b') >= 0 && col('winner') >= 0) return importPairwise(rows, head, lib);
  const iId = col('sample_id'), iLon = col('lon'), iLat = col('lat');
  if (iId < 0 && (iLon < 0 || iLat < 0)) return 'sample_id 열 또는 lon, lat 열이 필요합니다 (docs/labels.md).';
  const valueCols = head.map((h, i) => i).filter((i) => ![iId, iLon, iLat].includes(i));
  let matched = 0, skipped = 0;
  for (const r of rows.slice(1)) {
    let s: Sample | undefined;
    if (iId >= 0 && r[iId]?.trim()) s = lib.find((x) => x.id === r[iId].trim());
    else {
      const p: [number, number] = [parseFloat(r[iLon]), parseFloat(r[iLat])];
      if (Number.isFinite(p[0]) && Number.isFinite(p[1])) {
        let best: Sample | undefined, bd = maxDist;
        for (const x of lib) { const d = haversine(p, x.point); if (d <= bd) { bd = d; best = x; } }
        s = best;
      }
    }
    if (!s) { skipped++; continue; }
    for (const i of valueCols) {
      const v = parseFloat(r[i]);
      s.labels[`csv_${head[i]}`] = Number.isFinite(v) ? v : null;
    }
    matched++;
  }
  return `라벨 CSV: ${matched}줄을 표본에 붙였고 ${skipped}줄은 맞는 표본이 없어 건너뜀 (열 ${valueCols.map((i) => `csv_${head[i]}`).join(', ')}).`;
}

function importPairwise(rows: string[][], head: string[], lib: Sample[]): string {
  const ia = head.indexOf('sample_a'), ib = head.indexOf('sample_b'), iw = head.indexOf('winner'), iq = head.indexOf('question');
  const tally = new Map<string, Map<string, { w: number; n: number }>>();
  let bad = 0;
  for (const r of rows.slice(1)) {
    const a = r[ia]?.trim(), b = r[ib]?.trim(), w = r[iw]?.trim().toLowerCase();
    const q = iq >= 0 ? slug(r[iq] ?? '') || 'overall' : 'overall';
    if (!a || !b || !['a', 'b', 'tie'].includes(w)) { bad++; continue; }
    const t = tally.get(q) ?? new Map();
    for (const [id, score] of [[a, w === 'a' ? 1 : w === 'tie' ? 0.5 : 0], [b, w === 'b' ? 1 : w === 'tie' ? 0.5 : 0]] as [string, number][]) {
      const e = t.get(id) ?? { w: 0, n: 0 };
      e.w += score; e.n += 1;
      t.set(id, e);
    }
    tally.set(q, t);
  }
  let applied = 0;
  for (const [q, t] of tally) for (const [id, e] of t) {
    const s = lib.find((x) => x.id === id);
    if (s) { s.labels[`pairwise_${q}`] = e.w / e.n; applied++; }
  }
  return `쌍대 비교: 질문 ${tally.size}개, 표본 값 ${applied}개를 승률로 붙임${bad ? `, 형식이 틀린 줄 ${bad}개 건너뜀` : ''}.`;
}
