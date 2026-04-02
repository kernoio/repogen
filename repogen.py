#!/usr/bin/env python3
"""
repogen.py — thin shim for running repogen directly.

    python3 repogen.py <command> [args]

This file exists so the CLI can be run without installing the package.
All logic lives in the repogen/ package:

    repogen/core.py      — shared helpers, verification, analysis
    repogen/generate.py  — template and agent-based generation
    repogen/cli.py       — Click commands
    repogen/__init__.py  — public API for evaluation scripts

To import repogen functions from an evaluation script:

    from repogen.core import verify_repo, count_applications, count_endpoints
    from repogen.generate import generate_from_spec
"""

import os
import sys
from pathlib import Path

# Ensure the repo root is on sys.path so `import repogen` resolves
# to the repogen/ package directory regardless of working directory.
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load .env before anything else
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    _env = ROOT / ".env"
    if _env.exists():
        for _line in _env.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

from repogen.cli import cli

if __name__ == "__main__":
    cli()
