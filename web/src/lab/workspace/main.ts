/**
 * ARGOS lab: functional workspace (web/lab/workspace.html).
 *
 * Interactive prototype of the refreshed Observe workspace: task modes that
 * re-arrange the same regions, resizable and collapsible panes with per-mode
 * presets, the image as the hero with a HUD, a command palette, an inspector,
 * the Watch glance view, the attention centre and the drawer; plus an
 * overview of how the other sections inherit the same regions.
 *
 * Not part of the app bundle (`vite build` only builds index.html). Data is
 * synthetic (seeded, in the browser) unless ?frames=server points the viewer
 * at a running ARGOS simulator. It imports app components read-only
 * (FitsViewer, Histogram, Icon, IconButton, Button, Card, StatusBadge, the
 * keymap) and never writes the app's preference keys.
 */

import { mount } from 'svelte';
import '../../design/tokens.css';
import '../../app.css';
import 'uplot/dist/uPlot.min.css';
import './workspace.css';
import WorkspaceApp from './WorkspaceApp.svelte';

const target = document.getElementById('lab-workspace');
if (!target) throw new Error('lab: #lab-workspace mount point missing');

export default mount(WorkspaceApp, { target });
