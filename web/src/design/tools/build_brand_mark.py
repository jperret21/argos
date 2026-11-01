"""Build the ARGOS mark files of the web design system from the official logo generator.

Usage (from the repository root, standard library only):

    python web/src/design/tools/build_brand_mark.py

The mark is never redrawn by hand. Its only source is tools/gen_presets.py, which mirrors
tools/logo-generator.html; this script calls its build_svg() with the generator's default
preset and changes nothing but the colour (currentColor, so every theme applies,
Night Red included). It writes:

- web/src/design/brand/argos-mark.svg: the mark on its own 100-unit grid, for large uses
  (splash, about dialog, empty states).
- web/src/design/icons/about.svg: the same geometry scaled into the 24-unit icon grid, so
  <Icon name="about"> shows the real logo in the navigation rail and the about entry.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DESIGN = ROOT / "web" / "src" / "design"

# The generator's default preset ("argos-or"): stroke width 4, arms fully opaque, arms inset
# 0.95, no padding. Only the colour differs.
STROKE_WIDTH, RAYS, INSET, PAD = 4, 1, 0.95, 0


def load_generator():
    spec = importlib.util.spec_from_file_location("gen_presets", ROOT / "tools" / "gen_presets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mark_body() -> str:
    """Return the generator's SVG content without its root element."""
    svg = load_generator().build_svg("currentColor", None, STROKE_WIDTH, RAYS, INSET, 100, PAD)
    match = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S)
    # Drop the blank line build_svg leaves where the optional wordmark would go.
    return "\n".join(line for line in match.group(1).splitlines() if line.strip())


def main() -> None:
    body = mark_body()
    xmlns = 'xmlns="http://www.w3.org/2000/svg"'

    brand = DESIGN / "brand"
    brand.mkdir(exist_ok=True)
    (brand / "argos-mark.svg").write_text(f'<svg {xmlns} viewBox="0 0 100 100">\n{body}\n</svg>\n')

    indented = "\n".join(f"  {line}" for line in body.splitlines())
    (DESIGN / "icons" / "about.svg").write_text(
        f'<svg {xmlns} viewBox="0 0 24 24">\n'
        f'<g transform="scale(0.24)">\n{indented}\n</g>\n</svg>\n'
    )
    print(f"wrote {brand / 'argos-mark.svg'}")
    print(f"wrote {DESIGN / 'icons' / 'about.svg'}")


if __name__ == "__main__":
    main()
