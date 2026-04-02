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

# ── Shared helpers for fix_loop / from_spec ─────────────────────────────────

def _run(args: list, cwd: Path | None = None, timeout: int = 300) -> tuple[int, str, str]:
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def _compose_down(repo_path: Path) -> None:
    subprocess.run(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=repo_path, capture_output=True, timeout=60,
    )


def _collect_files(repo_path: Path) -> dict[str, str]:
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


def _find_free_port(start: int = 8000, end: int = 9000) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port in {start}–{end}")


def _extract_json(text: str) -> str:
    """Strip markdown fences and return the outermost JSON object."""
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


def _probe_crud(base: str, verbose: bool) -> tuple[bool, list[str]]:
    diag: list[str] = []
    passed = True
    item_id = None

    def record(msg: str) -> None:
        diag.append(f"  {msg}")
        if verbose:
            click.echo(f"  {msg}")

    rc, out, _ = _run([
        "curl", "-s", "-X", "POST", f"{base}/items",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"test-item","description":"hello world"}',
    ])
    if rc == 0 and out.strip():
        record(f"POST /items → {out.strip()[:400]}")
        try:
            item_id = json.loads(out).get("id")
        except (json.JSONDecodeError, AttributeError):
            record("  (could not extract .id from response)")
    else:
        record(f"POST /items FAILED  exit={rc}  body={out.strip() or '(empty)'}")
        passed = False

    if item_id is None:
        return passed, diag

    for method, url in [
        ("GET",  f"{base}/items"),
        ("GET",  f"{base}/items/{item_id}"),
    ]:
        rc, out, _ = _run(["curl", "-s", "-X", method, url])
        if rc == 0:
            record(f"{method} {url.replace(base,'')} → {out.strip()[:400]}")
        else:
            record(f"{method} {url.replace(base,'')} FAILED  exit={rc}")
            passed = False

    rc, out, _ = _run([
        "curl", "-s", "-X", "PUT", f"{base}/items/{item_id}",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"updated-item","description":"updated"}',
    ])
    if rc == 0:
        record(f"PUT /items/{item_id} → {out.strip()[:400]}")
    else:
        record(f"PUT /items/{item_id} FAILED  exit={rc}")
        passed = False

    rc, out, _ = _run([
        "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
        "-X", "DELETE", f"{base}/items/{item_id}",
    ])
    status = out.strip()
    if status in ("200", "204"):
        record(f"DELETE /items/{item_id} → HTTP {status}")
    else:
        record(f"DELETE /items/{item_id} FAILED → HTTP {status}")
        passed = False

    return passed, diag


def _verify_repo(repo_path: Path, port: int, wait: int, verbose: bool) -> tuple[bool, str]:
    """Build → start → probe. Captures all output. Always tears down."""
    diag: list[str] = []

    def section(title: str) -> None:
        diag.append(f"\n{'━' * 60}\n  {title}\n{'━' * 60}")

    def record(*parts: str) -> None:
        for p in parts:
            if p and p.strip():
                diag.append(p.rstrip())

    base = f"http://localhost:{port}"
    _compose_down(repo_path)

    section("docker compose build")
    rc, out, err = _run(["docker", "compose", "build"], cwd=repo_path)
    record(out, err)
    if rc != 0:
        _compose_down(repo_path)
        return False, "\n".join(diag)

    section("docker compose up -d")
    rc, out, err = _run(["docker", "compose", "up", "-d"], cwd=repo_path)
    record(out, err)
    if rc != 0:
        _compose_down(repo_path)
        return False, "\n".join(diag)

    if verbose:
        click.echo(f"  waiting {wait}s for startup...")
    time.sleep(wait)

    section("docker compose logs")
    _, logs, _ = _run(
        ["docker", "compose", "logs", "--no-color", "--timestamps"], cwd=repo_path
    )
    record(logs)

    section(f"GET {base}/health")
    if verbose:
        click.echo(f"\n  >> GET {base}/health")
    rc, out, _ = _run(["curl", "-s", f"{base}/health"])
    record(f"exit_code={rc}", f"body={out.strip() or '(empty)'}")
    if verbose:
        click.echo(f"  << exit={rc}  body={out.strip() or '(empty)'}")

    health_ok = rc == 0 and '"ok"' in out
    if not health_ok:
        _compose_down(repo_path)
        return False, "\n".join(diag)

    _, status_out, _ = _run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "GET", f"{base}/items"]
    )
    has_crud = status_out.strip() in ("200", "404")
    crud_ok = True
    if has_crud:
        section("CRUD endpoint probes")
        if verbose:
            click.echo("")
        crud_ok, crud_lines = _probe_crud(base, verbose)
        diag.extend(crud_lines)

    _compose_down(repo_path)
    return health_ok and crud_ok, "\n".join(diag)


