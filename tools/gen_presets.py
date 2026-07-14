#!/usr/bin/env python3
"""Generate the Argos logo presets as SVG (and PNG/JPG on macOS).

Mirrors the buildSVG() logic in logo-generator.html so the exported files
match exactly what the interactive generator produces.

Usage:
    python3 tools/gen_presets.py
Outputs into tools/logo-presets/ .
"""
import os
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "logo-presets")

GOLD, DARK = "#c49a3c", "#08080a"

# The four swirl arms (original artwork).
ARMS = [
    "M50 6 Q70 24 82 24 Q88 24 86 32 Q82 42 74 44",
    "M50 94 Q30 76 18 76 Q12 76 14 68 Q18 58 26 56",
    "M6 50 Q24 36 22 20 Q21 14 30 16 Q40 18 44 28",
    "M94 50 Q76 64 78 80 Q79 86 70 84 Q60 82 56 72",
]

# name, stroke, bg (None = transparent), sw, rays(opacity), inset, size, pad, raster
PRESETS = [
    ("argos-or",         GOLD,  None, 4, 1, 0.95, 1024, 0, "png"),
    ("or-sur-sombre",    GOLD,  DARK, 4, 1, 0.95, 1024, 0, "both"),
    ("monochrome-noir",  "#000000", None, 4, 1, 0.95, 1024, 0, "png"),
    ("monochrome-blanc", "#ffffff", DARK, 4, 1, 0.95, 1024, 0, "both"),
    ("favicon-32",       GOLD,  None, 4, 1, 0.95, 32,  0, "png"),
    ("favicon-64",       GOLD,  None, 4, 1, 0.95, 64,  0, "png"),
    ("icone-app-512",    DARK,  GOLD, 4, 1, 0.95, 512, 0, "both"),
    ("reseaux-1024",     GOLD,  DARK, 4, 1, 0.95, 1024, 0, "both"),
]


def build_svg(stroke, bg, sw, rays, inset, size, pad):
    inner = 100 - 2 * pad
    bg_rect = f'\n  <rect width="100" height="100" fill="{bg}"/>' if bg else ""
    arm_tf = f"translate(50 50) scale({inset}) translate(-50 -50)"
    arms = "\n".join(f'        <path d="{d}"/>' for d in ARMS)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 100 100">{bg_rect}
  <g transform="translate({pad} {pad}) scale({inner / 100})">
    <g fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="50" cy="50" r="42"/>
      <circle cx="50" cy="50" r="5" fill="{stroke}" stroke="none"/>
      <g opacity="{rays}" transform="{arm_tf}">
{arms}
      </g>
    </g>
  </g>
</svg>
'''


def main():
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(OUT)

    has_ql = shutil.which("qlmanage") is not None
    has_sips = shutil.which("sips") is not None

    for name, stroke, bg, sw, rays, inset, size, pad, raster in PRESETS:
        svg = build_svg(stroke, bg, sw, rays, inset, size, pad)
        svg_path = os.path.join(OUT, f"{name}.svg")
        with open(svg_path, "w") as f:
            f.write(svg)
        print(f"  svg  {name}.svg")

        if not has_ql:
            continue
        # Quick Look renders the SVG to <name>.svg.png at max dimension `size`.
        subprocess.run(["qlmanage", "-t", "-s", str(size), "-o", OUT, svg_path],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ql_png = os.path.join(OUT, f"{name}.svg.png")
        png_path = os.path.join(OUT, f"{name}.png")
        if os.path.exists(ql_png):
            os.replace(ql_png, png_path)
            print(f"  png  {name}.png ({size}px)")
            if raster == "both" and has_sips:
                jpg_path = os.path.join(OUT, f"{name}.jpg")
                subprocess.run(["sips", "-s", "format", "jpeg", png_path,
                                "--out", jpg_path],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print(f"  jpg  {name}.jpg")

    print(f"\nDone -> {OUT}")


if __name__ == "__main__":
    main()
