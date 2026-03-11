#!/usr/bin/env python3
"""
repogen — Generate synthetic benchmark repositories from a spec and language list.

Usage:
    repogen init     --spec specs/crud.md --langs languages.yaml
    repogen generate [--name repo-name] [--model MODEL] [--force]
    repogen verify   [--name repo-name] [--wait 30]
    repogen coverage [--report gaps.md]
    repogen push     --org my-org [--name repo-name] [--private]
    repogen status
"""

import json
import os
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

try:
    import click
except ImportError:
    sys.exit("Error: click required. Install with: pip install click")

try:
    import yaml
except ImportError:
    sys.exit("Error: PyYAML required. Install with: pip install pyyaml")

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False

ROOT = Path(__file__).parent
MATRIX_PATH = ROOT / "matrix.yaml"
PROGRESS_PATH = ROOT / "progress.yaml"
TEMPLATES_DIR = ROOT / "templates"
GENERATED_DIR = ROOT / "generated"

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
RESET = "\033[0m"

def log(msg):   click.echo(f"{GREEN}[repogen]{RESET} {msg}")
def warn(msg):  click.echo(f"{YELLOW}[warn]{RESET} {msg}", err=True)
def error(msg): click.echo(f"{RED}[error]{RESET} {msg}", err=True)


# ── Progress helpers ────────────────────────────────────────────────────────

def load_progress() -> dict:
    if not PROGRESS_PATH.exists():
        return {"repos": {}}
    with open(PROGRESS_PATH) as f:
        return yaml.safe_load(f) or {"repos": {}}

