"""
repogen.cli — Click command group and all subcommands.

Entry point (pyproject.toml): repogen.cli:cli
"""

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

import click
import yaml

from repogen.core import (
    GENERATED_DIR,
    MATRIX_PATH,
    find_free_port,
    load_matrix,
    load_progress,
    mark_progress,
    save_progress,
    verify_repo,
    count_applications,
    count_endpoints,
    run_fix_loop,
    agent_fix,
)
from repogen.generate import (
    generate_from_template,
    generate_from_agent,
    generate_from_spec,
    TEMPLATES_DIR,
)

GREEN  = "\033[0;32m"
YELLOW = "\033[1;33m"
RED    = "\033[0;31m"
RESET  = "\033[0m"

def log(msg):   click.echo(f"{GREEN}[repogen]{RESET} {msg}")
def warn(msg):  click.echo(f"{YELLOW}[warn]{RESET} {msg}", err=True)
def error(msg): click.echo(f"{RED}[error]{RESET} {msg}", err=True)


# Wire click.echo into core functions that need a print_fn
def _click_print(msg):
    click.echo(msg)


@click.group()
@click.version_option("0.1.0")
def cli():
    """repogen — Generate synthetic benchmark repositories from a spec."""
    pass


# ── init ──────────────────────────────────────────────────────────────────────

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

    progress_data = load_progress()
    for r in repos:
        progress_data.setdefault("repos", {}).setdefault(
            r["name"], {"status": "pending", "generated_at": None, "verified": False}
        )
    save_progress(progress_data)

    log(f"Planned {len(repos)} repo(s) → matrix.yaml")
    log(f"Output directory: {output}/")


# ── generate ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--name", default=None, help="Generate only this repo")
@click.option("--model", default="claude-sonnet-4-6", help="Claude model for agent path")
@click.option("--force", is_flag=True, help="Re-generate even if already done")
def generate(name, model, force):
    """Generate repos from matrix.yaml. Uses templates where available, Claude API otherwise."""
    try:
        repos = load_matrix()
    except FileNotFoundError as e:
        error(str(e)); sys.exit(1)

    progress = load_progress().get("repos", {})

    if name:
        repos = [r for r in repos if r["name"] == name]
        if not repos:
            error(f"Repo '{name}' not found in matrix.yaml"); sys.exit(1)

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
            generate_from_template(repo, output_dir, template_name)
        else:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                warn(f"  No template for {rname} and ANTHROPIC_API_KEY is not set — skipping")
                mark_progress(rname, "failed")
                continue
            generate_from_agent(repo, output_dir, model)

        mark_progress(rname, "done")
        log(f"  Done → {output_dir}")


# ── verify ────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("repo_path", required=False, default=None)
@click.argument("port", type=int, required=False, default=None)
@click.option("--name", default=None, help="Verify a repo by name (looks up port from matrix.yaml)")
@click.option("--wait", default=30, show_default=True, help="Seconds to wait for service startup")
@click.option("--verbose", "-v", is_flag=True, help="Show each HTTP probe request and response")
def verify(repo_path, port, name, wait, verbose):
    """Build and probe a repo with Docker Compose.

    Can be used in three ways:

    \b
    1. Direct path + port:
         repogen verify generated/seapoint 8001

    2. By name (port auto-read from matrix.yaml):
         repogen verify --name crud-python-fastapi

    3. All unverified repos in matrix.yaml:
         repogen verify
    """
    if repo_path:
        path = Path(repo_path)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists():
            error(f"Directory not found: {path}"); sys.exit(1)

        resolved_port = port
        if resolved_port is None:
            try:
                match = next((r for r in load_matrix() if r["name"] == path.name), None)
                if match:
                    resolved_port = match["port"]
                    log(f"Port {resolved_port} read from matrix.yaml")
            except FileNotFoundError:
                pass
        if resolved_port is None:
            error("PORT argument is required (repo not found in matrix.yaml)"); sys.exit(1)

        log(f"Verifying {path.name} (port {resolved_port})...")
        passed, diagnostics = verify_repo(path, resolved_port, wait, verbose)
        if passed:
            log(f"PASS — {path.name}")
            mark_progress(path.name, "done", verified=True)
        else:
            error(f"FAIL — {path.name}")
            click.echo(diagnostics, err=True)
            mark_progress(path.name, "failed")
            sys.exit(1)
        return

    try:
        repos = load_matrix()
    except FileNotFoundError as e:
        error(str(e)); sys.exit(1)

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
        rport = repo["port"]

        if not output_dir.exists():
            warn(f"  {rname}: directory not found — skipping")
            continue

        log(f"Verifying {rname} (port {rport})...")
        passed, diagnostics = verify_repo(output_dir, rport, wait, verbose)
        if passed:
            log(f"  PASS")
            mark_progress(rname, "done", verified=True)
        else:
            error(f"  FAIL")
            click.echo(diagnostics, err=True)
            mark_progress(rname, "failed")
            failed.append(rname)

    if failed:
        error(f"\nFailed: {', '.join(failed)}")
        sys.exit(1)
    else:
        log("All repos verified.")


