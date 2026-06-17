"""Sphinx configuration for SeerControl documentation.

Build with::

    cd docs
    sphinx-build -M html . _build

Or from the project root::

    uv run sphinx-build -b html docs docs/_build
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

# -- Project info -----------------------------------------------------------

project = "SeerControl"
author = "J. Perret"
copyright = f"{datetime.now().year}, {author}"
release = "0.2.1"

# -- General configuration -------------------------------------------------

extensions = [
    "myst_parser",          # MyST Markdown (.md) support
    "sphinx.ext.autodoc",   # Auto-generate API docs from docstrings
    "sphinx.ext.napoleon",  # Google/NumPy-style docstring support
    "sphinx.ext.viewcode",  # Link to source code
    "sphinx.ext.graphviz",  # DOT graph / diagram support
    "sphinx.ext.intersphinx",  # Cross-ref to Python, numpy, etc.
]

# MyST config — parse all .md files as MyST
myst_heading_anchors = 4          # auto-generate anchors down to h4
myst_enable_extensions = [
    "colon_fence",                 # ```{note} / ```{warning} directives
    "deflist",                     # definition lists
    "fieldlist",                   # field lists
    "html_image",                  # inline HTML images
]

# autodoc — scan seercontrol packages
sys.path.insert(0, os.path.abspath(".."))
autodoc_mock_imports = [
    "PyQt6",
    "PyQt6.QtCore",
    "PyQt6.QtWidgets",
    "PyQt6.QtGui",
    "pyqtgraph",
    "requests",
    "astropy",
    "astropy.io",
    "astropy.wcs",
    "astropy.coordinates",
    "astropy.time",
    "alpyca",
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
suppress_warnings = ["misc.highlighting_failure"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "style_nav_header_background": "#2b3e50",
    "collapse_navigation": False,
    "sticky_navigation": True,
}

# -- Graphviz settings ------------------------------------------------------

graphviz_output_format = "svg"

# -- Extensions -------------------------------------------------------------

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
