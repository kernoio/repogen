#!/usr/bin/env python3
"""
fix_loop.py — Verify a generated repo; on failure, send diagnostics to Claude
to fix it and retry.

Each cycle: build → start → probe (health + CRUD if present) → capture docker
logs. On failure, Claude receives the full diagnostics plus every current repo
file and returns a corrected JSON map of {filename: content}. Those files are
written back and the cycle repeats.

Usage:
    python3 scripts/fix_loop.py <repo-path> <port> [options]

Options:
    --max-retries N    Max fix-and-retry cycles (default: 3)
    --model MODEL      Claude model (default: claude-sonnet-4-6)
    --wait SECONDS     Startup wait before probing (default: 30)
    --verbose          Show each HTTP probe request and response

Requires: ANTHROPIC_API_KEY env var, docker, curl
"""

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE_MD = ROOT / "CLAUDE.md"
PROGRESS_PATH = ROOT / "progress.yaml"
MATRIX_PATH = ROOT / "matrix.yaml"

_SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".pytest_cache",
    "dist", "build", "target", "vendor", ".gradle", ".next", ".mypy_cache",
}
_SKIP_EXTS = {
    ".pyc", ".class", ".o", ".a", ".so", ".jar", ".war",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf",
}

MODEL_DEFAULT = "claude-sonnet-4-6"
MAX_RETRIES_DEFAULT = 3
WAIT_DEFAULT = 30


# ── File collection ───────────────────────────────────────────────────────────

def collect_files(repo_path: Path) -> dict[str, str]:
    """Return {rel_path: content} for all readable text files in repo_path."""
    files: dict[str, str] = {}
    for p in sorted(repo_path.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_path)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if rel.suffix in _SKIP_EXTS:
            continue
        try:
            files[str(rel)] = p.read_text(errors="replace")
        except OSError:
            pass
    return files


# ── Shell helpers ─────────────────────────────────────────────────────────────

def run_cmd(args: list, cwd: Path | None = None, timeout: int = 300) -> tuple[int, str, str]:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def compose_down(repo_path: Path) -> None:
    subprocess.run(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=repo_path, capture_output=True, timeout=60,
    )


# ── Verification ──────────────────────────────────────────────────────────────

def verify(
    repo_path: Path, port: int, wait: int, verbose: bool
) -> tuple[bool, str]:
    """
    Build → start → probe all endpoints → capture container logs.
    Returns (passed, diagnostics_string). Always tears down before returning.
    """
    diag: list[str] = []

    def section(title: str) -> None:
        diag.append(f"\n{'━' * 60}")
        diag.append(f"  {title}")
        diag.append("━" * 60)

    def record(*parts: str) -> None:
        for part in parts:
            if part and part.strip():
                diag.append(part.rstrip())

    base = f"http://localhost:{port}"

    # Ensure nothing is already running on this port from a prior failed cycle
    compose_down(repo_path)

    # ── Build ──────────────────────────────────────────────────────────────────
    section("docker compose build")
    rc, out, err = run_cmd(["docker", "compose", "build"], cwd=repo_path)
    record(out, err)
    if rc != 0:
        compose_down(repo_path)
        return False, "\n".join(diag)

    # ── Start ──────────────────────────────────────────────────────────────────
    section("docker compose up -d")
    rc, out, err = run_cmd(["docker", "compose", "up", "-d"], cwd=repo_path)
    record(out, err)
    if rc != 0:
        compose_down(repo_path)
        return False, "\n".join(diag)

    if verbose:
        print(f"  waiting {wait}s for startup...")
    time.sleep(wait)

    # ── Container logs (captured before any teardown) ──────────────────────────
    section("docker compose logs")
    _, logs, _ = run_cmd(
        ["docker", "compose", "logs", "--no-color", "--timestamps"], cwd=repo_path
    )
    record(logs)

    # ── Health probe ───────────────────────────────────────────────────────────
    section(f"GET {base}/health")
    if verbose:
        print(f"\n  >> GET {base}/health")
    rc, out, _ = run_cmd(["curl", "-s", f"{base}/health"])
    record(f"exit_code={rc}", f"body={out.strip() or '(empty)'}")
    if verbose:
        print(f"  << exit={rc}  body={out.strip() or '(empty)'}")

    health_ok = rc == 0 and '"ok"' in out
    if not health_ok:
        compose_down(repo_path)
        return False, "\n".join(diag)

    # ── CRUD probe (only if /items route responds) ─────────────────────────────
    _, status_out, _ = run_cmd(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "GET",
         f"{base}/items"]
    )
    has_crud = status_out.strip() in ("200", "404")

    crud_ok = True
    if has_crud:
        section("CRUD endpoint probes")
        if verbose:
            print()
        crud_ok, crud_lines = _probe_crud(base, verbose)
        diag.extend(crud_lines)

    compose_down(repo_path)
    return health_ok and crud_ok, "\n".join(diag)


