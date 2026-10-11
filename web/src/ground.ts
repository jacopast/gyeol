// 지상층 분류 그림(값 = 클래스 코드)을 테마 색으로 칠한다. 지도 바탕과 실험 그림이 같이 쓴다.
// 1 조건 없는 열린 공간 · 2 차로 · 3 사적 · 4 보도 · 5 조건부 열린 공간 · 6 POPS
import type { Tokens } from './mapstyle';

function rgb(css: string): [number, number, number] {
  const c = document.createElement('canvas').getContext('2d')!;
  c.fillStyle = css;
  const h = c.fillStyle as string; // #rrggbb
  return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
}

/** 클래스 → [r,g,b,a]. opaque=true면 사적 공간도 칠한다(실험 그림용). */
export function palette(t: Tokens, opaque = false): Record<number, [number, number, number, number]> {
  const acc = rgb(t.accent), fg = rgb(t.fg), bg = rgb(t.bg), cell = rgb(t.cell);
  return {
    0: opaque ? [...bg, 255] : [0, 0, 0, 0],
    1: [...acc, 235],
    2: opaque ? [...cell, 255] : [...fg, 18],
    3: opaque ? [...bg, 255] : [0, 0, 0, 0],
    4: [...fg, opaque ? 90 : 60],
    5: [...acc, 110],
    6: [...acc, 110],
  };
}

export async function loadClassImage(url: string): Promise<ImageData> {
  const img = new Image();
  img.crossOrigin = 'anonymous';
  img.src = url;
  await img.decode();
  const c = document.createElement('canvas');
  c.width = img.naturalWidth;
  c.height = img.naturalHeight;
  const g = c.getContext('2d', { willReadFrequently: true })!;
  g.drawImage(img, 0, 0);
  return g.getImageData(0, 0, c.width, c.height);
}

/** 클래스 그림을 canvas에 색칠해 그린다. */
export function paint(canvas: HTMLCanvasElement, cls: ImageData, pal: Record<number, [number, number, number, number]>): void {
  canvas.width = cls.width;
  canvas.height = cls.height;
  const g = canvas.getContext('2d')!;
  const out = g.createImageData(cls.width, cls.height);
  const s = cls.data, d = out.data;
  for (let i = 0; i < s.length; i += 4) {
    const p = pal[s[i]] ?? pal[0];
    d[i] = p[0]; d[i + 1] = p[1]; d[i + 2] = p[2]; d[i + 3] = p[3];
  }
  g.putImageData(out, 0, 0);
}
