<!--
  The viewer's context menu (web/spec/04-viewer-and-image-tools.md 2.2 rows 1.1 #4 and 1.2,
  2.3, 2.4; README 3.1): right-click on the image, Shift+F10 or the Menu key while the
  viewer has focus. Token-drawn (components/Menu.svelte), never the native menu, so Night
  Red holds. Items: tools/viewermenu.ts. Right-drag zoom is dropped (wheel, pinch, + / −).

  A sibling of the viewer in the stage: it listens on its parent for `contextmenu` on the
  image ([role="application"]) and on the viewer's keys; the actions are the caller's
  (zoom, star selection, region, export) except copying, done here.
-->
<script lang="ts">
  import Menu from '../../components/Menu.svelte';
  import type { MenuChoice } from '../../components/menu';
  import { pixelAt, type ViewerGeometry } from './geometry';
  import { pixelText, skyText, viewerMenuItems, type ViewerMenuAction } from './viewermenu';

  interface Props {
    geometry: ViewerGeometry | null;
    /** Sky position of a frame pixel when the field is identified (null: not solved). */
    skyAt?: ((x: number, y: number) => { raHours: number; decDeg: number } | null) | null;
    keys: { fit?: string; one?: string; region?: string };
    canIdentify?: boolean;
    identifyReason?: string | null;
    hasSelection?: boolean;
    onaction: (action: ViewerMenuAction, pixel: { x: number; y: number } | null) => void;
    /** Copy feedback (the caller's toast). */
    oncopied?: (what: string, text: string) => void;
  }

  let { geometry, skyAt = null, keys, canIdentify = false, identifyReason = null, hasSelection = false, onaction, oncopied }: Props = $props();

  let anchor: HTMLSpanElement | undefined = $state();
  let open = $state(false);
  let point = $state<{ x: number; y: number } | null>(null);
  let pixel = $state<{ x: number; y: number } | null>(null);

  const sky = $derived(pixel && skyAt ? skyAt(pixel.x, pixel.y) : null);
  const items = $derived(viewerMenuItems({ pixel, sky, keys, canIdentify, identifyReason, hasSelection }));

  function openAt(clientX: number, clientY: number): void {
    const host = anchor?.parentElement;
    if (!host) return;
    const b = host.getBoundingClientRect();
    pixel = geometry ? pixelAt(geometry, clientX - b.left, clientY - b.top) : null;
    point = { x: clientX, y: clientY };
    open = true;
  }

  $effect(() => {
    const host = anchor?.parentElement;
    if (!host) return;
    const viewer = () => host.querySelector<HTMLElement>('[role="application"]');
    const onContext = (e: MouseEvent) => {
      if (!(e.target as Element | null)?.closest?.('[role="application"]')) return;
      e.preventDefault();
      openAt(e.clientX, e.clientY);
    };
    const onKey = (e: KeyboardEvent) => {
      const v = viewer();
      if (!v || document.activeElement !== v) return;
      if (!(e.key === 'ContextMenu' || (e.key === 'F10' && e.shiftKey))) return;
      e.preventDefault();
      // From the keyboard: at the image centre (the point the viewer's arrows pan around).
      const r = v.getBoundingClientRect();
      openAt(r.left + r.width / 2, r.top + r.height / 2);
    };
    host.addEventListener('contextmenu', onContext);
    host.addEventListener('keydown', onKey);
    return () => {
      host.removeEventListener('contextmenu', onContext);
      host.removeEventListener('keydown', onKey);
    };
  });

  async function copy(what: string, text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
      oncopied?.(what, text);
    } catch {
      oncopied?.(`${what}: the browser refused the clipboard`, text);
    }
  }

  function choose(item: MenuChoice): void {
    const id = item.id as ViewerMenuAction;
    if (id === 'copy-pixel' && pixel) void copy('Pixel position', pixelText(pixel));
    else if (id === 'copy-sky' && sky) void copy('RA / Dec', skyText(sky));
    else onaction(id, pixel);
  }
</script>

<span class="anchor" bind:this={anchor} aria-hidden="true"></span>
<Menu bind:open {point} anchor={null} {items} label="Image" minWidth={300} onselect={choose} />

<style>
  .anchor {
    position: absolute;
    width: 0;
    height: 0;
    overflow: hidden;
  }
</style>