def _probe_crud(base: str, verbose: bool) -> tuple[bool, list[str]]:
    """Run the full /items CRUD suite. Returns (passed, log_lines)."""
    diag: list[str] = []
    passed = True
    item_id = None

    def log(msg: str) -> None:
        diag.append(f"  {msg}")
        if verbose:
            print(f"  {msg}")

    # POST /items
    rc, out, _ = run_cmd([
        "curl", "-s", "-X", "POST", f"{base}/items",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"test-item","description":"hello world"}',
    ])
    if rc == 0 and out.strip():
        log(f"POST /items → {out.strip()[:400]}")
        try:
            item_id = json.loads(out).get("id")
        except (json.JSONDecodeError, AttributeError):
            log("  (could not extract .id from response)")
    else:
        log(f"POST /items FAILED  exit={rc}  body={out.strip() or '(empty)'}")
        passed = False

    if item_id is None:
        return passed, diag

    # GET /items
    rc, out, _ = run_cmd(["curl", "-s", f"{base}/items"])
    if rc == 0:
        log(f"GET /items → {out.strip()[:400]}")
    else:
        log(f"GET /items FAILED  exit={rc}")
        passed = False

    # GET /items/:id
    rc, out, _ = run_cmd(["curl", "-s", f"{base}/items/{item_id}"])
    if rc == 0:
        log(f"GET /items/{item_id} → {out.strip()[:400]}")
    else:
        log(f"GET /items/{item_id} FAILED  exit={rc}")
        passed = False

    # PUT /items/:id
    rc, out, _ = run_cmd([
        "curl", "-s", "-X", "PUT", f"{base}/items/{item_id}",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"updated-item","description":"updated"}',
    ])
    if rc == 0:
        log(f"PUT /items/{item_id} → {out.strip()[:400]}")
    else:
        log(f"PUT /items/{item_id} FAILED  exit={rc}")
        passed = False

    # DELETE /items/:id
    rc, out, _ = run_cmd([
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "-X", "DELETE", f"{base}/items/{item_id}",
    ])
    http_status = out.strip()
    if http_status in ("200", "204"):
        log(f"DELETE /items/{item_id} → HTTP {http_status}")
    else:
        log(f"DELETE /items/{item_id} FAILED → HTTP {http_status}")
        passed = False

    return passed, diag


# ── Agent fix ─────────────────────────────────────────────────────────────────

