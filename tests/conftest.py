"""Make the lnrelease package importable in tests.

The pipeline runs with the repo root as cwd and lnrelease/ on sys.path (see
scrape.py's `from utils import ...`), so tests mirror that layout rather than
turning lnrelease/ into an installable package.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'lnrelease'))
