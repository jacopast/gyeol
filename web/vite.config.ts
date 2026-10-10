import { defineConfig } from 'vite';

// GitHub Pages는 /gyeol/ 아래에서 서빙된다 (빌드·미리보기). 로컬 개발은 /.
export default defineConfig(({ command, isPreview }) => ({
  base: command === 'build' || isPreview ? '/gyeol/' : '/',
  worker: { format: 'es' },
  test: { include: ['tests/**/*.test.ts'] },
}));
