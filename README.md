# Argos

**Differential photometry for the Seestar S30 Pro.**  
From raw Bayer frames to AAVSO-ready light curves — on your laptop, in real time.

> ⌘ Early development. Brewing since 2024.  
> Not ready for general use — but getting there.

---

The Seestar S30 Pro is a clever little telescope. Its native app is fine for
eyepiece replacement, but it saves FITS files with almost no metadata and
offers zero scientific workflow beyond "save a JPEG". Argos fills the gap:
ASCOM Alpaca control, science-grade FITS headers, live star detection,
aperture photometry, and — eventually — full ensemble differential light
curves ready for AAVSO submission.

Why the name? **Argos** was the hundred-eyed giant of Greek myth, the
all-seeing watcher. A fitting guardian for a piece of software that watches
the sky.

---

### Status · what works today

| Telescope control (Alpaca) | ✅ |
| Manual jogging (native API) | ✅ |
| Live preview loop | ✅ |
| FITS export (16-bit, science headers) | ✅ |
| Auto-discovery (UDP) | ✅ |
| Star detection & focus metrics (HFD, FWHM) | ✅ |
| Aperture photometry | ✅ |
| ASTAP plate solving | ✅ |
| Sequencer (multi-step plans) | ✅ |
| Ensemble differential photometry | ✅ |
| AAVSO light-curve export | ✅ |
| Autofocus routines | 🚧 |
| Filter wheel support | 🚧 |

---

### Try it

```bash
brew install uv
git clone https://github.com/jperret21/argos.git
cd argos
uv sync --extra dev
uv run python main.py
```

No telescope? The app works against the ASCOM Alpaca simulator —
see [`docs/simulator_testing.md`](docs/simulator_testing.md).

---

MIT License.