def save_progress(data: dict):
    with open(PROGRESS_PATH, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

def mark_progress(name: str, status: str, verified: bool = False):
    data = load_progress()
    now = datetime.now(timezone.utc).isoformat()
    data.setdefault("repos", {})[name] = {
        "status": status,
        "generated_at": now if status == "done" else None,
        "verified": verified,
    }
    save_progress(data)


# ── Matrix helpers ──────────────────────────────────────────────────────────

def load_matrix() -> list[dict]:
    if not MATRIX_PATH.exists():
        sys.exit(f"matrix.yaml not found. Run: repogen init --spec <spec> --langs <langs>")
    with open(MATRIX_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("repos", [])


# ── CLI ─────────────────────────────────────────────────────────────────────

@click.group()
@click.version_option("0.1.0")
def cli():
    """repogen — Generate synthetic benchmark repositories from a spec."""
    pass


@cli.command()
@click.option("--spec", required=True, type=click.Path(exists=True), help="Spec file (.md or .yaml)")
@click.option("--langs", default="languages.yaml", type=click.Path(exists=True), help="languages.yaml path")
@click.option("--output", default="generated", help="Output directory for repos")
def init(spec, langs, output):
    """Read spec + language list, plan all combinations, write matrix.yaml."""
    with open(langs) as f:
        lang_data = yaml.safe_load(f)

    langs_list = lang_data.get("languages", [])
    repos = []
    port = 9000

    for lang_entry in langs_list:
        lang = lang_entry["name"]
        for fw_entry in lang_entry.get("frameworks", []):
            fw = fw_entry["name"]
            internal_port = lang_entry.get("default_internal_port", 8080)
            start_period = lang_entry.get("healthcheck_start_period", 30)
            template = fw_entry.get("template")
            repos.append({
                "name": f"repo-{lang}-{fw}",
                "language": lang,
                "framework": fw,
                "port": port,
                "internal_port": internal_port,
                "start_period": start_period,
                "template": template,
                "output": output,
            })
            port += 1

    matrix = {"spec": str(spec), "output": output, "repos": repos}
    with open(MATRIX_PATH, "w") as f:
        yaml.dump(matrix, f, default_flow_style=False, sort_keys=False)

    # Initialise progress
    progress_data = load_progress()
    for r in repos:
        progress_data.setdefault("repos", {}).setdefault(
            r["name"], {"status": "pending", "generated_at": None, "verified": False}
        )
    save_progress(progress_data)

    log(f"Planned {len(repos)} repo(s) → matrix.yaml")
    log(f"Output directory: {output}/")


@cli.command()
@click.option("--name", default=None, help="Generate only this repo")
@click.option("--model", default="claude-sonnet-4-6", help="Claude model for agent path")
@click.option("--force", is_flag=True, help="Re-generate even if already done")
def generate(name, model, force):
    """Generate repos from matrix.yaml. Uses templates where available, Claude API otherwise."""
    repos = load_matrix()
    progress = load_progress().get("repos", {})

    if name:
        repos = [r for r in repos if r["name"] == name]
        if not repos:
            error(f"Repo '{name}' not found in matrix.yaml")
            sys.exit(1)

    pending = [
        r for r in repos
        if force or progress.get(r["name"], {}).get("status") not in ("done",)
    ]

    if not pending:
        log("Nothing to generate — all repos are done. Use --force to regenerate.")
        return

    log(f"Generating {len(pending)} repo(s)...")

    for repo in pending:
        rname = repo["name"]
        output_dir = Path(repo.get("output", "generated")) / rname
        template_name = repo.get("template")

        log(f"  {rname}")
        mark_progress(rname, "in-progress")

        if template_name and (TEMPLATES_DIR / template_name).exists():
            _generate_from_template(repo, output_dir, template_name)
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                warn(f"  No template for {rname} and ANTHROPIC_API_KEY is not set — skipping")
                mark_progress(rname, "failed")
                continue
            _generate_from_agent(repo, output_dir, model)

        mark_progress(rname, "done")
        log(f"  Done → {output_dir}")


def _generate_from_template(repo: dict, output_dir: Path, template_name: str):
    """Render Jinja2 template to output_dir."""
    if not HAS_JINJA2:
        sys.exit("Jinja2 required for template rendering: pip install jinja2")

    src = TEMPLATES_DIR / template_name
    output_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(src)),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )

    ctx = {
        "repo_name": repo["name"],
        "language": repo["language"],
        "framework": repo["framework"],
        "port": repo["port"],
        "internal_port": repo["internal_port"],
        "orm": repo.get("orm", ""),
    }

    for item in src.rglob("*"):
        if item.is_dir():
            continue
        rel = item.relative_to(src)
        dest = output_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        if item.suffix == ".j2":
            dest = dest.with_suffix("")
            template = env.get_template(str(rel))
            dest.write_text(template.render(**ctx))
        else:
            shutil.copy2(item, dest)


def _generate_from_agent(repo: dict, output_dir: Path, model: str):
    """Call Claude API to generate repo files, with retry on failure."""
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required for agent path: pip install anthropic")

    client = anthropic.Anthropic()
    output_dir.mkdir(parents=True, exist_ok=True)

    spec_path = Path(load_matrix()[0].get("spec", "specs/crud.md") if load_matrix() else "specs/crud.md")
    spec_text = spec_path.read_text() if spec_path.exists() else ""

    prompt = textwrap.dedent(f"""
        Generate a minimal Dockerized repository for the following stack:

        Language: {repo['language']}
        Framework: {repo['framework']}
        Repo name: {repo['name']}
        Host port: {repo['port']}
        Internal port: {repo['internal_port']}

        Spec:
        {spec_text}

        Required files (return as a JSON object mapping filename → file content):
        - Dockerfile
        - docker-compose.yml
        - .gitignore
        - .dockerignore
        - README.md
        - All source files needed for the service

        The service MUST expose GET /health → {{"status": "ok"}} with HTTP 200.
        Return ONLY a JSON object, no other text.
    """)

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(raw.split("\n")[1:-1])

    try:
        files = json.loads(raw)
    except json.JSONDecodeError as e:
        error(f"  Could not parse agent response as JSON: {e}")
        return

    for filename, content in files.items():
        dest = output_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)

    log(f"  Agent generated {len(files)} file(s) for {repo['name']}")