def _agent_fix(
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
    """Send diagnostics + current files to Claude; apply returned fix. Returns True on success."""
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()
    current_files = _collect_files(repo_path)
    claude_md = CLAUDE_MD.read_text() if CLAUDE_MD.exists() else ""

    file_dump = "\n\n".join(
        f"### {name}\n```\n{content}\n```"
        for name, content in current_files.items()
    )

    prompt = textwrap.dedent(f"""
        You are fixing a Dockerized benchmark repository that failed verification.
        This is fix attempt {attempt}.

        ## Repository info
        - Name:      {repo_name}
        - Language:  {language}
        - Framework: {framework}
        - Host port: {port}

        ## Failure diagnostics
        ```
        {diagnostics}
        ```

        ## Current repository files
        {file_dump}

        ## Known fix patterns (from CLAUDE.md)
        {claude_md}

        ## Instructions
        1. Identify the root cause from the diagnostics.
        2. Return the complete corrected file set as a JSON object:
           {{"relative/path": "file content", ...}}
        3. Include EVERY file the repo needs — both changed and unchanged.
        4. The service MUST expose GET /health returning {{"status": "ok"}} with HTTP 200.
        5. Output ONLY the JSON object. No prose, no markdown fences.
    """).strip()

    click.echo(f"  [agent] Sending {len(current_files)} file(s) + diagnostics to {model}...")

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = _extract_json(response.content[0].text)

    try:
        new_files: dict = json.loads(raw)
    except json.JSONDecodeError as e:
        error(f"Could not parse agent response as JSON: {e}")
        click.echo(f"  First 800 chars:\n{raw[:800]}", err=True)
        return False

    if not isinstance(new_files, dict) or not new_files:
        error("Agent response was not a non-empty JSON object")
        return False

    click.echo(f"  [agent] Applying {len(new_files)} file(s):")
    for filename, content in new_files.items():
        dest = repo_path / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        click.echo(f"    + {filename}")

    return True


def _run_fix_loop(
    repo_path: Path,
    port: int,
    max_retries: int,
    model: str,
    wait: int,
    verbose: bool,
    repo_name: str,
    language: str,
    framework: str,
) -> bool:
    """Verify → fix → retry loop. Returns True if the repo passes verification."""
    for cycle in range(max_retries + 1):
        label = "initial verify" if cycle == 0 else f"re-verify after fix {cycle}"
        log(f"── {label}")

        passed, diagnostics = _verify_repo(repo_path, port, wait, verbose)

        if passed:
            log(f"✓  PASS — {repo_name}")
            mark_progress(repo_name, "done", verified=True)
            return True

        warn(f"✗  FAIL")

        if cycle == max_retries:
            error(f"Exhausted {max_retries} fix attempt(s). Final diagnostics:\n")
            click.echo(diagnostics)
            mark_progress(repo_name, "failed")
            return False

        log(f"Invoking agent (fix {cycle + 1} of {max_retries})...")
        if not _agent_fix(
            repo_path=repo_path,
            diagnostics=diagnostics,
            attempt=cycle + 1,
            model=model,
            repo_name=repo_name,
            language=language,
            framework=framework,
            port=port,
        ):
            error("Agent returned no usable fix — aborting.")
            return False

        log("Fix applied — re-verifying...")

    return False


# ── fix_loop command ─────────────────────────────────────────────────────────

@cli.command(name="fix_loop")
@click.argument("repo_path")
@click.argument("port", type=int, required=False, default=None)
@click.option("--max-retries", default=3, show_default=True, help="Fix attempts before giving up")
@click.option("--model", default="claude-sonnet-4-6", show_default=True, help="Claude model")
@click.option("--wait", default=30, show_default=True, help="Seconds to wait for service startup")
@click.option("--verbose", "-v", is_flag=True, help="Show each HTTP probe request and response")
def fix_loop(repo_path, port, max_retries, model, wait, verbose):
    """Verify a repo; on failure ask Claude to fix it and retry.

    REPO_PATH is the path to a generated repo directory.
    PORT is the host port (auto-detected from matrix.yaml if omitted).

    \b
    Examples:
      repogen fix_loop generated/seapoint 8001
      repogen fix_loop generated/crud-python-fastapi 8002 --max-retries 5
      repogen fix_loop generated/sfr-go-gin 8003 --verbose
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        error("ANTHROPIC_API_KEY is not set"); sys.exit(1)

    path = Path(repo_path)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    if not path.exists():
        error(f"Repo directory not found: {path}"); sys.exit(1)

    # Auto-detect port from matrix.yaml if not provided
    resolved_port = port
    if resolved_port is None:
        try:
            repos = load_matrix()
            match = next((r for r in repos if r["name"] == path.name), None)
            if match:
                resolved_port = match["port"]
                log(f"Port {resolved_port} read from matrix.yaml")
        except SystemExit:
            pass
    if resolved_port is None:
        error("PORT argument is required (repo not found in matrix.yaml)"); sys.exit(1)

    repo_name = path.name
    parts = repo_name.split("-")
    language  = parts[1] if len(parts) > 1 else "unknown"
    framework = "-".join(parts[2:]) if len(parts) > 2 else "unknown"

    log(f"repo={repo_name}  port={resolved_port}  max_retries={max_retries}  model={model}")

    ok = _run_fix_loop(
        repo_path=path, port=resolved_port, max_retries=max_retries,
        model=model, wait=wait, verbose=verbose,
        repo_name=repo_name, language=language, framework=framework,
    )
    sys.exit(0 if ok else 1)


# ── from_spec command ────────────────────────────────────────────────────────

@cli.command(name="from_spec")
@click.argument("spec_path")
@click.option("--output", default=str(GENERATED_DIR), show_default=True,
              help="Parent directory for generated repos")
@click.option("--name", default=None,
              help="Repo directory name (default: lowercased spec filename stem)")
@click.option("--port", type=int, default=None,
              help="Host port (default: auto-detect next free port from 8000)")
@click.option("--model", default="claude-sonnet-4-6", show_default=True, help="Claude model")
@click.option("--no-fix", is_flag=True, help="Write files and exit — skip verification")
@click.option("--max-retries", default=3, show_default=True, help="fix_loop max retry cycles")
@click.option("--wait", default=30, show_default=True, help="Startup wait in seconds for fix_loop")
def from_spec(spec_path, output, name, port, model, no_fix, max_retries, wait):
    """Generate a benchmark repo from a Repo-spec .md file.

    SPEC_PATH is the path to a Repo-spec .md file (e.g. Repo-specs/Seapoint.md).
    The spec describes the target codebase's stack, patterns, and includes a
    generation hint. Claude generates a minimal CRUD service matching that stack,
    then fix_loop verifies and self-repairs the result.

    \b
    Examples:
      repogen from_spec Repo-specs/Seapoint.md
      repogen from_spec Repo-specs/Seapoint.md --port 8005
      repogen from_spec Repo-specs/Seapoint.md --name seapoint-v2 --no-fix
      repogen from_spec Repo-specs/Seapoint.md --max-retries 5 --wait 45
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        error("ANTHROPIC_API_KEY is not set"); sys.exit(1)

    spec = Path(spec_path)
    if not spec.is_absolute():
        spec = (Path.cwd() / spec).resolve()
    if not spec.exists():
        error(f"Spec file not found: {spec}"); sys.exit(1)

    repo_name  = name or spec.stem.lower()
    output_dir = Path(output) / repo_name
    resolved_port = port or _find_free_port()

    log(f"spec    → {spec.name}")
    log(f"output  → {output_dir}")
    log(f"port    → {resolved_port}")
    log(f"model   → {model}")

    if output_dir.exists() and any(output_dir.iterdir()):
        warn(f"{output_dir} already exists — files will be overwritten")

    # ── Generate ───────────────────────────────────────────────────────────────
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()
    spec_text = spec.read_text()
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
           section of the spec
        3. Is fully Dockerized and starts cleanly with `docker compose up`

        ## Repository metadata
        - Repo name:  {repo_name}
        - Host port:  {resolved_port}

        ## Architecture spec (target codebase to replicate)
        ───────────────────────────────────────────────────
        {spec_text}
        ───────────────────────────────────────────────────

        ## CRUD endpoint contract (implement all of these exactly)
        {crud_spec}

        ## Docker & file conventions (follow these exactly)
        {claude_md}

        ## Output format
        Return ONLY a single JSON object mapping relative file path to file content:
        {{ "Dockerfile": "...", "docker-compose.yml": "...", "src/index.ts": "..." }}
        Include every file the repository needs. No prose, no markdown fences.
    """).strip()

    log("Generating repo from spec...")
    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = _extract_json(response.content[0].text)

    try:
        files: dict = json.loads(raw)
    except json.JSONDecodeError as e:
        error(f"Could not parse agent response as JSON: {e}")
        click.echo(f"First 800 chars:\n{raw[:800]}", err=True)
        sys.exit(1)

    if not isinstance(files, dict) or not files:
        error("Agent returned an empty or non-object response"); sys.exit(1)

    # ── Write files ────────────────────────────────────────────────────────────
    log(f"Writing {len(files)} file(s):")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in files.items():
        dest = output_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        click.echo(f"  + {filename}")

    if no_fix:
        log("Done (--no-fix; skipping verification).")
        click.echo(f"  Verify manually:  repogen fix_loop {output_dir} {resolved_port}")
        return

    # ── Verify + self-repair ───────────────────────────────────────────────────
    log(f"Running fix_loop (up to {max_retries} repair cycles)...")

    parts = repo_name.split("-")
    language  = parts[1] if len(parts) > 1 else "unknown"
    framework = "-".join(parts[2:]) if len(parts) > 2 else "unknown"

    ok = _run_fix_loop(
        repo_path=output_dir, port=resolved_port, max_retries=max_retries,
        model=model, wait=wait, verbose=False,
        repo_name=repo_name, language=language, framework=framework,
    )

    if not ok:
        error(f"{repo_name} still failing after {max_retries} repair attempt(s).")
        click.echo(f"  Files are in {output_dir}/ — inspect and fix manually.")
        sys.exit(1)


if __name__ == "__main__":
    cli()
