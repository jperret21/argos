/**
 * ARGOS lab: stack research (web/lab/research.html).
 *
 * Live, minimal proofs of what Svelte 5, uPlot, Canvas / WebGL2, workers and
 * modern CSS give the ARGOS UI, with the facts measured in the engine that
 * opens the page. Not part of the app bundle: `vite build` only builds
 * index.html. Synthetic data only, no server.
 */

import { mount } from 'svelte';
import '../../design/tokens.css';
import 'uplot/dist/uPlot.min.css';
import './lab.css';
import ResearchApp from './ResearchApp.svelte';

const target = document.getElementById('lab');
if (!target) throw new Error('lab: #lab mount point missing');

export default mount(ResearchApp, { target });
