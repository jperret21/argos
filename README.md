# Argos

**Desktop astrophotography & differential photometry for the ZWO Seestar S30 Pro.**
*The hundred-eyed watcher — from raw frames to calibrated light curves, on your laptop.*

> **Field-validation alpha (0.4.1).** Suitable for technically confident
> testers who retain their raw FITS and review results independently; not yet
> a general-public or unattended-observatory release.

The Seestar S30 Pro is a formidable little sky-explorer, and its app is a pleasure
to use — but it is built for *looking*, not for *measuring*. The FITS files it saves
are missing the metadata real science needs, and there is no measurement workflow
beyond a pretty picture. Argos picks up from there and turns this remarkable
telescope into a scientific instrument: it completes the FITS headers, detects and
measures every star, solves astrometry on each frame, and builds differential light
curves — frame by frame, as the light lands.

**Why "Argos"?** In Greek myth, Argos Panoptes was the giant of a hundred eyes, the
all-seeing watcher who never closed them all at once. A fitting name for software
that keeps watch over the sky.

## The pipeline

From raw photons to a calibrated light curve, all running locally:

**Acquisition & control**
- ASCOM Alpaca mount control — GoTo, tracking, park — plus the native Seestar jog
  API for the moves the firmware won't expose over Alpaca
- Live exposure loop with linear / log / asinh auto-stretch (display only; the linear
  frame written to disk is never altered)
- Multi-step sequencer (Light / Dark / Flat / Bias)
- Filter wheel — the internal Seestar wheel (Dark / IR / LP) and Alpaca wheels
- Slew the mount straight from Stellarium over the Telescope Protocol v1.0
- UDP auto-discovery of the Seestar on the local network

**Frames & data**
- Science-grade 16-bit FITS — fills in the headers the Seestar omits (exposure
  mid-times, gain, airmass, Moon separation), ready for Siril, PixInsight, AstroImageJ
- All measurement runs on the raw green pixels — no demosaic, no interpolation, so
  every value is signal the camera actually recorded

**Astrometry**
- Star detection at 5σ over a robust sky estimate, with per-star HFD, FWHM and
  eccentricity for focus and frame-quality metrics
- ASTAP plate solving — a full WCS recovered on every sub, so any pixel maps to real
  sky coordinates

**Photometry**
- Aperture photometry — circular aperture + median sky annulus → background-subtracted
  flux, instrumental magnitude and a CCD-equation uncertainty, with a saturation flag
- Ensemble differential photometry — zero-point from a comparison ensemble; the
  uncertainty combines the target's photon noise with the ensemble scatter
  (Honeycutt 1992)
- AAVSO VSX / VSP catalog — variable targets and comparison stars by cone search on
  the solved field; comparisons auto-ranked by proximity and matched brightness
- Light-curve export — per-target CSV: JD_UTC / BJD_TDB, magnitude and error, airmass
  (Kasten–Young), FWHM, sky background, comparisons used

## On the way

- Autofocus — HFD V-curve sweep with a parabola-fit minimum (focuser control is
  already wired; the routine is landing next)

## Try it

**macOS — download the app.** Grab the `.dmg` from the
[latest release](https://github.com/jperret21/argos/releases), drag Argos into
Applications, then **right-click Argos → Open** the first time.

Argos is not signed with an Apple Developer certificate, so macOS blocks the
first launch. That is about the absence of a paid certificate, not about the
software. If macOS claims Argos "is damaged", clear the quarantine flag:

```bash
xattr -dr com.apple.quarantine /Applications/Argos.app
```

**Debian / Ubuntu (x86_64 technical preview).** A tagged release also carries
a `.deb` built and smoke-tested on Ubuntu CI. Download it, then install it with:

```bash
sudo apt install ./argos_0.4.1_amd64.deb
```

Launch **Argos** from the applications menu or run `argos`. The Linux package
is not field-validated yet; keep it to technical testing until that changes.

**From source** (macOS is the reference platform; Linux is a technical preview):

```bash
brew install uv
git clone https://github.com/jperret21/argos.git
cd argos
uv sync --extra dev
uv run python main.py
```

Plate solving needs [ASTAP](https://www.hnsky.org/astap.htm) installed
separately — Argos finds it automatically but never bundles it.

Before a first observing session, read the French
[0.4.1 field guide](docs/guide_terrain_0_4_1.md): site setup, ASTAP, connection,
planning, dockable workspaces, photometry roles, exports and the field-test checklist.

No telescope? Argos runs against the ASCOM Alpaca simulator:

```bash
# terminal 1 — mock Seestar
uv run python scripts/mock_alpaca_server.py
# terminal 2 — Argos
uv run python main.py
```

See [`docs/simulator_testing.md`](docs/simulator_testing.md) for the full guide.

## Privacy and field diagnostics

Argos has **no remote telemetry, analytics or automatic crash upload**. Target,
catalogue and site searches use the network only when the observer asks for
them. Local diagnostics are opt-in and can be disabled in **Settings → Local
diagnostics**.

For a field issue, **More → Create local support bundle…** creates a ZIP only
when requested. It contains redacted local logs and, if selected, redacted
session metadata; raw FITS, observing-site coordinates, network addresses and
observer identity are excluded. Argos never uploads the ZIP — review and share
it manually only if you choose to do so.

## CI and releases

GitHub Actions runs linting, formatting, documentation and tests on every pull
request and on every push to `main` or `release/**`.

Installers are deliberately **not** rebuilt for every commit on `main`. After a
release branch has been merged and its CI is green, create and push a version
tag, for example `v0.4.1`:

```bash
git checkout main
git pull --ff-only
git tag -a v0.4.1 -m "Argos 0.4.1"
git push origin v0.4.1
```

The release workflow then builds the macOS `.dmg` and Debian/Ubuntu `.deb`,
smoke-tests both bundles, and creates a GitHub release **draft** with the two
artifacts attached. Publishing that draft remains a deliberate human step. The
same packaging workflow can also be started manually from the
[Actions page](https://github.com/jperret21/argos/actions).

## Contributing

Argos is open source and built in the open. Issues, ideas and pull requests are all
welcome — especially from Seestar owners who want to push their data further. The
codebase is uv-managed, fully typed, and covered by tests:

```bash
uv sync --extra dev
uv run --extra dev pytest
```

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) to get started.

## License

**GNU General Public License v3.0** — see [`LICENSE`](LICENSE).

Argos links against PyQt6, which is GPL v3 (Riverbank also sells a commercial
licence). Distributing Argos as a binary means redistributing PyQt6, so the
project as a whole is GPL v3 — the same licence Siril and INDI use.

Argos does not bundle ASTAP: it is an external solver you install separately,
under its own licence.
