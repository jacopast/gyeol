import { defineConfig } from 'vite';

// GitHub Pages는 /gyeol/ 아래에서 서빙된다. 로컬 개발은 /.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/gyeol/' : '/',
  worker: { format: 'es' },
  test: { include: ['tests/**/*.test.ts'] },
}));