# ── fix_loop ──────────────────────────────────────────────────────────────────

@cli.command(name="fix_loop")
@click.argument("repo_path")
@click.argument("port", type=int, required=False, default=None)
@click.option("--max-retries", default=3, show_default=True, help="Fix attempts before giving up")
@click.option("--model", default="claude-sonnet-4-6", show_default=True, help="Claude model")
@click.option("--wait", default=30, show_default=True, help="Seconds to wait for service startup")
@click.option("--verbose", "-v", is_flag=True, help="Show each HTTP probe request and response")
def fix_loop(repo_path, port, max_retries, model, wait, verbose):
    """Verify a repo; on failure ask Claude to fix it and retry.

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

    resolved_port = port
    if resolved_port is None:
        try:
            match = next((r for r in load_matrix() if r["name"] == path.name), None)
            if match:
                resolved_port = match["port"]
                log(f"Port {resolved_port} read from matrix.yaml")
        except FileNotFoundError:
            pass
    if resolved_port is None:
        error("PORT argument is required (repo not found in matrix.yaml)"); sys.exit(1)

    repo_name = path.name
    parts = repo_name.split("-")
    language  = parts[1] if len(parts) > 1 else "unknown"
    framework = "-".join(parts[2:]) if len(parts) > 2 else "unknown"

    log(f"repo={repo_name}  port={resolved_port}  max_retries={max_retries}  model={model}")

    ok = run_fix_loop(
        repo_path=path, port=resolved_port, max_retries=max_retries,
        model=model, wait=wait, verbose=verbose,
        repo_name=repo_name, language=language, framework=framework,
        print_fn=_click_print,
    )
    sys.exit(0 if ok else 1)


# ── from_spec ─────────────────────────────────────────────────────────────────

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

    repo_name     = name or spec.stem.lower()
    output_dir    = Path(output) / repo_name
    resolved_port = port or find_free_port()

    log(f"spec    → {spec.name}")
    log(f"output  → {output_dir}")
    log(f"port    → {resolved_port}")
    log(f"model   → {model}")

    if output_dir.exists() and any(output_dir.iterdir()):
        warn(f"{output_dir} already exists — files will be overwritten")

    log("Generating repo from spec...")
    try:
        files = generate_from_spec(spec, repo_name, resolved_port, model)
    except ValueError as e:
        error(str(e)); sys.exit(1)

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

    log(f"Running fix_loop (up to {max_retries} repair cycles)...")

    parts = repo_name.split("-")
    language  = parts[1] if len(parts) > 1 else "unknown"
    framework = "-".join(parts[2:]) if len(parts) > 2 else "unknown"

    ok = run_fix_loop(
        repo_path=output_dir, port=resolved_port, max_retries=max_retries,
        model=model, wait=wait, verbose=False,
        repo_name=repo_name, language=language, framework=framework,
        print_fn=_click_print,
    )
    if not ok:
        error(f"{repo_name} still failing after {max_retries} repair attempt(s).")
        click.echo(f"  Files are in {output_dir}/ — inspect and fix manually.")
        sys.exit(1)


# ── endpoints ─────────────────────────────────────────────────────────────────

@cli.command(name="endpoints")
@click.argument("repo_path", required=False, default=None)
@click.option("--name", default=None, help="Analyse a repo by name (path read from matrix.yaml)")
@click.option("--all", "all_repos", is_flag=True, help="Analyse all verified repos in matrix.yaml")
@click.option("--model", default="claude-sonnet-4-6", show_default=True, help="Claude model for endpoint analysis")
@click.option("--output", default=None, help="Write results to this YAML file (default: <repo>/endpoints.yaml)")
def endpoints(repo_path, name, all_repos, model, output):
    """Count applications and endpoints in one or more generated repos.

    \b
    Examples:
      repogen endpoints generated/seapoint
      repogen endpoints --name crud-python-fastapi
      repogen endpoints --all
      repogen endpoints --all --output results/endpoints.yaml
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        error("ANTHROPIC_API_KEY is not set"); sys.exit(1)

    targets: list[Path] = []

    if repo_path:
        p = Path(repo_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists():
            error(f"Directory not found: {p}"); sys.exit(1)
        targets.append(p)
    elif name:
        try:
            repos = load_matrix()
            match = next((r for r in repos if r["name"] == name), None)
            if not match:
                error(f"Repo '{name}' not found in matrix.yaml"); sys.exit(1)
            targets.append(Path(match.get("output", "generated")) / name)
        except FileNotFoundError as e:
            error(str(e)); sys.exit(1)
    elif all_repos:
        try:
            repos = load_matrix()
            progress = load_progress().get("repos", {})
            for r in repos:
                if progress.get(r["name"], {}).get("verified"):
                    targets.append(Path(r.get("output", "generated")) / r["name"])
        except FileNotFoundError as e:
            error(str(e)); sys.exit(1)
        if not targets:
            log("No verified repos found in matrix.yaml.")
            return
    else:
        error("Provide a repo path, --name, or --all"); sys.exit(1)

    from datetime import timezone
    combined: list[dict] = []

    for path in targets:
        if not path.exists():
            warn(f"  {path.name}: directory not found — skipping")
            continue

        log(f"Analysing {path.name}...")

        apps = count_applications(path)
        log(f"  Applications: {len(apps)}")
        for a in apps:
            port_str = ", ".join(a["ports"]) if a["ports"] else "—"
            click.echo(f"    • {a['name']}  ({a['image']})  ports: {port_str}")

        log(f"  Endpoints: querying {model}...")
        eps = count_endpoints(path, model)
        log(f"  Endpoints: {len(eps)}")
        for e in eps:
            click.echo(f"    • {e.get('method','?'):<7} {e.get('path','?'):<30}  {e.get('description','')}")

        result = {
            "repo": path.name,
            "analysed_at": datetime.now(timezone.utc).isoformat(),
            "applications": {"count": len(apps), "services": apps},
            "endpoints": {"count": len(eps), "routes": eps},
        }

        per_repo_out = Path(output) if output and len(targets) == 1 else path / "endpoints.yaml"
        per_repo_out.write_text(yaml.dump(result, default_flow_style=False, sort_keys=False, allow_unicode=True))
        log(f"  Written → {per_repo_out}")
        combined.append(result)

    if output and len(targets) > 1:
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml.dump(combined, default_flow_style=False, sort_keys=False, allow_unicode=True))
        log(f"\nCombined results → {out_path}")


