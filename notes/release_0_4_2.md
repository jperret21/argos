# Argos 0.4.2 — photometry corrections

> Branch: `release/0.4.2`, cut from `main` with `release/0.4.1` merged in.
> Last updated: 2026-09-09.

A patch release with no new features. It exists because writing the 0.4.1
documentation against the source turned up five measurement defects, none of
which were visible from the interface — the curve looked the same, the file
looked the same, and the numbers were wrong.

If you have exports from 0.4.1 or earlier, **three of the five affect files you
already hold**. Re-running the batch measurement on the saved frames
regenerates them correctly.

---

## What was wrong

| Defect | Effect on your data | Affects old exports |
|---|---|---|
| Offline batch photometry used an electron gain of **1.0** whenever `camera.egain_table` was empty — the default | ADU treated as electrons: every batch SNR and every formal error wrong by the gain (1.723 e⁻/ADU for an IMX585 at gain 80) | **yes** |
| A point was emitted only when the relative-flux ratio existed | A run whose comparisons were all flagged *suspect* silently lost good differential magnitudes — no row, no note | **yes** |
| `comps_used` reported the flux-ratio ensemble | The wrong ensemble size stated beside every `mag` | **yes** |
| The *suspect* flag never reached the export | Measured, plotted, then dropped: a hot pixel drifting through an aperture left no trace in the file | file only |
| Airmass came from the mount's last reported altitude | Sampled at an arbitrary instant while the point is timed at the exposure midpoint | file only |

The ratio path rejects *suspect* comparisons and the magnitude path does not,
which is why the first three interact: the same flag that shrank one ensemble
also decided whether a row existed at all.

## What changed

- Offline gain falls back to the sensor reference, as the live path already
  did. The two paths now resolve the same $g$ for the same frame.
- A point is kept when **either** product exists. Only a frame that produced
  neither a magnitude nor a ratio is dropped.
- `comps_used` counts the magnitude ensemble; the ratio's own count is exported
  beside it as the new `relative_comps_used` rather than in its place.
- `suspect` is a column. It still removes nothing — the observer decides.
- New `airmass_at()` derives airmass from the target's own coordinates at the
  point's JD. The frame-level value remains the fallback when no site is set.

Both the live and the offline batch paths carried copies of three of these
defects. They now share `airmass_at()` rather than each holding an inline copy,
so they cannot drift apart again.

## Deliberately not changed

Two items were judgement calls about the science, not bugs, and are documented
rather than silently altered:

- **The no-FWHM aperture is 7.5 green px** (~56″ on an S30 Pro), not the 4 px
  floor three docstrings claimed. Widening or narrowing it changes a
  measurement, so the arithmetic is untouched and pinned by a test; the
  comments now state what it actually does.
- **`camera.linearity_max_adu = 50000`** cannot be reconciled with the
  project's own EGAIN/FULLWELL tables at any shipped gain, so the saturation
  flag effectively never fires. Resolving it needs a **gain measured from a
  pair of flats**, not a guess. Recorded as an open defect.

## Also

- Alpaca docstrings called port 4700 the default; it is the native JSON-RPC
  port. These are published through autodoc and contradicted the architecture
  page.
- The Plan screen's heading said "Sequencer" while the sidebar said "Plan".
- Splash typo: "Devellloped".

## State of the branch

- 514 tests pass, 45 skipped; `ruff` and `black` clean.
- Sphinx builds with `-W` and no warnings.
- The documentation now describes 0.4.2 behaviour, with a *Before 0.4.2* box
  at each of the two places where an old file reads differently
  (`differential_photometry` §3.3 and §8).

## Before tagging

- [ ] Build the macOS DMG and the Debian package, tag `v0.4.2`.
- [ ] Update the download names and the release-tag links in `README.md`,
      `docsrc/install.md` and the public site (`docs/install.html`,
      `docs/index.html`) — they still point at the 0.4.1 artefacts on purpose,
      because those are the files that currently exist.
