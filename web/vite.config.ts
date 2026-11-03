import { svelte } from '@sveltejs/vite-plugin-svelte';
import { defineConfig } from 'vitest/config';

// Offline-first: everything is bundled, nothing is fetched from a CDN at runtime.
// The future Tauri shell loads dist/ from disk, hence the relative base.
export default defineConfig({
  base: './',
  plugins: [svelte()],
  build: {
    target: 'es2022',
    sourcemap: true,
  },
  test: {
    // scripts/*.test.mjs: the dependency-free CI tools (audit-png.mjs).
    include: ['src/**/*.test.ts', 'scripts/**/*.test.mjs'],
    environment: 'node',
  },
});
