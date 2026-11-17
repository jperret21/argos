"""Build web/src/design/icon-sheet.html, the static review page of the ARGOS icon set.

Usage (from the repository root, standard library only):

    python web/src/design/tools/build_icon_sheet.py

Every SVG of web/src/design/icons/ is inlined at build time, so the page needs no
script loader and no network: open it from disk, or through the Vite dev server
(http://localhost:<port>/src/design/icon-sheet.html) to get the bundled Plex fonts,
which browsers refuse to load from file:// pages. Colours come only from
tokens.css (linked relatively), so the theme switcher shows each icon exactly as
the app will. Append #charcoal or #night-red to the URL to open a given theme.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from pathlib import Path

DESIGN = Path(__file__).resolve().parent.parent
ICONS = DESIGN / "icons"
OUT = DESIGN / "icon-sheet.html"

SIZES = (16, 20, 24, 48)

# The icons the spike screen needs (web UI contract).
SPIKE = set(
    "connect disconnect simulator capture live stop goto park unpark tracking focus-in "
    "focus-out zoom-in zoom-out zoom-fit zoom-1to1 stretch-auto stretch-reset histogram "
    "crosshair plate-solve settings theme nav-connection nav-imaging nav-sequencer "
    "nav-analyze nav-configuration".split()
)

# Review order: by the observer's task, not alphabetically.
CATEGORIES: list[tuple[str, list[str]]] = [
    ("Navigation rail", "nav-connection nav-imaging nav-sequencer nav-analyze nav-configuration"),
    (
        "Equipment and connection",
        "connect disconnect simulator discover network mount camera filter-wheel focuser",
    ),
    ("Acquisition and transport", "capture live start pause stop abort"),
    (
        "Mount",
        "goto park unpark tracking sync center-target jog-pad jog-north jog-south jog-west "
        "jog-east",
    ),
    ("Focus", "focus-in focus-out focus-move autofocus focus-metrics"),
    (
        "Image viewer",
        "zoom-in zoom-out zoom-fit zoom-fill zoom-1to1 stretch-auto stretch-reset histogram "
        "crosshair loupe saturation region-stats statistics",
    ),
    (
        "Field, catalogues and planning",
        "plate-solve plate-solve-auto catalogue sky-grid field-stars variable-star galaxy "
        "nebula exoplanet other-objects labels planetarium visibility transit",
    ),
    (
        "Photometry and analysis",
        "photometry target-star comparison-star check-star recommend-comparisons "
        "comparison-quality light-curve error-bars relative-flux session-metrics "
        "rerun-photometry frames metadata inspector",
    ),
    (
        "Files and data",
        "open-image open-session open-file save export export-aavso copy browse search site "
        "bookmark",
    ),
    ("Lists and editing", "add duplicate remove move-up move-down clear close refresh"),
    (
        "Layout and panels",
        "add-plot panels arrange layout-tile layout-reset panel-float panel-dock disclosure",
    ),
    ("Application", "log watch attention settings theme help about support-bundle quit"),
]
CATEGORIES = [(name, ids.split()) for name, ids in CATEGORIES]

CSS = """
*, *::before, *::after { box-sizing: border-box; }
html { background: var(--bg); color-scheme: dark; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: var(--weight-regular) var(--text-m) / var(--leading-normal) var(--font-ui);
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1360px; margin: 0 auto; padding: 0 var(--space-6) var(--space-6); }
header.top {
  position: sticky; top: 0; z-index: var(--z-sticky);
  background: var(--bg); border-bottom: 1px solid var(--border);
}
.top .wrap { display: flex; align-items: center; gap: var(--space-5); padding-block: var(--space-4); flex-wrap: wrap; }
.brand { display: flex; align-items: center; gap: var(--space-3); color: var(--fg); }
.brand .mark { color: var(--accent); display: inline-flex; }
.brand .mark svg { width: 28px; height: 28px; }
.brand h1 { margin: 0; font-size: var(--text-xl); font-weight: var(--weight-semibold); letter-spacing: -0.02em; }
.brand p { margin: 0; color: var(--text-muted); font-size: var(--text-s); }
.controls { margin-left: auto; display: flex; gap: var(--space-4); flex-wrap: wrap; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--radius-s); overflow: hidden; }
.seg span { padding: 0 var(--space-3); align-self: center; color: var(--text-muted);
  font: var(--weight-medium) var(--text-2xs) / 1 var(--font-mono); text-transform: uppercase; letter-spacing: var(--tracking-caps); }
