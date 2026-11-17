"""Build web/screenshots/index.html, the gallery of the web UI screenshots.

Usage (from the repository root, standard library only):

    python web/scripts/build_screenshot_gallery.py

Each milestone is a folder web/screenshots/<YYYY-MM-DD>_<slug>/ holding PNG files and a
manifest.json:

    {
      "title": "Observe screen, first version",
      "date": "2026-11-01",
      "summary": "One paragraph on what this milestone shows.",
      "shots": [
        {"file": "live-1440x900-observatory.png",
         "caption": "What the screenshot shows and why it matters.",
         "tags": ["observe", "observatory", "1440x900"]}
      ]
    }

PNG files listed in no manifest still appear, captioned with their file name. The page is
self-contained (no network), newest milestone first, with a tag filter. The images and
index.html are not tracked by git (see web/.gitignore); the manifests are, so the history
of milestones stays in the repository.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "screenshots"


def load_milestones() -> list[dict]:
    milestones = []
    for folder in sorted(p for p in ROOT.iterdir() if p.is_dir()):
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        shots = [s for s in manifest.get("shots", []) if (folder / s["file"]).exists()]
        listed = {s["file"] for s in shots}
        for png in sorted(folder.rglob("*.png")):
            rel = png.relative_to(folder).as_posix()
            if rel not in listed:
                shots.append({"file": rel, "caption": rel, "tags": []})
        milestones.append(
            {
                "folder": folder.name,
                "title": manifest.get("title", folder.name),
                "date": manifest.get("date", folder.name[:10]),
                "summary": manifest.get("summary", ""),
                "shots": shots,
            }
        )
    return sorted(milestones, key=lambda m: m["folder"], reverse=True)


def render(milestones: list[dict]) -> str:
    tags = sorted({t for m in milestones for s in m["shots"] for t in s.get("tags", [])})
    tag_buttons = "".join(
        f'<button type="button" data-tag="{html.escape(t)}">{html.escape(t)}</button>' for t in tags
    )
    sections = []
    for m in milestones:
        cards = []
        for s in m["shots"]:
            src = f'{html.escape(m["folder"])}/{html.escape(s["file"])}'
            shot_tags = " ".join(html.escape(t) for t in s.get("tags", []))
            cards.append(
                f'<figure data-tags="{shot_tags}"><a href="{src}" target="_blank">'
                f'<img src="{src}" loading="lazy" alt="{html.escape(s["caption"])}"></a>'
                f'<figcaption>{html.escape(s["caption"])}'
                f'<span class="tags">{shot_tags}</span></figcaption></figure>'
            )
        sections.append(
            f'<section><h2>{html.escape(m["title"])} <small>{html.escape(m["date"])}</small></h2>'
            f'<p>{html.escape(m["summary"])}</p><div class="grid">{"".join(cards)}</div></section>'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ARGOS web UI screenshots</title>
<style>
  :root {{ color-scheme: dark; --bg: #191b1f; --surface: #22262c; --border: #343c45;
    --fg: #e8e5df; --muted: #a9a59c; --accent: #c49a3c; }}
  body {{ margin: 0; background: var(--bg); color: var(--fg);
    font: 14px/1.5 "IBM Plex Sans", "Helvetica Neue", "Segoe UI", sans-serif; }}
  header, section {{ padding: 16px 24px; }}
  header {{ border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--bg); z-index: 1; }}
  h1 {{ font-size: 18px; margin: 0 0 8px; }}
  h2 {{ font-size: 16px; margin: 8px 0; }} h2 small {{ color: var(--muted); font-weight: 400; }}
  p {{ color: var(--muted); max-width: 900px; margin: 0 0 12px; }}
  .filters button {{ background: var(--surface); color: var(--fg); border: 1px solid var(--border);
    border-radius: 2px; padding: 2px 8px; margin: 0 4px 4px 0; font: inherit; font-size: 12px; cursor: pointer; }}
  .filters button[aria-pressed="true"] {{ border-color: var(--accent); color: var(--accent); }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }}
  figure {{ margin: 0; background: var(--surface); border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }}
  figure img {{ display: block; width: 100%; height: auto; }}
  figcaption {{ padding: 8px 10px; font-size: 13px; }}
  .tags {{ display: block; color: var(--muted); font: 11px "IBM Plex Mono", Menlo, monospace; margin-top: 4px; }}
  figure[hidden] {{ display: none; }}
</style>
</head>
<body>
<header><h1>ARGOS web UI screenshots</h1><div class="filters">{tag_buttons}</div></header>
{"".join(sections)}
<script>
  const active = new Set();
  document.querySelectorAll('.filters button').forEach((b) => b.addEventListener('click', () => {{
    const t = b.dataset.tag;
    active.has(t) ? active.delete(t) : active.add(t);
    b.setAttribute('aria-pressed', active.has(t));
    document.querySelectorAll('figure').forEach((f) => {{
      const own = f.dataset.tags.split(' ');
      f.hidden = [...active].some((x) => !own.includes(x));
    }});
  }}));
</script>
</body>
</html>
"""


def main() -> None:
    ROOT.mkdir(exist_ok=True)
    milestones = load_milestones()
    (ROOT / "index.html").write_text(render(milestones))
    count = sum(len(m["shots"]) for m in milestones)
    print(f"wrote {ROOT / 'index.html'} ({len(milestones)} milestones, {count} screenshots)")


if __name__ == "__main__":
    main()