# ── coverage ──────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--report", default="gaps.md", help="Output file for gap report")
def coverage(report):
    """Analyse language/framework/size coverage and write a gap report."""
    try:
        repos = load_matrix()
    except FileNotFoundError as e:
        error(str(e)); sys.exit(1)

    progress = load_progress().get("repos", {})
    sfrs  = [r for r in repos if "services" not in r]
    monos = [r for r in repos if "services" in r]

    lang_fws: dict[str, list] = defaultdict(list)
    for r in sfrs:
        lang_fws[r["language"]].append(r["framework"])

    all_langs   = sorted(lang_fws.keys())
    done_count  = sum(1 for r in repos if progress.get(r["name"], {}).get("status") == "done")
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

    lang_pairs_covered: set = set()
    for m in monos:
        lang_set = sorted(set(s["language"] for s in m.get("services", [])))
        for pair in combinations(lang_set, 2):
            lang_pairs_covered.add(pair)

    all_pairs    = set(combinations(all_langs, 2))
    missing_pairs = all_pairs - lang_pairs_covered

    lines += ["\n## Language pair coverage\n\n", f"Covered: {len(lang_pairs_covered)} / {len(all_pairs)}\n"]
    if missing_pairs:
        lines.append("\nMissing pairs:\n")
        for p in sorted(missing_pairs):
            lines.append(f"- {p[0]} + {p[1]}\n")

    Path(report).write_text("".join(lines))
    log(f"Coverage report written to {Path(report)}")
    click.echo("".join(lines))