.seg button {
  font: var(--weight-medium) var(--text-s) / 1 var(--font-ui); color: var(--text-muted);
  background: transparent; border: 0; border-left: 1px solid var(--border-soft);
  height: 30px; padding: 0 var(--space-4); cursor: pointer;
}
.seg button:hover { background: var(--hover-bg); color: var(--fg); }
.seg button[aria-pressed='true'] { background: var(--toggled-bg); color: var(--toggled-fg); box-shadow: inset 0 -2px 0 var(--toggled-border); }
button:focus-visible { outline: var(--focus-ring-w) solid var(--focus-ring); outline-offset: var(--focus-ring-offset); }

.intro { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--space-4); margin: var(--space-6) 0; }
.fact { border: 1px solid var(--border-soft); border-radius: var(--radius-m); padding: var(--space-4); background: var(--bg-2); }
.fact b { display: block; font: var(--weight-medium) var(--text-xl) / 1.1 var(--font-mono); font-variant-numeric: var(--numeric); }
.fact span { color: var(--text-muted); font-size: var(--text-s); }

h2 { font-size: var(--text-l); font-weight: var(--weight-semibold); margin: var(--space-6) 0 var(--space-3);
  display: flex; align-items: baseline; gap: var(--space-3); }
h2 small { color: var(--text-muted); font: var(--weight-medium) var(--text-2xs) / 1 var(--font-mono); letter-spacing: var(--tracking-caps); text-transform: uppercase; }

/* In-context strip */
.context { display: grid; grid-template-columns: 92px 1fr; border: 1px solid var(--border); border-radius: var(--radius-m); overflow: hidden; }
.rail { background: var(--bg-2); border-right: 1px solid var(--border); padding: var(--space-3) 0; display: flex; flex-direction: column; gap: var(--space-1); }
.rail div { position: relative; display: flex; flex-direction: column; align-items: center; gap: var(--space-1);
  padding: var(--space-2) 0; color: var(--fg-muted); font: var(--weight-medium) var(--text-xs) / 1.2 var(--font-ui); }
.rail div span { color: var(--text-muted); }
.rail div svg { width: var(--icon-l); height: var(--icon-l); }
.rail .sel { background: var(--surface); color: var(--toggled-fg); }
.rail .sel span { color: var(--toggled-fg); }
.rail .sel::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent); }
.panes { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-4); }
.toolbar { display: flex; flex-wrap: wrap; gap: var(--space-4); align-items: center; }
.group { display: inline-flex; gap: var(--space-1); padding-right: var(--space-4); border-right: 1px solid var(--border-soft); }
.group:last-child { border-right: 0; }
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
  height: var(--control-h-m); min-width: var(--control-h-m); padding: 0 var(--space-2);
  border: 1px solid transparent; border-radius: var(--radius-s); background: transparent;
  color: var(--fg-muted); font: var(--weight-medium) var(--text-m) / 1 var(--font-ui);
}
.btn svg { width: var(--icon-m); height: var(--icon-m); }
.btn.hover { background: var(--hover-bg); color: var(--fg); }
.btn.on { background: var(--toggled-bg); color: var(--toggled-fg); border-color: var(--toggled-border); }
.btn.secondary { color: var(--fg); border-color: var(--border); padding: 0 var(--space-4) 0 var(--space-3); }
.btn.primary { background: var(--primary-bg); color: var(--primary-fg); border-color: var(--primary-border); padding: 0 var(--space-4) 0 var(--space-3); }
.btn.primary.hover { background: var(--primary-bg-hover); color: var(--primary-fg-hover); }
.btn.danger { color: var(--fg); border-color: var(--danger); padding: 0 var(--space-4) 0 var(--space-3); }
.btn.danger svg { color: var(--danger); }
.btn.danger.hover { background: var(--danger); color: var(--on-danger); }
.btn.danger.hover svg { color: var(--on-danger); }
.btn.disabled { color: var(--fg-disabled); }
.caption { color: var(--text-muted); font-size: var(--text-xs); }
.statusline { display: flex; gap: var(--space-5); flex-wrap: wrap; font: var(--text-s) / 1.4 var(--font-mono); color: var(--text-muted); }
.statusline i { display: inline-block; width: 8px; height: 8px; border-radius: var(--radius-round); margin-right: var(--space-2); vertical-align: 1px; }

