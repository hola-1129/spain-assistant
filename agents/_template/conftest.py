"""Test bootstrap: make `shared.*` and template-local `tools`/`agent` importable."""
import sys
from pathlib import Path

TEMPLATE_ROOT = Path(__file__).resolve().parent
WORKSPACE = TEMPLATE_ROOT.parents[1]

for _p in (WORKSPACE, TEMPLATE_ROOT):
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