# ── push ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("repo_path", required=False, default=None)
@click.option("--org", required=True, help="GitHub organisation or username")
@click.option("--name", default=None, help="Push only this repo (looked up in matrix.yaml then generated/)")
@click.option("--private", is_flag=True, help="Create private repos")
def push(repo_path, org, name, private):
    """Push verified repos to GitHub.

    \b
    Examples:
      repogen push --org my-org generated/Seapoint   # direct path
      repogen push --org my-org --name Seapoint       # from matrix or generated/
      repogen push --org my-org                       # all verified in matrix.yaml
    """
    import subprocess as sp

    # Direct path argument — bypasses matrix.yaml entirely
    if repo_path:
        p = Path(repo_path)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists():
            error(f"Directory not found: {p}"); sys.exit(1)
        repos = [{"name": p.name, "output": str(p.parent)}]
    else:
        try:
            all_repos = load_matrix()
        except FileNotFoundError:
            all_repos = []

        progress = load_progress().get("repos", {})

        if name:
            repos = [r for r in all_repos if r["name"] == name]
            # Fall back to generated/<name> if not in matrix
            if not repos:
                fallback = ROOT / "generated" / name
                if fallback.exists():
                    repos = [{"name": name, "output": str(ROOT / "generated")}]
                else:
                    error(f"'{name}' not found in matrix.yaml and generated/{name} does not exist")
                    sys.exit(1)
        else:
            repos = [r for r in all_repos if progress.get(r["name"], {}).get("verified")]

    if not repos:
        log("No verified repos to push.")
        return

    try:
        token = sp.check_output(["gh", "auth", "token"], text=True).strip()
    except (sp.CalledProcessError, FileNotFoundError):
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
            if not (repo_path / ".git").exists():
                sp.run(["git", "init", "-b", "main"], cwd=repo_path, check=True, capture_output=True)
                sp.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
                sp.run(["git", "commit", "-m", f"Initial commit: {rname}"],
                       cwd=repo_path, check=True, capture_output=True)

            sp.run(["gh", "repo", "create", f"{org}/{rname}", visibility,
                    "--description", f"Synthetic benchmark repo: {rname}"],
                   check=True, capture_output=True)

            remote_url = (
                f"https://x-access-token:{token}@github.com/{org}/{rname}.git"
                if token else
                f"https://github.com/{org}/{rname}.git"
            )
            sp.run(["git", "remote", "add", "origin", remote_url], cwd=repo_path, capture_output=True)
            sp.run(["git", "remote", "set-url", "origin", remote_url], cwd=repo_path, capture_output=True)
            sp.run(["git", "push", "-u", "origin", "main"], cwd=repo_path, check=True, capture_output=True)

            log(f"  Done → https://github.com/{org}/{rname}")

        except sp.CalledProcessError as e:
            error(f"  Failed: {rname} — {e}")
            failed.append(rname)

    if failed:
        error(f"\nFailed: {', '.join(failed)}")
        sys.exit(1)


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
def status():
    """Show generation and verification status of all repos."""
    try:
        repos = load_matrix()
    except FileNotFoundError as e:
        error(str(e)); sys.exit(1)

    progress = load_progress().get("repos", {})

    click.echo(f"{'Repo':<40} {'Status':<12} {'Verified'}")
    click.echo("-" * 65)
    counts: dict[str, int] = {"done": 0, "pending": 0, "failed": 0, "in-progress": 0}
    for repo in repos:
        rname = repo["name"]
        info  = progress.get(rname, {})
        st    = info.get("status", "pending")
        verified = "✓" if info.get("verified") else ""
        counts[st] = counts.get(st, 0) + 1
        click.echo(f"{rname:<40} {st:<12} {verified}")

    click.echo("-" * 65)
    click.echo(f"Total: {len(repos)}  |  " + "  ".join(f"{k}: {v}" for k, v in counts.items() if v))