/* Icon cards */
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: var(--space-3); }
.card { border: 1px solid var(--border-soft); border-radius: var(--radius-m); background: var(--bg); padding: var(--space-4) var(--space-4) var(--space-3); }
.card:hover { border-color: var(--border); }
.renders { display: flex; align-items: flex-end; gap: var(--space-5); color: var(--ink, var(--fg)); min-height: 66px; }
.renders figure { margin: 0; display: flex; flex-direction: column; align-items: center; gap: var(--space-1); }
.renders svg { display: block; }
.renders figcaption { color: var(--text-muted); font: var(--text-2xs) / 1 var(--font-mono); font-variant-numeric: var(--numeric); }
.s16 { width: 16px; height: 16px; } .s20 { width: 20px; height: 20px; }
.s24 { width: 24px; height: 24px; } .s48 { width: 48px; height: 48px; }
.meta { margin-top: var(--space-3); border-top: 1px solid var(--border-soft); padding-top: var(--space-2); }
.id { font: var(--weight-medium) var(--text-s) / 1.3 var(--font-mono); color: var(--fg); }
.label { color: var(--text-muted); font-size: var(--text-xs); line-height: 1.35; margin-top: 2px; min-height: 15px; }
.chips { display: flex; gap: var(--space-1); flex-wrap: wrap; margin-top: var(--space-2); }
.chip { font: var(--weight-medium) var(--text-2xs) / 1 var(--font-mono); letter-spacing: 0.02em; color: var(--text-muted);
  border: 1px solid var(--border-soft); border-radius: var(--radius-s); padding: 3px 5px; }
.chip.spike { color: var(--toggled-fg); border-color: var(--toggled-border); }
.chip.key { color: var(--fg); border-color: var(--border); }
kbd { font: var(--weight-medium) var(--text-2xs) / 1 var(--font-mono); color: var(--fg); background: var(--surface);
  border: 1px solid var(--border); border-radius: var(--radius-s); padding: 3px 5px; }
