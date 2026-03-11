# Spec: Edge Case Repositories

Generate repositories that intentionally exhibit specific broken or unusual patterns. These are used to test that agentic systems can detect, diagnose, and handle edge cases correctly.

## Edge case types

### 1. Missing Dockerfile

The repository contains application source code but no Dockerfile and no docker-compose.yml.

- **Purpose:** Test that the agent can detect a missing Dockerfile and generate one from scratch
- **Naming:** `edge-missing-dockerfile-<language>-<framework>`
- **Contents:** Source code + README only

### 2. Broken Dockerfile (bad base image)

The Dockerfile references a base image that does not exist on Docker Hub.

```dockerfile
FROM nonexistent-image:99.99
COPY . .
CMD ["./app"]
```

- **Purpose:** Test that the agent detects the pull error and substitutes the correct base image
- **Naming:** `edge-bad-image-<language>-<framework>`

### 3. Wrong port

The application listens on port 8080 internally, but `docker-compose.yml` maps host port 3000 to container port 3000 — the app is unreachable.

- **Purpose:** Test that the agent can identify port mismatches from build logs and compose config
- **Naming:** `edge-wrong-port-<language>-<framework>`

### 4. Missing health endpoint

The service starts and runs, but has no `/health` route. All requests return 404.

- **Purpose:** Test that the agent notices the missing route in the health probe failure and adds it
- **Naming:** `edge-no-health-<language>-<framework>`

### 5. Missing dependency

The application imports a library that is not listed in the requirements/package manifest, so the build fails with a missing module error.

- **Purpose:** Test that the agent can read build errors, identify the missing package, and add it to the manifest
- **Naming:** `edge-missing-dep-<language>-<framework>`

### 6. Non-standard structure

The application source is in a non-standard location (e.g., `code/` instead of `src/`) and the Dockerfile COPY path is wrong.

- **Purpose:** Test that the agent can read the Dockerfile and source layout, identify the mismatch, and fix the COPY instruction
- **Naming:** `edge-bad-path-<language>-<framework>`

## Notes

- Edge case repos do NOT need to pass verification — their value is that they **fail in specific, documented ways**
- Include a `README.md` describing the intended failure and what a correct fix looks like
- Use `edge-` prefix consistently so the CLI can identify and exclude them from coverage metrics
- These repos are particularly useful for evaluating agentic repair systems: provide the broken repo, measure whether the agent produces a working fix
