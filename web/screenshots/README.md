# Web UI screenshots

Progress screenshots of the new ARGOS web UI, one folder per milestone
(`<YYYY-MM-DD>_<slug>/`) with a `manifest.json` (title, date, summary, and a caption and
tags per screenshot). They track the redesign and feed the website and the documentation.

- Build the gallery: `python web/scripts/build_screenshot_gallery.py`, then open
  `web/screenshots/index.html`.
- The PNG files and `index.html` are not tracked by git (they would weigh tens of MB over
  the waves); the manifests are. Copy an optimised selection into `docs/` when a page of the
  site or of the documentation needs one.
- Every workflow that changes the UI saves its final screenshots here, at 1440x900 in the
  three themes at least.