footer { margin-top: var(--space-6); padding-top: var(--space-4); border-top: 1px solid var(--border-soft); color: var(--text-muted); font-size: var(--text-s); }
footer code { font-family: var(--font-mono); color: var(--fg); }
@media (max-width: 720px) {
  .wrap { padding: 0 var(--space-4) var(--space-5); }
  .context { grid-template-columns: 1fr; }
  .rail { flex-direction: row; overflow-x: auto; }
  .rail div { min-width: 76px; }
}
"""

SCRIPT = """
(function () {
  var themes = ['observatory', 'charcoal', 'night-red'];
  var inks = { fg: 'var(--fg)', muted: 'var(--fg-muted)', accent: 'var(--toggled-fg)' };
  function setTheme(t) {
    if (themes.indexOf(t) < 0) t = 'observatory';
    document.documentElement.setAttribute('data-theme', t);
    document.querySelectorAll('[data-set-theme]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-set-theme') === t));
    });
    try { localStorage.setItem('argos-icon-sheet-theme', t); } catch (e) {}
  }
  function setInk(k) {
    document.documentElement.style.setProperty('--ink', inks[k] || inks.fg);
    document.querySelectorAll('[data-set-ink]').forEach(function (b) {
      b.setAttribute('aria-pressed', String(b.getAttribute('data-set-ink') === k));
    });
  }
  var initial = location.hash.slice(1);
  if (themes.indexOf(initial) < 0) {
    try { initial = localStorage.getItem('argos-icon-sheet-theme') || ''; } catch (e) { initial = ''; }
  }
  setTheme(initial);
  document.addEventListener('DOMContentLoaded', function () {
    setTheme(document.documentElement.getAttribute('data-theme'));
    setInk('fg');
    document.querySelectorAll('[data-set-theme]').forEach(function (b) {
      b.addEventListener('click', function () { setTheme(b.getAttribute('data-set-theme')); });
    });
    document.querySelectorAll('[data-set-ink]').forEach(function (b) {
      b.addEventListener('click', function () { setInk(b.getAttribute('data-set-ink')); });
    });
  });
})();
"""


def load_svg(icon_id: str, css_class: str = "") -> str:
    """Inline one icon: drop the XML whitespace, add a size class and aria-hidden."""
    text = (ICONS / f"{icon_id}.svg").read_text(encoding="utf-8").strip()
    text = re.sub(r">\s+<", "><", text)
    attrs = ' aria-hidden="true" focusable="false"'
    if css_class:
        attrs += f' class="{css_class}"'
    return text.replace("<svg ", f"<svg{attrs} ", 1)


def clean_label(labels: list[str], icon_id: str) -> str:
    """First Qt label that has words, without the text glyphs the Qt buttons used
    as icons (the colour emoji among them would break the Night Red rule)."""
    for text in labels:
        kept = "".join(
            " " if ord(c) > 0x2000 and unicodedata.category(c) in ("So", "Sm") or c in "＋－" else c
            for c in text
        )
        kept = " ".join(kept.split())
        if re.search(r"[A-Za-z]", kept):
            return kept
    cleaned = [" ".join(t.split()) for t in labels if re.search(r"\w", t)]
    return cleaned[0] if cleaned else icon_id.replace("-", " ").capitalize()


def card(entry: dict) -> str:
    icon_id = entry["id"]
    renders = "".join(
        f'<figure>{load_svg(icon_id, f"s{s}")}<figcaption>{s}</figcaption></figure>' for s in SIZES
    )
    label = html.escape(clean_label(entry.get("labels", []), icon_id))
    chips = [f'<span class="chip">{html.escape(entry.get("display", "icon"))}</span>']
    if icon_id in SPIKE:
        chips.append('<span class="chip spike">spike</span>')
    if entry.get("keystone"):
        chips.append('<span class="chip key">keystone</span>')
    if entry.get("shortcut"):
        chips.append(
            f'<kbd title="{entry.get("shortcut_origin", "")}">{html.escape(entry["shortcut"])}</kbd>'
        )
    concept = html.escape(entry.get("concept", ""), quote=True)
    return (
        f'<article class="card" id="{icon_id}" title="{concept}">'
        f'<div class="renders">{renders}</div>'
        f'<div class="meta"><div class="id">{icon_id}</div><div class="label">{label}</div>'
        f'<div class="chips">{"".join(chips)}</div></div></article>'
    )


def btn(icon_id: str, cls: str = "", text: str = "", title: str = "") -> str:
    inner = load_svg(icon_id) + (f"<span>{html.escape(text)}</span>" if text else "")
    return f'<span class="btn {cls}" title="{html.escape(title or text or icon_id)}">{inner}</span>'


def context_strip() -> str:
    rail = "".join(
        f'<div class="{"sel" if i == 1 else ""}">{load_svg(icon_id)}<span>{name}</span></div>'
        for i, (icon_id, name) in enumerate(
            [
                ("nav-connection", "Connection"),
                ("nav-imaging", "Observe"),
                ("nav-sequencer", "Plan"),
                ("nav-analyze", "Review"),
                ("nav-configuration", "Settings"),
            ]
        )
    )
    viewer = (
        '<div class="group">'
        + btn("zoom-in", title="Zoom in (+)")
        + btn("zoom-out", "hover", title="Zoom out (-), hover")
        + btn("zoom-fit", title="Fit to window (F)")
        + btn("zoom-fill", title="Fill the viewer (Shift+F)")
        + btn("zoom-1to1", title="1:1 (1)")
        + '</div><div class="group">'
        + btn("stretch-auto", "on", title="Auto stretch (A), toggled")
        + btn("stretch-reset", title="Reset stretch")
        + btn("histogram", title="Adjust image (H)")
        + '</div><div class="group">'
        + btn("crosshair", "on", title="Crosshair (X), toggled")
        + btn("plate-solve", title="Identify field (S)")
        + btn("sky-grid", title="Coordinate grid (G)")
        + btn("loupe", "disabled", title="Loupe, disabled")
        + "</div>"
    )
    acquisition = (
        '<div class="group">'
        + btn("capture", title="Take shot (E)")
        + btn("live", title="Live (V)")
        + btn("stop", "hover", title="Stop")
        + '</div><div class="group">'
        + btn("focus-out", title="Focus out ([)")
        + btn("focus-in", title="Focus in (])")
        + btn("autofocus", title="Autofocus")
        + '</div><div class="group">'
        + btn("tracking", "on", title="Tracking (T), on")
        + btn("goto", "primary", "Slew")
        + btn("park", "secondary", "Park")
        + btn("abort", "danger", "Abort")
        + "</div>"
    )
    hovered = (
        '<div class="group">'
        + btn("connect", "primary hover", "Connect", "Connect, hover")
        + btn("disconnect", "secondary", "Disconnect")
        + btn("simulator", "secondary", "Simulator")
        + btn("stop", "danger hover", "Stop sequence", "Stop sequence, hover")
        + "</div>"
    )
    status = (
        '<div class="statusline">'
        '<span><i style="background: var(--status-ok)"></i>Mount ready</span>'
        '<span><i style="background: var(--status-busy)"></i>Slewing</span>'
        '<span><i style="background: var(--status-error)"></i>Focuser offline</span>'
        '<span><i style="background: var(--status-idle)"></i>Filter wheel idle</span>'
        "</div>"
    )
    return (
        '<section aria-label="Icons in context"><h2>In context <small>rail 24 px, toolbars 20 px'
        '</small></h2><div class="context"><nav class="rail" aria-label="Rail preview">'
        f'{rail}</nav><div class="panes"><div class="toolbar">{viewer}</div>'
        f'<div class="toolbar">{acquisition}</div><div class="toolbar">{hovered}</div>'
        f'{status}<div class="caption">Ghost buttons rest in --fg-muted, hover in --fg, toggled in '
        "--toggled-fg; primary, secondary and danger as in BRAND.md section 8. Static mock-up: "
        "states are drawn, not interactive.</div></div></div></section>"
    )


def main() -> None:
    inventory = json.loads((DESIGN / "icon-inventory.json").read_text(encoding="utf-8"))
    by_id = {e["id"]: e for e in inventory}
    on_disk = sorted(p.stem for p in ICONS.glob("*.svg"))
    listed = [i for _, ids in CATEGORIES for i in ids]
    missing = sorted(set(on_disk) - set(listed))
    unknown = sorted(set(listed) - set(by_id))
    if missing or unknown or len(listed) != len(set(listed)):
        raise SystemExit(f"category map out of date: missing {missing}, unknown {unknown}")
    sections = []
    for name, ids in CATEGORIES:
        cards = "".join(card(by_id[i]) for i in ids)
        sections.append(
            f"<section><h2>{html.escape(name)} <small>{len(ids)} icons</small></h2>"
            f'<div class="grid">{cards}</div></section>'
        )
    facts = [
        (str(len(on_disk)), "icons, one SVG each, currentColor only"),
        (f"{len(SPIKE)}", "needed by the spike screen (marked spike)"),
        ("24 / 1.5", "unit grid / stroke: 1 px at 16, 1.5 px at 24"),
        ("16 20 24", "px display sizes: --icon-s, --icon-m, --icon-l"),
    ]
    intro = "".join(f'<div class="fact"><b>{a}</b><span>{b}</span></div>' for a, b in facts)
    theme_buttons = "".join(
        f'<button type="button" data-set-theme="{t}" aria-pressed="false">{n}</button>'
        for t, n in (
            ("observatory", "Observatory"),
            ("charcoal", "Charcoal"),
            ("night-red", "Night Red"),
        )
    )
    ink_buttons = "".join(
        f'<button type="button" data-set-ink="{k}" aria-pressed="false">{n}</button>'
        for k, n in (("fg", "Text"), ("muted", "Muted"), ("accent", "Toggled"))
    )
    page = f"""<!doctype html>
