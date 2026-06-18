"""Sphinx configuration for Argos documentation.

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

project = "Argos"
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

_PYQT = _mock.MagicMock()
for _sub in ("QtCore", "QtWidgets", "QtGui", "QtSvg", "QtNetwork"):
    setattr(_PYQT, _sub, _mock.MagicMock())
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
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_theme_options = {
    "dark_css_variables": {
        "color-brand-primary": "#6ab0f5",
        "color-brand-content": "#6ab0f5",
    },
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
suppress_warnings = ["misc.highlighting_failure", "ref.duplicate", "toc.circular", "duplicate"]
