"""
repogen.generate — repository generation functions.

    from repogen.generate import generate_from_template, generate_from_agent, generate_from_spec
"""

import json
import shutil
import sys
import textwrap
from pathlib import Path

from repogen.core import (
    CLAUDE_MD,
    CRUD_SPEC,
    TEMPLATES_DIR,
    extract_json,
    load_matrix,
)

try:
    from jinja2 import Environment, FileSystemLoader, StrictUndefined
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False


def generate_from_template(repo: dict, output_dir: Path, template_name: str) -> None:
    """Render a Jinja2 template into output_dir."""
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
            dest.write_text(env.get_template(str(rel)).render(**ctx))
        else:
            shutil.copy2(item, dest)


def generate_from_agent(repo: dict, output_dir: Path, model: str) -> None:
    """Call the Claude API to generate repo files from a matrix entry."""
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        matrix = load_matrix()
        spec_path = Path(matrix[0].get("spec", "specs/crud.md")) if matrix else Path("specs/crud.md")
    except FileNotFoundError:
        spec_path = Path("specs/crud.md")
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
        print(f"  Could not parse agent response as JSON: {e}", file=sys.stderr)
        return

    for filename, content in files.items():
        dest = output_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content)


def generate_from_spec(
    spec_path: Path,
    repo_name: str,
    port: int,
    model: str = "claude-sonnet-4-6",
) -> dict[str, str]:
    """Call the Claude API to generate a repo from a Repo-spec document.

    Returns {filename: content} — the caller is responsible for writing files.
    """
    try:
        import anthropic
    except ImportError:
        sys.exit("anthropic package required: pip install anthropic")

    client = anthropic.Anthropic()
    spec_text = spec_path.read_text()
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
        - Host port:  {port}

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

    response = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = extract_json(response.content[0].text)

    try:
        files: dict = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Could not parse agent response as JSON: {e}\n{raw[:800]}")

    if not isinstance(files, dict) or not files:
        raise ValueError("Agent returned an empty or non-object response")

    return files