@cli.command()
@click.option("--name", default=None, help="Verify only this repo")
@click.option("--wait", default=30, help="Seconds to wait for service startup")
def verify(name, wait):
    """Build and probe repos with Docker Compose."""
    repos = load_matrix()
    progress = load_progress().get("repos", {})

    if name:
        repos = [r for r in repos if r["name"] == name]
    else:
        repos = [r for r in repos if progress.get(r["name"], {}).get("status") == "done"
                 and not progress.get(r["name"], {}).get("verified")]

    if not repos:
        log("No repos to verify.")
        return

    failed = []
    for repo in repos:
        rname = repo["name"]
        output_dir = Path(repo.get("output", "generated")) / rname
        port = repo["port"]

        log(f"Verifying {rname} (port {port})...")

        if not output_dir.exists():
            warn(f"  Directory not found: {output_dir} — skipping")
            continue

        try:
            subprocess.run(
                ["docker", "compose", "build"],
                cwd=output_dir, check=True, capture_output=True
            )
            subprocess.run(
                ["docker", "compose", "up", "-d"],
                cwd=output_dir, check=True, capture_output=True
            )

            import time
            log(f"  Waiting {wait}s for startup...")
            time.sleep(wait)

            result = subprocess.run(
                ["curl", "-sf", f"http://localhost:{port}/health"],
                capture_output=True, text=True
            )

            subprocess.run(
                ["docker", "compose", "down"],
                cwd=output_dir, capture_output=True
            )

            if result.returncode == 0 and "ok" in result.stdout:
                log(f"  PASS — {result.stdout.strip()}")
                mark_progress(rname, "done", verified=True)
            else:
                error(f"  FAIL — health probe returned: {result.stdout.strip() or '(empty)'}")
                mark_progress(rname, "failed")
                failed.append(rname)

        except subprocess.CalledProcessError as e:
            error(f"  Build/start failed for {rname}: {e}")
            subprocess.run(["docker", "compose", "down"], cwd=output_dir, capture_output=True)
            mark_progress(rname, "failed")
            failed.append(rname)

    if failed:
        error(f"\nFailed: {', '.join(failed)}")
        sys.exit(1)
    else:
        log("All repos verified.")


@cli.command()
@click.option("--report", default="gaps.md", help="Output file for gap report")
def coverage(report):
    """Analyse language/framework/size coverage and write a gap report."""
    repos = load_matrix()
    progress = load_progress().get("repos", {})

    sfrs = [r for r in repos if "services" not in r]
    monos = [r for r in repos if "services" in r]

    from collections import defaultdict
    from itertools import combinations

    lang_fws = defaultdict(list)
    for r in sfrs:
        lang_fws[r["language"]].append(r["framework"])

    all_langs = sorted(lang_fws.keys())

    done_count = sum(1 for r in repos if progress.get(r["name"], {}).get("status") == "done")
    verified_count = sum(1 for r in repos if progress.get(r["name"], {}).get("verified"))

    lines = [
        "# Coverage Report\n",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        f"Total repos: {len(repos)} | Done: {done_count} | Verified: {verified_count}\n\n",
        "## Languages and frameworks\n\n",
        "| Language | Frameworks | Count |\n",
        "|----------|------------|:-----:|\n",
    ]
    for lang in all_langs:
        fws = lang_fws[lang]
        lines.append(f"| {lang} | {', '.join(fws)} | {len(fws)} |\n")

    if monos:
        sizes = sorted(set(len(m.get("services", [])) for m in monos))
        lines += [
            "\n## Monorepo sizes\n\n",
            f"Covered sizes: {sizes}\n",
            f"Missing (2–{max(sizes)}): {sorted(set(range(2, max(sizes)+1)) - set(sizes))}\n",
        ]

    # Language pair coverage
    lang_pairs_covered = set()
    for m in monos:
        lang_set = sorted(set(s["language"] for s in m.get("services", [])))
        for pair in combinations(lang_set, 2):
            lang_pairs_covered.add(pair)

    all_pairs = set(combinations(all_langs, 2))
    missing_pairs = all_pairs - lang_pairs_covered

    lines += [
        "\n## Language pair coverage\n\n",
        f"Covered: {len(lang_pairs_covered)} / {len(all_pairs)}\n",
    ]
    if missing_pairs:
        lines.append("\nMissing pairs:\n")
        for p in sorted(missing_pairs):
            lines.append(f"- {p[0]} + {p[1]}\n")

    report_path = Path(report)
    report_path.write_text("".join(lines))
    log(f"Coverage report written to {report_path}")
    click.echo("".join(lines))


