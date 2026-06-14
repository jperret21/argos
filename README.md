# SeerControl

**Desktop control software for the ZWO Seestar S30 Pro.**

This project is in **early development** — not yet ready for testing.
Goals, features, and architecture are evolving rapidly.

---

## Status

| Area | Status |
|---|---|
| Telescope control (Alpaca) | Working — GoTo, tracking, park |
| Manual jogging (native API) | Working — N/S/E/W at 3 speeds |
| Live preview | Working — continuous exposure loop |
| FITS export | Working — 16-bit with science headers |
| Auto-discovery (UDP) | Working |
| Sequencer | In progress |
| Plate solving | Planned |
| Focuser / Filter wheel | Planned |

See [STATUS.md](docs/STATUS.md) for the full project dashboard.

---

## Getting Started

```bash
# Requirements: macOS (Apple Silicon or Intel), Python 3.11+, uv

brew install uv
git clone https://github.com/jperret21/seerstar.git
cd seerstar
uv sync --extra dev
./run.sh
```

See [CONTRIBUTING.md](docs/CONTRIBUTING.md) for development setup and workflow.

---

## Project Goals

SeerControl aims to provide a **desktop-grade control interface** for the Seestar S30 Pro,
with an emphasis on:

- **Precision** — fine-grained control over telescope and camera
- **Quality** — science-grade FITS output, compatible with PixInsight, Siril, AstroImageJ
- **Openness** — built on open standards (ASCOM Alpaca, FITS) and open source

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for design decisions and module layout.

---

## License

MIT