<!-- Generated by tools/build_icon_sheet.py from icons/*.svg and icon-inventory.json.
     Do not edit by hand: change an icon, then run the script again. -->
<html lang="en" data-theme="observatory">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARGOS icon set</title>
<link rel="stylesheet" href="./tokens.css">
<script>{SCRIPT}</script>
<style>{CSS}</style>
</head>
<body>
<header class="top"><div class="wrap">
<div class="brand"><span class="mark">{load_svg("about")}</span>
<div><h1>ARGOS icon set</h1><p>Review sheet of the web UI icons, drawn on the ARGOS grammar (BRAND.md section 6).</p></div></div>
<div class="controls">
<div class="seg" role="group" aria-label="Theme"><span>Theme</span>{theme_buttons}</div>
<div class="seg" role="group" aria-label="Icon colour"><span>Ink</span>{ink_buttons}</div>
</div></div></header>
<main class="wrap">
<div class="intro">{intro}</div>
{context_strip()}
{"".join(sections)}
<footer>Each card shows the icon at 16, 20, 24 and 48 px, its id, its first Qt label, its default
display (<code>icon</code> or <code>icon+label</code>) and its shortcut. Hover a card for the concept.
Source: <code>web/src/design/icons/&lt;id&gt;.svg</code>; brief: <code>icon-inventory.json</code>;
rules: <code>BRAND.md</code>.</footer>
</main>
</body>
</html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({len(page) // 1024} KiB, {len(on_disk)} icons)")


if __name__ == "__main__":
    main()