def agent_fix(
    *,
    repo_path: Path,
    diagnostics: str,
    attempt: int,
    model: str,
    repo_name: str,
    language: str,
    framework: str,
    port: int,
) -> bool:
    """Send diagnostics + current files to Claude; write back the returned fix.
    Returns True if files were successfully applied."""
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()

    current_files = collect_files(repo_path)
    claude_md = CLAUDE_MD.read_text() if CLAUDE_MD.exists() else ""

    file_dump = "\n\n".join(
        f"### {name}\n```\n{content}\n```"
        for name, content in current_files.items()
    )

    prompt = textwrap.dedent(f"""
        You are fixing a Dockerized benchmark repository that failed automated
        verification. This is fix attempt {attempt}.

        ## Repository info
        - Name:      {repo_name}
        - Language:  {language}
        - Framework: {framework}
        - Host port: {port}

        ## Failure diagnostics
        The output below includes docker build logs, container runtime logs,
        and the results of probing each HTTP endpoint.

        ```
        {diagnostics}
        ```

        ## Current repository files
        {file_dump}

        ## Known fix patterns (from CLAUDE.md)
        {claude_md}

        ## Your task
        1. Identify the root cause from the diagnostics.
        2. Return the complete corrected file set as a single JSON object:
           {{"relative/path": "file content", ...}}
        3. Include EVERY file the repository needs — both changed and unchanged.
        4. The service MUST respond to GET /health with HTTP 200 and body
           {{"status": "ok"}}.
        5. Output ONLY the JSON object — no prose, no markdown fences.
    """).strip()

    print(f"  [agent] Sending {len(current_files)} file(s) + diagnostics to {model}...")

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if the model wrapped the JSON
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```\s*$", "", raw)
        raw = raw.strip()

    # Last resort: pull out the outermost JSON object
    if not raw.startswith("{"):
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            raw = m.group(0)

    try:
        new_files: dict = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [agent] ERROR: could not parse response as JSON: {e}", file=sys.stderr)
        print(f"  [agent] First 800 chars:\n{raw[:800]}", file=sys.stderr)
        return False

    if not isinstance(new_files, dict) or not new_files:
        print("  [agent] ERROR: response was not a non-empty JSON object", file=sys.stderr)
        return False

    print(f"  [agent] Applying {len(new_files)} file(s):")
    for filename, content in new_files.items():
        dest = repo_path / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        print(f"    + {filename}")

    return True


# ── Progress helpers (optional — only if matrix + progress files exist) ────────

def _mark_progress(repo_name: str, status: str, verified: bool = False) -> None:
    """Update progress.yaml if it exists. Silent no-op otherwise."""
    try:
        import yaml
    except ImportError:
        return
    if not PROGRESS_PATH.exists():
        return
    try:
        from datetime import datetime, timezone
        data = yaml.safe_load(PROGRESS_PATH.read_text()) or {"repos": {}}
        data.setdefault("repos", {})[repo_name] = {
            "status": status,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "verified": verified,
        }
        PROGRESS_PATH.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    except Exception:
        pass  # progress tracking is best-effort


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify a repo; on failure ask Claude to fix it and retry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
            Examples:
              python3 scripts/fix_loop.py generated/crud-python-fastapi 8001
              python3 scripts/fix_loop.py generated/sfr-go-gin 8002 --max-retries 5 --wait 45
              python3 scripts/fix_loop.py generated/crud-ts-express 8003 --verbose
        """),
    )
    parser.add_argument("repo_path", help="Path to the generated repo directory")
    parser.add_argument("port", type=int, help="Host port the service binds to")
    parser.add_argument(
        "--max-retries", type=int, default=MAX_RETRIES_DEFAULT,
        help=f"Fix attempts before giving up (default: {MAX_RETRIES_DEFAULT})",
    )
    parser.add_argument(
        "--model", default=MODEL_DEFAULT,
        help=f"Claude model (default: {MODEL_DEFAULT})",
    )
    parser.add_argument(
        "--wait", type=int, default=WAIT_DEFAULT,
        help=f"Seconds to wait for service startup (default: {WAIT_DEFAULT})",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show HTTP probe request/response details",
    )
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set")

    repo_path = Path(args.repo_path)
    if not repo_path.is_absolute():
        repo_path = (Path.cwd() / repo_path).resolve()
    if not repo_path.exists():
        sys.exit(f"ERROR: repo not found: {repo_path}")

    repo_name = repo_path.name
    # Parse language/framework from naming convention: <prefix>-<lang>-<framework>
    parts = repo_name.split("-")
    language  = parts[1] if len(parts) > 1 else "unknown"
    framework = "-".join(parts[2:]) if len(parts) > 2 else "unknown"

    print(
        f"[fix_loop] repo={repo_name}  port={args.port}  "
        f"max_retries={args.max_retries}  model={args.model}"
    )

    for cycle in range(args.max_retries + 1):
        label = "initial verify" if cycle == 0 else f"re-verify after fix {cycle}"
        print(f"\n[fix_loop] ── {label} {'─' * max(0, 44 - len(label))}")

        passed, diagnostics = verify(repo_path, args.port, args.wait, args.verbose)

        if passed:
            print(f"\n[fix_loop] ✓  PASS — {repo_name}")
            _mark_progress(repo_name, "done", verified=True)
            return

        print(f"[fix_loop] ✗  FAIL")

        if cycle == args.max_retries:
            print(
                f"\n[fix_loop] Exhausted {args.max_retries} fix attempt(s). "
                f"Final diagnostics:\n"
            )
            print(diagnostics)
            _mark_progress(repo_name, "failed")
            sys.exit(1)

        print(f"[fix_loop] Invoking agent (fix {cycle + 1} of {args.max_retries})...")
        if not agent_fix(
            repo_path=repo_path,
            diagnostics=diagnostics,
            attempt=cycle + 1,
            model=args.model,
            repo_name=repo_name,
            language=language,
            framework=framework,
            port=args.port,
        ):
            print("[fix_loop] Agent returned no usable fix — aborting.", file=sys.stderr)
            sys.exit(1)

        print("[fix_loop] Fix applied — re-verifying...")


if __name__ == "__main__":
    main()
