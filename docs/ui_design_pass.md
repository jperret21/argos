# Argos — UI Design Pass (WS9)

> A real UI design workstream, modeled on N.I.N.A.'s Imaging workspace
> (screenshots analysed 2026-07-05: Customize_Imaging, Image_Recognition,
> Camera, Customize_Colors from nighttime-imaging.eu). Goal: a sober, dense,
> fully **customizable** night screen — the user composes their own cockpit.

## What NINA gets right (observed)

1. **The workspace is the user's.** Every panel (Camera, Statistics, HFR
   History, Guider, Image History, Sequence…) is a dockable tile with a
   title bar and a close ✕. A toolbar of small icon toggles shows/hides each
   panel. Panels resize freely and **float** as independent windows (second
   monitor). The image stays the hero in the middle.
2. **Density without clutter.** Statistics = compact key/value pairs
   (Mean/Median/Min/Max/#Stars/HFR). Trends = small sparklines (HFR History).
   No wasted chrome; panel titles are small, borders hairline.
3. **Flat dark theme + one accent.** Charcoal background, teal accent for
   actions/active states, color-coded charts. Theme presets plus a fully
   custom palette (per-color swatches), switchable at runtime.
4. **Profiles.** Equipment/UI profiles selectable at startup.

## Plan — three increments, app runnable after each

### WS9a — Dockable Imaging workspace (the core)

Replace the fixed splitter layout of `ImagingPage` with a Qt-native docking
workspace:

- The page hosts an internal `QMainWindow` (widget-mode) whose central widget
  is the FitsViewer + stats strip; every current dock becomes a real
  `QDockWidget`: Camera, Mount, Focuser (+V-curve), Filter wheel, Histogram/
  Display, Sequence, Log, Statistics (new), Light curve (from the photometry
  window's plot).
- A slim panel-toggle toolbar above the workspace (NINA's top strip): one
  checkable icon per panel; closing a dock unchecks it and vice-versa.
- Docks are movable, resizable, closable, **floatable** (multi-monitor:
  drag the light curve or the sequence to screen 2).
- Layout persistence per profile: `QMainWindow.saveState()` into config
  (`ui.imaging.layout`), restore at startup; "Reset layout" action kept.
- Defaults: image center, Camera right, Sequence bottom (current WS6 dock),
  Log tabbed with Sequence, everything else hidden — sober by default,
  dense on demand.

Files: `imaging_page.py` (layout rework), new `argos/ui/widgets/dock_host.py`
(QDockWidget factory with themed title bars), `statusbar/theme` untouched.

### WS9b — Statistics + trend panels (NINA parity for measuring)

- **Statistics dock**: the per-frame numbers as a compact 2-column grid
  (Mean/Median/StdDev/MAD/Min/Max/#Stars/HFD/FWHM/ecc + bit depth) — data
  already computed by `PreviewProcessor`/`frame_metrics`; today only 6 of
  them fit in the thin strip.
- **HFD History dock**: the sparkline currently buried in the focuser dock
  becomes its own toggleable panel (trend + #stars overlay); the focuser
  dock keeps the V-curve.
- **Image History strip** (later, optional): thumbnails of the last N subs.

### WS9c — Theme system + profiles

- `theme.py` becomes parameterized: a `Palette` dataclass (bg, surfaces,
  border, fg, accent, semantic colors) → the QSS is generated from it.
- Preset palettes: the current equilux warm-grey, a NINA-like charcoal+teal,
  a high-contrast, a red-light night mode (every color derived from red —
  the astronomy killer feature NINA lacks).
- Settings → Appearance: preset picker + accent color override; applies at
  runtime (`app.setStyleSheet` regenerate), stored in `ui.theme.*`.
- (Later) UI profiles: named (layout + theme + sequence preset) bundles.

## Non-goals

- No plugin system (NINA's is out of scope).
- No per-color swatch editor in v1 — presets + accent override first.
- The 4-mode navigation (Equipment/Capture/Analyze/Settings) stays; the
  customization happens INSIDE Capture.

## Order

WS9a is the structural piece and should land before WS7's light-curve dock
(so the curve arrives as a dock, not another fixed splitter). WS9b rides on
it. WS9c is independent and can go last.
