"""Sphinx configuration for Argos documentation.

The Sphinx sources live in ``docsrc/``; ``docs/`` is the hand-written showcase
and is not part of this build. ``.github/workflows/pages.yml`` builds this tree
with ``-W`` and publishes both halves together on a push to ``main``: the
showcase at ``/argos/``, this documentation at ``/argos/docs/``.

Build it from the project root as the Pages job does (warnings are errors)::

    uv run --extra docs sphinx-build -W -b html docsrc /tmp/argos-docs
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# -- Project info -----------------------------------------------------------

project = "ARGOS"
author = "J. Perret"
copyright = f"{datetime.now().year}, {author}"
# The one version: argos/__init__.py's __version__, read as text (importing
# argos here would run the package before autodoc's mocks are in place).
release = re.search(
    r'^__version__ = "([^"]+)"',
    (Path(__file__).resolve().parent.parent / "argos" / "__init__.py").read_text("utf-8"),
    re.M,
).group(1)
version = release

# -- General configuration -------------------------------------------------

extensions = [
    "myst_parser",          # MyST Markdown (.md) support
    "sphinx.ext.autodoc",   # Auto-generate API docs from docstrings
    "sphinx.ext.napoleon",  # Google/NumPy-style docstring support
    "sphinx.ext.viewcode",  # Link to source code
    "sphinx.ext.graphviz",  # DOT graph / diagram support
    "sphinx.ext.intersphinx",  # Cross-ref to Python, numpy, etc.
    "sphinx_design",        # Grids, cards, tabs, dropdowns
    "sphinx_copybutton",    # Copy button on code blocks
]

# MyST config — parse all .md files as MyST
myst_heading_anchors = 4          # auto-generate anchors down to h4
myst_enable_extensions = [
    "colon_fence",                 # ```{note} / ```{warning} directives
    "deflist",                     # definition lists
    "fieldlist",                   # field lists
    "html_image",                  # inline HTML images
    "dollarmath",                  # $inline$ and $$display$$ maths
    "amsmath",                     # align/aligned environments
    "tasklist",                    # - [ ] checkboxes
]

# autodoc — scan argos packages
sys.path.insert(0, os.path.abspath(".."))

# Custom mock for PyQt6 so pyqtSignal() doesn't produce *args signatures.
import unittest.mock as _mock

class _PyqtSignalInstance:
    """A pyqtSignal instance — Sphinx sees it as a plain object."""
    pass

class _PyqtSignal:
    """Mock for pyqtSignal — returns a plain instance."""
    def __new__(cls, *types, **kwargs):
        return _PyqtSignalInstance()

class _NamedMock(_mock.MagicMock):
    """A MagicMock shown by its dotted name (``PyQt6.QtWidgets.QPushButton``).

    autodoc renders a mocked annotation with repr(); MagicMock's own repr carries
    the object's memory address, which changes on every build.
    """

    def __repr__(self) -> str:
        return self._extract_mock_name()


_PYQT = _NamedMock(name="PyQt6")
for _sub in ("QtCore", "QtWidgets", "QtGui", "QtSvg", "QtNetwork"):
    setattr(_PYQT, _sub, _NamedMock())
    sys.modules[f"PyQt6.{_sub}"] = getattr(_PYQT, _sub)
_PYQT.QtCore.pyqtSignal = _PyqtSignal
sys.modules["PyQt6"] = _PYQT

del _mock, _PYQT  # Keep _PyqtSignal* classes in namespace for autodoc

# Other packages — mock only in autodoc's scope so Sphinx itself can use them.
autodoc_mock_imports = [
    "pyqtgraph",
    "requests",
    "astropy",
    "astropy.io",
    "astropy.wcs",
    "astropy.coordinates",
    "astropy.time",
    "alpyca",
    # argos.server (the 0.5.0 runtime): the `server` extra. The Pages job installs
    # only the docs extra (.github/workflows/pages.yml), so without these mocks an
    # argos.server page builds on a developer's machine and fails the deploy.
    "fastapi",
    "starlette",
    "pydantic",
    "uvicorn",
    "anyio",
]

# intersphinx — cross-ref to Python stdlib docs
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "astropy": ("https://docs.astropy.org/en/stable", None),
}

# -- HTML output ------------------------------------------------------------

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "../tests/**"]

# Don't include test files or conftest.py in autodoc downloads
nitpicky = False

html_theme = "furo"
html_title = f"ARGOS {release}"
# The mark from tools/logo-generator.html (docs/favicon.svg has its geometry;
# never redrawn), as the sidebar logo and the favicon.
html_logo = "../docs/favicon.svg"
html_favicon = "../docs/favicon.svg"
# One canonical URL per page (<link rel="canonical">), as the showcase has.
html_baseurl = "https://perretjules.com/argos/docs/"
# ../docs/fonts: the showcase's IBM Plex files, copied into _static for the
# text (_static/custom.css) and the diagrams (_static/diagrams.css); one copy of
# the fonts in the repository.
html_static_path = ["_static", "../docs/fonts"]
html_css_files = ["custom.css"]
# The diagrams follow the page's theme, Furo's toggle included (_static/diagrams.css).
html_js_files = ["diagrams.js"]

# MathJax from _static, never from a CDN: the site loads nothing remote. 3.2.2's
# tex-svg-full.js holds every TeX extension and the SVG glyphs, so it fetches no
# font or component at run time (_static/mathjax/LICENSE.txt, Apache 2.0). Its
# menu is off: the accessibility explorer it offers would load the speech-rule
# engine from a CDN.
mathjax_path = "mathjax/tex-svg-full.js"
mathjax3_config = {"options": {"enableMenu": False}}

_PLEX_SANS = '"IBM Plex Sans", "IBM Plex Mono", Arial, sans-serif'
_PLEX_MONO = '"IBM Plex Mono", "IBM Plex Sans", ui-monospace, Menlo, monospace'
html_theme_options = {
    # ARGOS's palette instead of Furo's (web/src/design/BRAND.md §3-§5, tokens.css):
    # IBM Plex for text and code; brass only for the current page in the sidebar,
    # focus and the links' underline, never as text (brass is 2.61:1 on white):
    # links are the body text's colour with a brass underline, as on the showcase.
    # Light pages use --accent-deep #8d6b2b (4.92:1 on white), dark pages --accent
    # #c49a3c (7.05:1 on Furo's #131416). Admonitions use ARGOS's status roles:
    # brass for warnings, a neutral grey (light) or --cyan (dark, "secondary
    # information") for notes, --danger for errors; their icons are in custom.css.
    "light_css_variables": {
        "color-brand-primary": "#8d6b2b",
        "color-brand-content": "#8d6b2b",
        "color-link": "var(--color-foreground-primary)",
        "color-link--hover": "var(--color-foreground-primary)",
        "color-link--visited": "var(--color-foreground-primary)",
        "color-link--visited--hover": "var(--color-foreground-primary)",
        "color-link-underline": "#8d6b2b",
        "color-link-underline--hover": "#8d6b2b",
        "color-link-underline--visited": "#8d6b2b",
        "color-link-underline--visited--hover": "#8d6b2b",
        "color-sidebar-link-text": "var(--color-foreground-primary)",
        "color-sidebar-link-text--top-level": "var(--color-foreground-primary)",
        "color-api-name": "var(--color-foreground-primary)",
        "color-api-pre-name": "var(--color-foreground-secondary)",
        "color-admonition-title--warning": "#8d6b2b",
        "color-admonition-title-background--warning": "rgba(141, 107, 43, 0.1)",
        "color-admonition-title--caution": "#8d6b2b",
        "color-admonition-title-background--caution": "rgba(141, 107, 43, 0.1)",
        "color-admonition-title--attention": "#8d6b2b",
        "color-admonition-title-background--attention": "rgba(141, 107, 43, 0.1)",
        "color-admonition-title--note": "#5b6562",
        "color-admonition-title-background--note": "rgba(91, 101, 98, 0.1)",
        "color-admonition-title--tip": "#5b6562",
        "color-admonition-title-background--tip": "rgba(91, 101, 98, 0.1)",
        "color-admonition-title--hint": "#5b6562",
        "color-admonition-title-background--hint": "rgba(91, 101, 98, 0.1)",
        "color-admonition-title--important": "#5b6562",
        "color-admonition-title-background--important": "rgba(91, 101, 98, 0.1)",
        "color-admonition-title--seealso": "#5b6562",
        "color-admonition-title-background--seealso": "rgba(91, 101, 98, 0.1)",
        "color-admonition-title--danger": "#bf7772",
        "color-admonition-title-background--danger": "rgba(191, 119, 114, 0.12)",
        "color-admonition-title--error": "#bf7772",
        "color-admonition-title-background--error": "rgba(191, 119, 114, 0.12)",
        "font-stack": _PLEX_SANS,
        "font-stack--headings": _PLEX_SANS,
        "font-stack--monospace": _PLEX_MONO,
    },
    "dark_css_variables": {
        "color-brand-primary": "#c49a3c",
        "color-brand-content": "#c49a3c",
        "color-link": "var(--color-foreground-primary)",
        "color-link--hover": "var(--color-foreground-primary)",
        "color-link--visited": "var(--color-foreground-primary)",
        "color-link--visited--hover": "var(--color-foreground-primary)",
        "color-link-underline": "#c49a3c",
        "color-link-underline--hover": "#c49a3c",
        "color-link-underline--visited": "#c49a3c",
        "color-link-underline--visited--hover": "#c49a3c",
        "color-sidebar-link-text": "var(--color-foreground-primary)",
        "color-sidebar-link-text--top-level": "var(--color-foreground-primary)",
        "color-api-name": "var(--color-foreground-primary)",
        "color-api-pre-name": "var(--color-foreground-secondary)",
        "color-admonition-title--warning": "#d0a85a",
        "color-admonition-title-background--warning": "rgba(208, 168, 90, 0.12)",
        "color-admonition-title--caution": "#d0a85a",
        "color-admonition-title-background--caution": "rgba(208, 168, 90, 0.12)",
        "color-admonition-title--attention": "#d0a85a",
        "color-admonition-title-background--attention": "rgba(208, 168, 90, 0.12)",
        "color-admonition-title--note": "#7da8b2",
        "color-admonition-title-background--note": "rgba(125, 168, 178, 0.12)",
        "color-admonition-title--tip": "#7da8b2",
        "color-admonition-title-background--tip": "rgba(125, 168, 178, 0.12)",
        "color-admonition-title--hint": "#7da8b2",
        "color-admonition-title-background--hint": "rgba(125, 168, 178, 0.12)",
        "color-admonition-title--important": "#7da8b2",
        "color-admonition-title-background--important": "rgba(125, 168, 178, 0.12)",
        "color-admonition-title--seealso": "#7da8b2",
        "color-admonition-title-background--seealso": "rgba(125, 168, 178, 0.12)",
        "color-admonition-title--danger": "#bf7772",
        "color-admonition-title-background--danger": "rgba(191, 119, 114, 0.12)",
        "color-admonition-title--error": "#bf7772",
        "color-admonition-title-background--error": "rgba(191, 119, 114, 0.12)",
    },
    "source_repository": "https://github.com/jperret21/argos/",
    "source_branch": "main",
    "source_directory": "docsrc/",
    "footer_icons": [
        {
            "name": "GitHub",
            "url": "https://github.com/jperret21/argos",
            "html": '<svg stroke="currentColor" fill="currentColor" stroke-width="0" viewBox="0 0 16 16"><path fill-rule="evenodd" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.012 8.012 0 0 0 16 8c0-4.42-3.58-8-8-8z"></path></svg>',
            "class": "",
        },
    ],
}

# -- Graphviz settings ------------------------------------------------------

graphviz_output_format = "svg"

# -- Extensions -------------------------------------------------------------

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False

# autodoc — don't duplicate dataclass fields (attributes + __init__ params)
autoclass_content = 'class'
# Default values as written in the source: an object default (a module, say)
# would otherwise be rendered by its repr, with the build machine's path in it.
autodoc_preserve_defaults = True
# Document what each module defines, not the names it re-exports in __all__:
# a re-export documented twice gave the source views' [docs] links an anchor
# that does not exist (e.g. site_check's horizontal_at).
autodoc_default_options = {"ignore-module-all": True}
# "duplicate": a dataclass field is described twice on its own page, by its
# docstring's Attributes section and by :undoc-members: (sequencer, session_log).
suppress_warnings = ["misc.highlighting_failure", "ref.duplicate", "toc.circular", "duplicate"]
