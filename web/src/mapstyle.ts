// 무채색 베이스맵 (SPEC 9.2): 땅 --bg, 건물 --cell-bg, 도로 --line, 물은 --bg보다 약간 어둡게, 라벨 --muted
// 키 없는 OpenFreeMap 벡터 타일 (OpenMapTiles 스키마)
import type { Map as MLMap, StyleSpecification } from 'maplibre-gl';

export interface Tokens { bg: string; fg: string; muted: string; line: string; cell: string; water: string; accent: string }

export function readTokens(): Tokens {
  const s = getComputedStyle(document.documentElement);
  const g = (k: string) => s.getPropertyValue(k).trim();
  return { bg: g('--bg'), fg: g('--fg'), muted: g('--muted'), line: g('--line'), cell: g('--cell-bg'), water: g('--water'), accent: g('--accent') };
}

export function baseStyle(t: Tokens): StyleSpecification {
  return {
    version: 8,
    glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
    sources: { omt: { type: 'vector', url: 'https://tiles.openfreemap.org/planet', attribution: '© OpenStreetMap · OpenFreeMap' } },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': t.bg } },
      { id: 'water', type: 'fill', source: 'omt', 'source-layer': 'water', paint: { 'fill-color': t.water } },
      { id: 'building', type: 'fill', source: 'omt', 'source-layer': 'building', minzoom: 13, paint: { 'fill-color': t.cell } },
      {
        id: 'road', type: 'line', source: 'omt', 'source-layer': 'transportation',
        filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'minor', 'service']]],
        paint: { 'line-color': t.line, 'line-width': ['interpolate', ['linear'], ['zoom'], 11, 0.3, 16, 2] },
      },
      {
        id: 'place', type: 'symbol', source: 'omt', 'source-layer': 'place',
        filter: ['in', ['get', 'class'], ['literal', ['city', 'town', 'suburb']]],
        layout: { 'text-field': ['coalesce', ['get', 'name:ko'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': 11 },
        paint: { 'text-color': t.muted, 'text-halo-color': t.bg, 'text-halo-width': 1 },
      },
      {
        id: 'place-minor', type: 'symbol', source: 'omt', 'source-layer': 'place', minzoom: 14,
        filter: ['in', ['get', 'class'], ['literal', ['neighbourhood', 'quarter']]],
        layout: { 'text-field': ['coalesce', ['get', 'name:ko'], ['get', 'name']], 'text-font': ['Noto Sans Regular'], 'text-size': 10 },
        paint: { 'text-color': t.muted, 'text-halo-color': t.bg, 'text-halo-width': 1 },
      },
      {
        id: 'road-name', type: 'symbol', source: 'omt', 'source-layer': 'transportation_name', minzoom: 15,
        layout: { 'text-field': ['get', 'name'], 'text-font': ['Noto Sans Regular'], 'text-size': 10, 'symbol-placement': 'line' },
        paint: { 'text-color': t.muted, 'text-halo-color': t.bg, 'text-halo-width': 1 },
      },
    ],
  };
}

/** 테마가 바뀌면 베이스맵·데이터 레이어 색을 다시 칠한다. */
export function repaint(map: MLMap, t: Tokens): void {
  const set = (id: string, prop: string, v: unknown) => { if (map.getLayer(id)) map.setPaintProperty(id, prop as any, v); };
  set('bg', 'background-color', t.bg);
  set('water', 'fill-color', t.water);
  set('building', 'fill-color', t.cell);
  set('road', 'line-color', t.line);
  for (const id of ['place', 'place-minor', 'road-name']) { set(id, 'text-color', t.muted); set(id, 'text-halo-color', t.bg); }
  set('cells-fill', 'fill-color', t.fg);
  set('spaces-line', 'line-color', t.muted);
  for (const id of ['sample-10', 'sample-5', 'design-line', 'design-boundary', 'design-walk-after']) set(id, 'line-color', t.fg);
  set('design-walk-before', 'line-color', t.muted);
  set('design-walk-start', 'circle-color', t.fg);
  set('library-line', 'line-color', t.muted);
  set('sample-point', 'circle-color', t.fg);
  set('sample-point', 'circle-stroke-color', t.bg);
  set('spaces-name', 'text-color', t.muted);
  set('spaces-name', 'text-halo-color', t.bg);
  set('nearest-line', 'line-color', t.fg);
}
