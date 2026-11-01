/**
 * ARGOS lab: the control system (web/lab/controls.html).
 *
 * An interactive specimen of the refreshed controls: buttons and toolbars,
 * segmented and split controls, numeric fields with scrubbing, steppers,
 * sliders with ticks, the focuser and the mount jog pad, hold-to-confirm,
 * busy and progress states, chips, key hints and disabled reasons, every
 * state in the three themes. Synthetic hardware only (sim.svelte.ts), no
 * server. Not part of the app bundle: `vite build` only builds index.html.
 *
 * Imports from web/src/lib and web/src/design are read-only; everything new
 * lives here, ready to be promoted piece by piece (see each file's header).
 */

import { mount } from 'svelte';
import '../../design/tokens.css';
import '../../app.css';
import './controls.css';
import ControlsApp from './ControlsApp.svelte';

// Page errors, readable by the WKWebView probe (no devtools there).
const labErrors: string[] = [];
(window as unknown as { __labErrors: string[] }).__labErrors = labErrors;
window.addEventListener('error', (e) => labErrors.push(String(e.message)));
window.addEventListener('unhandledrejection', (e) => labErrors.push(String(e.reason)));

const target = document.getElementById('lab');
if (!target) throw new Error('lab: #lab mount point missing');

export default mount(ControlsApp, { target });
