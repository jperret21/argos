import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/vite-plugin-svelte').SvelteConfig} */
export default {
  preprocess: vitePreprocess(),
  // Runes everywhere: no accidental fallback to Svelte 4 reactivity.
  compilerOptions: { runes: true },
};