@cli.command()
@click.option("--org", required=True, help="GitHub organisation or username")
@click.option("--name", default=None, help="Push only this repo")
@click.option("--private", is_flag=True, help="Create private repos")
def push(org, name, private):
    """Push verified repos to GitHub."""
    repos = load_matrix()
    progress = load_progress().get("repos", {})

    if name:
        repos = [r for r in repos if r["name"] == name]
    else:
        repos = [r for r in repos if progress.get(r["name"], {}).get("verified")]

    if not repos:
        log("No verified repos to push.")
        return

    try:
        token = subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        token = ""
        warn("Could not get gh auth token — will attempt push without auth")

    visibility = "--private" if private else "--public"
    failed = []

    for repo in repos:
        rname = repo["name"]
        repo_path = Path(repo.get("output", "generated")) / rname

        if not repo_path.exists():
            warn(f"  {rname}: directory not found — skipping")
            continue

        log(f"Pushing {rname} → {org}/{rname}")

        try:
            # git init if needed
            if not (repo_path / ".git").exists():
                subprocess.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
                subprocess.run(
                    ["git", "commit", "-m", f"Initial commit: {rname}"],
                    cwd=repo_path, check=True, capture_output=True
                )

            # Create remote
            subprocess.run(
                ["gh", "repo", "create", f"{org}/{rname}", visibility,
                 "--description", f"Synthetic benchmark repo: {rname}"],
                check=True, capture_output=True
            )

            # Set remote URL with token auth
            if token:
                remote_url = f"https://x-access-token:{token}@github.com/{org}/{rname}.git"
            else:
                remote_url = f"https://github.com/{org}/{rname}.git"

            subprocess.run(["git", "remote", "add", "origin", remote_url],
                           cwd=repo_path, capture_output=True)
            subprocess.run(["git", "remote", "set-url", "origin", remote_url],
                           cwd=repo_path, capture_output=True)
            subprocess.run(["git", "push", "-u", "origin", "main"],
                           cwd=repo_path, check=True, capture_output=True)

            log(f"  Done → https://github.com/{org}/{rname}")

        except subprocess.CalledProcessError as e:
            error(f"  Failed: {rname} — {e}")
            failed.append(rname)

    if failed:
        error(f"\nFailed: {', '.join(failed)}")
        sys.exit(1)


@cli.command()
def status():
    """Show generation and verification status of all repos."""
    repos = load_matrix()
    progress = load_progress().get("repos", {})

    click.echo(f"{'Repo':<40} {'Status':<12} {'Verified'}")
    click.echo("-" * 65)
    counts = {"done": 0, "pending": 0, "failed": 0, "in-progress": 0}
    for repo in repos:
        name = repo["name"]
        info = progress.get(name, {})
        st = info.get("status", "pending")
        verified = "✓" if info.get("verified") else ""
        counts[st] = counts.get(st, 0) + 1
        click.echo(f"{name:<40} {st:<12} {verified}")

    click.echo("-" * 65)
    click.echo(f"Total: {len(repos)}  |  " + "  ".join(f"{k}: {v}" for k, v in counts.items() if v))


if __name__ == "__main__":
    cli()
