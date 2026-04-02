"""
repogen.core — shared helpers, verification, and analysis functions.

These are the functions evaluation scripts should import directly:

    from repogen.core import verify_repo, count_applications, count_endpoints
    from repogen.core import collect_files, find_free_port

All functions are pure (no Click dependency) so they can be called from
evaluation scripts, notebooks, or any other context without the CLI.
"""

import json
import os
import re
import socket
import subprocess
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

# ── Path constants ────────────────────────────────────────────────────────────

ROOT          = Path(__file__).parent.parent
MATRIX_PATH   = ROOT / "matrix.yaml"
PROGRESS_PATH = ROOT / "progress.yaml"
TEMPLATES_DIR = ROOT / "templates"
GENERATED_DIR = ROOT / "generated"
SPECS_DIR     = ROOT / "Repo-specs"
CLAUDE_MD     = ROOT / "CLAUDE.md"
CRUD_SPEC     = ROOT / "specs" / "crud.md"

# ── Skip lists ────────────────────────────────────────────────────────────────

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".pytest_cache",
    "dist", "build", "target", "vendor", ".gradle", ".next", ".mypy_cache",
}
SKIP_EXTS = {
    ".pyc", ".class", ".o", ".a", ".so", ".jar", ".war",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff", ".woff2", ".ttf",
}

# Infrastructure image substrings used by count_applications.
INFRA_IMAGES = {
    "postgres", "mysql", "mariadb", "redis", "mongo", "mongodb",
    "rabbitmq", "kafka", "zookeeper", "elasticsearch", "meilisearch",
    "memcached", "nats", "etcd", "influxdb", "cassandra",
}


# ── Progress helpers ──────────────────────────────────────────────────────────

def load_progress() -> dict:
    if not PROGRESS_PATH.exists():
        return {"repos": {}}
    return yaml.safe_load(PROGRESS_PATH.read_text()) or {"repos": {}}


def save_progress(data: dict) -> None:
    PROGRESS_PATH.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False)
    )


def mark_progress(name: str, status: str, verified: bool = False) -> None:
    data = load_progress()
    data.setdefault("repos", {})[name] = {
        "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat() if status == "done" else None,
        "verified": verified,
    }
    save_progress(data)


# ── Matrix helpers ────────────────────────────────────────────────────────────

def load_matrix() -> list[dict]:
    if not MATRIX_PATH.exists():
        raise FileNotFoundError(
            "matrix.yaml not found. Run: repogen init --spec <spec> --langs <langs>"
        )
    return (yaml.safe_load(MATRIX_PATH.read_text()) or {}).get("repos", [])


# ── Low-level shell helpers ───────────────────────────────────────────────────

def run_cmd(
    args: list,
    cwd: Path | None = None,
    timeout: int = 300,
) -> tuple[int, str, str]:
    """Run a subprocess and return (returncode, stdout, stderr)."""
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def compose_down(repo_path: Path) -> None:
    """Tear down docker compose services, silently."""
    subprocess.run(
        ["docker", "compose", "down", "-v", "--remove-orphans"],
        cwd=repo_path, capture_output=True, timeout=60,
    )


# ── File collection ───────────────────────────────────────────────────────────

def collect_files(repo_path: Path) -> dict[str, str]:
    """Return {relative_path: content} for all readable text files in repo_path.

    Skips binary files, compiled artefacts, and dependency directories.
    """
    files: dict[str, str] = {}
    for p in sorted(repo_path.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_path)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if rel.suffix in SKIP_EXTS:
            continue
        try:
            files[str(rel)] = p.read_text(errors="replace")
        except OSError:
            pass
    return files


# ── Port utilities ────────────────────────────────────────────────────────────

