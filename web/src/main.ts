import { mount } from 'svelte';
import './design/tokens.css';
import './app.css';
import App from './App.svelte';

const target = document.getElementById('app');
if (!target) throw new Error('ARGOS: #app mount point missing from index.html');

export default mount(App, { target });
