# -*- coding: utf-8 -*-
"""sys.path bootstrap for tests/: repo root holds particle_core.pyd,
editor/ holds studio_imgui + particle_studio. Import this first."""
import os as _os
import sys as _sys

_TESTS_DIR = _os.path.dirname(_os.path.abspath(__file__))
_REPO_ROOT = _os.path.dirname(_TESTS_DIR)
for _p in (_REPO_ROOT, _os.path.join(_REPO_ROOT, "editor")):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)
