"""
repogen — Generate synthetic benchmark repositories from a spec and language list.

Public API for use in evaluation scripts and notebooks:

    from repogen.core import verify_repo, count_applications, count_endpoints
    from repogen.core import collect_files, run_fix_loop, find_free_port
    from repogen.generate import generate_from_spec, generate_from_template, generate_from_agent

CLI entry point:
    repogen.cli:cli   (configured in pyproject.toml)
"""

from repogen.core import (
    verify_repo,
    count_applications,
    count_endpoints,
    collect_files,
    run_fix_loop,
    find_free_port,
    load_matrix,
    load_progress,
    mark_progress,
)
from repogen.generate import (
    generate_from_spec,
    generate_from_template,
    generate_from_agent,
)

__version__ = "0.1.0"

__all__ = [
    # verification
    "verify_repo",
    # analysis
    "count_applications",
    "count_endpoints",
    # file utilities
    "collect_files",
    "find_free_port",
    # fix loop
    "run_fix_loop",
    # progress / matrix
    "load_matrix",
    "load_progress",
    "mark_progress",
    # generation
    "generate_from_spec",
    "generate_from_template",
    "generate_from_agent",
]