def find_free_port(start: int = 8000, end: int = 9000) -> int:
    """Return the first TCP port in [start, end) not currently in use."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"No free port in {start}–{end}")


# ── JSON extraction ───────────────────────────────────────────────────────────

def extract_json(text: str) -> str:
    """Strip markdown fences and return the outermost JSON object or array string."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    if not text.startswith("{") and not text.startswith("["):
        m = re.search(r"[\[{][\s\S]*[\]}]", text)
        if m:
            text = m.group(0)
    return text


# ── CRUD probe ────────────────────────────────────────────────────────────────

def probe_crud(base: str, verbose: bool = False) -> tuple[bool, list[str]]:
    """Run the full /items CRUD suite against a live service.

    Returns (passed, log_lines).
    """
    diag: list[str] = []
    passed = True
    item_id = None

    def record(msg: str) -> None:
        diag.append(f"  {msg}")
        if verbose:
            print(f"  {msg}")

    rc, out, _ = run_cmd([
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
        ("GET", f"{base}/items"),
        ("GET", f"{base}/items/{item_id}"),
    ]:
        rc, out, _ = run_cmd(["curl", "-s", "-X", method, url])
        if rc == 0:
            record(f"{method} {url.replace(base, '')} → {out.strip()[:400]}")
        else:
            record(f"{method} {url.replace(base, '')} FAILED  exit={rc}")
            passed = False

    rc, out, _ = run_cmd([
        "curl", "-s", "-X", "PUT", f"{base}/items/{item_id}",
        "-H", "Content-Type: application/json",
        "-d", '{"name":"updated-item","description":"updated"}',
    ])
    if rc == 0:
        record(f"PUT /items/{item_id} → {out.strip()[:400]}")
    else:
        record(f"PUT /items/{item_id} FAILED  exit={rc}")
        passed = False

    rc, out, _ = run_cmd([
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


# ── Verification ──────────────────────────────────────────────────────────────

def verify_repo(
    repo_path: Path,
    port: int,
    wait: int = 30,
    verbose: bool = False,
) -> tuple[bool, str]:
    """Build → start → probe a repo with docker compose.

    Captures build output, container logs, health probe, and CRUD suite.
    Always tears down before returning.

    Returns (passed, diagnostics_string).
    """
    diag: list[str] = []

    def section(title: str) -> None:
        diag.append(f"\n{'━' * 60}\n  {title}\n{'━' * 60}")

    def record(*parts: str) -> None:
        for p in parts:
            if p and p.strip():
                diag.append(p.rstrip())

    base = f"http://localhost:{port}"
    compose_down(repo_path)

    section("docker compose build")
    rc, out, err = run_cmd(["docker", "compose", "build"], cwd=repo_path)
    record(out, err)
    if rc != 0:
        compose_down(repo_path)
        return False, "\n".join(diag)

    section("docker compose up -d")
    rc, out, err = run_cmd(["docker", "compose", "up", "-d"], cwd=repo_path)
    record(out, err)
    if rc != 0:
        compose_down(repo_path)
        return False, "\n".join(diag)

    if verbose:
        print(f"  waiting {wait}s for startup...")
    time.sleep(wait)

    section("docker compose logs")
    _, logs, _ = run_cmd(
        ["docker", "compose", "logs", "--no-color", "--timestamps"], cwd=repo_path
    )
    record(logs)

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

    _, status_out, _ = run_cmd(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-X", "GET", f"{base}/items"]
    )
    has_crud = status_out.strip() in ("200", "404")
    crud_ok = True
    if has_crud:
        section("CRUD endpoint probes")
        if verbose:
            print()
        crud_ok, crud_lines = probe_crud(base, verbose)
        diag.extend(crud_lines)

    compose_down(repo_path)
    return health_ok and crud_ok, "\n".join(diag)


# ── Application counting ──────────────────────────────────────────────────────

def count_applications(repo_path: Path) -> list[dict]:
    """Parse docker-compose.yml and return application (non-infrastructure) services.

    Each entry: {"name": str, "image": str, "ports": list[str]}
    """
    for name in ("docker-compose.yml", "docker-compose.yaml"):
        compose_path = repo_path / name
        if compose_path.exists():
            break
    else:
        return []

    try:
        data = yaml.safe_load(compose_path.read_text()) or {}
    except yaml.YAMLError:
        return []

    apps = []
    for svc_name, svc in (data.get("services") or {}).items():
        svc = svc or {}
        image = svc.get("image", "") or ""
        build = svc.get("build")
        is_infra = any(img in image.lower() for img in INFRA_IMAGES)
        if is_infra and not build:
            continue
        raw_ports = svc.get("ports") or []
        ports = [str(p).split(":")[0] if ":" in str(p) else str(p) for p in raw_ports]
        apps.append({"name": svc_name, "image": image or "(build)", "ports": ports})

    return apps


# ── Endpoint counting ─────────────────────────────────────────────────────────

def count_endpoints(repo_path: Path, model: str = "claude-sonnet-4-6") -> list[dict]:
    """Send all source files to Claude and return a list of HTTP endpoints.

    Each entry: {"method": str, "path": str, "description": str}
    Requires ANTHROPIC_API_KEY to be set.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required: pip install anthropic")

    source_files = collect_files(repo_path)
    if not source_files:
        return []

    _skip_names = {"package-lock.json", "yarn.lock", "bun.lockb", "poetry.lock", "Cargo.lock"}
    file_dump = "\n\n".join(
        f"### {name}\n```\n{content[:4000]}\n```"
        for name, content in source_files.items()
        if Path(name).name not in _skip_names
    )

    prompt = textwrap.dedent(f"""
        Examine the source files of this repository and list every HTTP endpoint it exposes.

        Return ONLY a JSON array. Each element must have exactly these keys:
        - "method"      — HTTP verb in uppercase (GET, POST, PUT, PATCH, DELETE, etc.)
        - "path"        — URL path as declared in the code (e.g. "/items/:id")
        - "description" — one short sentence describing what it does

        If the repo exposes no HTTP endpoints, return an empty array: []
        Do not include any text before or after the JSON array.

        ## Repository files
        {file_dump}
    """).strip()

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = extract_json(response.content[0].text)
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    return []


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
    print_fn=print,
) -> bool:
    """Send diagnostics + current repo files to Claude; write back the returned fix.

    print_fn is injectable so the CLI can pass click.echo and scripts can use print.
    Returns True if files were successfully applied.
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()
    current_files = collect_files(repo_path)
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

    print_fn(f"  [agent] Sending {len(current_files)} file(s) + diagnostics to {model}...")

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = extract_json(response.content[0].text)

    try:
        new_files: dict = json.loads(raw)
    except json.JSONDecodeError as e:
        print_fn(f"  [agent] ERROR: could not parse response as JSON: {e}")
        print_fn(f"  First 800 chars:\n{raw[:800]}")
        return False

    if not isinstance(new_files, dict) or not new_files:
        print_fn("  [agent] ERROR: response was not a non-empty JSON object")
        return False

    print_fn(f"  [agent] Applying {len(new_files)} file(s):")
    for filename, content in new_files.items():
        dest = repo_path / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)
        print_fn(f"    + {filename}")

    return True


# ── Fix loop ──────────────────────────────────────────────────────────────────

def run_fix_loop(
    repo_path: Path,
    port: int,
    max_retries: int = 3,
    model: str = "claude-sonnet-4-6",
    wait: int = 30,
    verbose: bool = False,
    repo_name: str | None = None,
    language: str = "unknown",
    framework: str = "unknown",
    print_fn=print,
) -> bool:
    """Verify → fix → retry loop.

    Returns True if the repo passes verification within max_retries attempts.
    print_fn is injectable for CLI vs script use.
    """
    if repo_name is None:
        repo_name = repo_path.name

    for cycle in range(max_retries + 1):
        label = "initial verify" if cycle == 0 else f"re-verify after fix {cycle}"
        print_fn(f"[fix_loop] ── {label}")

        passed, diagnostics = verify_repo(repo_path, port, wait, verbose)

        if passed:
            print_fn(f"[fix_loop] ✓  PASS — {repo_name}")
            mark_progress(repo_name, "done", verified=True)
            return True

        print_fn(f"[fix_loop] ✗  FAIL")

        if cycle == max_retries:
            print_fn(f"[fix_loop] Exhausted {max_retries} fix attempt(s). Final diagnostics:\n")
            print_fn(diagnostics)
            mark_progress(repo_name, "failed")
            return False

        print_fn(f"[fix_loop] Invoking agent (fix {cycle + 1} of {max_retries})...")
        if not agent_fix(
            repo_path=repo_path,
            diagnostics=diagnostics,
            attempt=cycle + 1,
            model=model,
            repo_name=repo_name,
            language=language,
            framework=framework,
            port=port,
            print_fn=print_fn,
        ):
            print_fn("[fix_loop] Agent returned no usable fix — aborting.")
            return False

        print_fn("[fix_loop] Fix applied — re-verifying...")

    return False
