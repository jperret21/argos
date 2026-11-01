/**
 * ARGOS lab: live charts (web/lab/charts.html).
 *
 * Dynamic chart prototypes on a synthetic night (SW And from Paris,
 * 2026-11-01): live light curve, Review plot wall, autofocus V-curve,
 * conditions timeline, visibility timeline, histogram with stretch handles,
 * glanceable mini-charts, and the charts in their Observe space. Not part
 * of the app bundle (`vite build` only builds index.html). No server.
 */

import { mount } from 'svelte';
import '../../design/tokens.css';
import 'uplot/dist/uPlot.min.css';
import './lab.css';
import ChartsLab from './ChartsLab.svelte';

const target = document.getElementById('lab');
if (!target) throw new Error('lab: #lab mount point missing');

export default mount(ChartsLab, { target });
