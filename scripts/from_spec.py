#!/usr/bin/env python3
"""
from_spec.py — Generate a benchmark repository from a Repo-spec .md file.

A Repo-spec describes a real codebase: its stack, design patterns, folder
layout, and a generation hint. This script sends that spec to Claude, which
returns a minimal Dockerized CRUD service that matches the target stack. The
result is written to generated/<name>/ and optionally verified + self-repaired
by fix_loop.

Usage:
    python3 scripts/from_spec.py <spec.md>
    python3 scripts/from_spec.py Repo-specs/Seapoint.md --port 8005
    python3 scripts/from_spec.py Repo-specs/Seapoint.md --name my-repo --no-fix

Requires: ANTHROPIC_API_KEY, docker, curl (for fix_loop)
"""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD   = ROOT / "CLAUDE.md"
CRUD_SPEC   = ROOT / "specs" / "crud.md"
GENERATED   = ROOT / "generated"

MODEL_DEFAULT       = "claude-sonnet-4-6"
MAX_RETRIES_DEFAULT = 3
WAIT_DEFAULT        = 30


# ── Helpers ───────────────────────────────────────────────────────────────────

def find_free_port(start: int = 8000, end: int = 9000) -> int:
    """Return the first TCP port in [start, end) not currently in use."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port found between {start} and {end}")


def extract_json(text: str) -> str:
    """Strip markdown fences and find the outermost JSON object."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    if not text.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
    return text


# ── Generation ────────────────────────────────────────────────────────────────

def generate(spec_text: str, repo_name: str, port: int, model: str) -> dict[str, str]:
    """Send the spec to Claude; return {filename: content} for the new repo."""
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()

    claude_md = CLAUDE_MD.read_text() if CLAUDE_MD.exists() else ""
    crud_spec  = CRUD_SPEC.read_text()  if CRUD_SPEC.exists()  else ""

    prompt = textwrap.dedent(f"""
        You are generating a minimal Dockerized benchmark repository.

        ## Your goal
        Using the architecture spec below as your guide, produce a self-contained
        service that:

        1. Implements the standard CRUD /items API (contract in the CRUD spec section)
        2. Matches the target codebase's language, framework, ORM, and idioms as
           closely as possible — pay particular attention to the "generation hint"
           section of the spec, which lists exactly what to keep and how to build it
        3. Is fully Dockerized and starts cleanly with `docker compose up`

        ## Repository metadata
        - Repo name:  {repo_name}
        - Host port:  {port}   (map this to the container's internal port in docker-compose.yml)

        ## Architecture spec  (target codebase to replicate)
        ───────────────────────────────────────────────────
        {spec_text}
        ───────────────────────────────────────────────────

        ## CRUD endpoint contract  (implement all of these exactly)
        {crud_spec}

        ## Docker & file conventions  (follow these exactly)
        {claude_md}

        ## Output format
        Return ONLY a single JSON object mapping each relative file path to its
        complete UTF-8 content.  Example shape:

        {{
          "Dockerfile": "FROM ...",
          "docker-compose.yml": "services:\\n  ...",
          "src/index.ts": "import ..."
        }}

        Include every file the repository needs.
        Do NOT include any text before or after the JSON object.
    """).strip()

    print(f"  Calling {model}...")
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = extract_json(response.content[0].text)

    try:
        files: dict = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: could not parse agent response as JSON: {e}", file=sys.stderr)
        print(f"First 800 chars of response:\n{raw[:800]}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(files, dict) or not files:
        sys.exit("ERROR: agent returned an empty or non-object response")

    return files


# ── Output ────────────────────────────────────────────────────────────────────

def write_files(files: dict[str, str], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        dest = output_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        print(f"  + {filename}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a benchmark repo from a Repo-spec .md file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            examples:
              python3 scripts/from_spec.py Repo-specs/Seapoint.md
              python3 scripts/from_spec.py Repo-specs/Seapoint.md --port 8005
              python3 scripts/from_spec.py Repo-specs/Seapoint.md --name seapoint-v2 --no-fix
              python3 scripts/from_spec.py Repo-specs/Seapoint.md --max-retries 5 --wait 45
        """),
    )
    parser.add_argument(
        "spec",
        help="Path to the Repo-spec .md file",
    )
    parser.add_argument(
        "--output", default=str(GENERATED),
        help=f"Parent directory for generated repos (default: {GENERATED})",
    )
    parser.add_argument(
        "--name", default=None,
        help="Repo directory name (default: lowercased spec filename stem)",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Host port to bind (default: auto-detect next free port from 8000)",
    )
    parser.add_argument(
        "--model", default=MODEL_DEFAULT,
        help=f"Claude model (default: {MODEL_DEFAULT})",
    )
    parser.add_argument(
        "--no-fix", action="store_true",
        help="Write files and exit — skip fix_loop verification",
    )
    parser.add_argument(
        "--max-retries", type=int, default=MAX_RETRIES_DEFAULT,
        help=f"fix_loop max retry cycles (default: {MAX_RETRIES_DEFAULT})",
    )
    parser.add_argument(
        "--wait", type=int, default=WAIT_DEFAULT,
        help=f"Startup wait in seconds passed to fix_loop (default: {WAIT_DEFAULT})",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set")

    # Resolve spec path
    spec_path = Path(args.spec)
    if not spec_path.is_absolute():
        spec_path = (Path.cwd() / spec_path).resolve()
    if not spec_path.exists():
        sys.exit(f"ERROR: spec file not found: {spec_path}")

    repo_name  = args.name or spec_path.stem.lower()
    output_dir = Path(args.output) / repo_name
    port       = args.port or find_free_port()

    print(f"[from_spec] spec    → {spec_path.name}")
    print(f"[from_spec] output  → {output_dir}")
    print(f"[from_spec] port    → {port}")
    print(f"[from_spec] model   → {args.model}")

    if output_dir.exists() and any(output_dir.iterdir()):
        print(f"[from_spec] note: {output_dir} already exists — files will be overwritten")

    # ── Generate ───────────────────────────────────────────────────────────────
    print(f"\n[from_spec] Generating repo from spec...")
    spec_text = spec_path.read_text()
    files = generate(spec_text, repo_name, port, args.model)

    # ── Write ──────────────────────────────────────────────────────────────────
    print(f"\n[from_spec] Writing {len(files)} file(s):")
    write_files(files, output_dir)

    if args.no_fix:
        print(f"\n[from_spec] Done (--no-fix; skipping verification).")
        print(f"  Verify manually:  bash scripts/verify.sh {output_dir} {port}")
        return

    # ── Verify + self-repair via fix_loop ──────────────────────────────────────
    print(f"\n[from_spec] Running fix_loop (up to {args.max_retries} repair cycles)...")

    fix_loop_path = Path(__file__).parent / "fix_loop.py"
    if not fix_loop_path.exists():
        print(f"WARNING: fix_loop.py not found at {fix_loop_path} — skipping verification")
        return

    result = subprocess.run([
        sys.executable, str(fix_loop_path),
        str(output_dir), str(port),
        "--max-retries", str(args.max_retries),
        "--model",       args.model,
        "--wait",        str(args.wait),
    ])

    if result.returncode == 0:
        print(f"\n[from_spec] ✓  {repo_name} — generated and verified.")
    else:
        print(
            f"\n[from_spec] ✗  {repo_name} — still failing after "
            f"{args.max_retries} repair attempt(s)."
        )
        print(f"  Files are in {output_dir}/ — inspect and fix manually.")
        sys.exit(1)


if __name__ == "__main__":
    main()
