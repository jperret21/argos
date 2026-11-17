import { mount } from 'svelte';
import './design/tokens.css';
import './app.css';
import App from './App.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('ARGOS: #app mount point missing from index.html');

// Development only: /?gallery=1 shows every shared component in every state
// (design review). `import.meta.env.DEV` is false in `vite build`, so the
// gallery and its fixtures are not in the production bundle.
if (import.meta.env.DEV && new URLSearchParams(location.search).has('gallery')) {
  void import('./lib/components/gallery/Gallery.svelte').then(({ default: Gallery }) => mount(Gallery, { target }));
} else {
  mount(App, { target });
}
