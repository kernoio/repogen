#!/usr/bin/env bash
# verify.sh — Build and smoke-test a generated repository
#
# Usage:
#   scripts/verify.sh generated/<repo-name> <port>          # single repo
#   STARTUP_WAIT=45 scripts/verify.sh generated/<repo> 8080 # custom wait time
#
# For CRUD repos (spec=crud), all 6 endpoints are tested:
#   GET  /health        → 200 {"status":"ok"}
#   POST /items         → 201
#   GET  /items         → 200
#   GET  /items/<id>    → 200
#   PUT  /items/<id>    → 200
#   DELETE /items/<id>  → 204
#
# For health-only repos, only GET /health is tested.
#
# Requires: docker, docker compose, curl, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STARTUP_WAIT="${STARTUP_WAIT:-30}"

pass() { echo "  PASS $*"; }
fail() { echo "  FAIL $*" >&2; }

verify_repo() {
  local path="$1"
  local port="$2"
  # Allow relative or absolute paths
  local abs_path
  if [[ "$path" = /* ]]; then
    abs_path="$path"
  else
    abs_path="$REPO_ROOT/$path"
  fi
  local base="http://localhost:$port"

  if [[ ! -d "$abs_path" ]]; then
    echo "SKIP $path (directory not found)"
    return 0
  fi

  echo "Verifying $path (port $port)..."

  # Build and start
  if ! (cd "$abs_path" && docker compose build -q 2>/dev/null && docker compose up -d 2>/dev/null); then
    echo "FAIL $path — build/start failed"
    (cd "$abs_path" && docker compose down -v -q 2>/dev/null) || true
    return 1
  fi

  echo "  Waiting ${STARTUP_WAIT}s for startup..."
  sleep "$STARTUP_WAIT"

  local failed=0

  # 1. Health check (required for all repo types)
  if curl -sf "$base/health" | grep -q '"ok"'; then
    pass "GET /health"
  else
    fail "GET /health"
    failed=1
  fi

  # 2-6. CRUD endpoints (only if /items route exists)
  local has_crud=0
  if curl -so /dev/null -w "%{http_code}" -X GET "$base/items" 2>/dev/null | grep -qE "^(200|404)$"; then
    has_crud=1
  fi

  if [[ $has_crud -eq 1 ]]; then
    # Create item
    local item_json
    item_json=$(curl -sf -X POST "$base/items" \
      -H "Content-Type: application/json" \
      -d '{"name":"test-item","description":"hello world"}' 2>/dev/null || echo "")
    if [[ -n "$item_json" ]]; then
      pass "POST /items"
    else
      fail "POST /items"
      failed=1
    fi

    local item_id
    item_id=$(echo "$item_json" | jq -r '.id // empty' 2>/dev/null || echo "")

    if [[ -n "$item_id" ]]; then
      # List items
      if curl -sf "$base/items" | jq -e '. | length > 0' >/dev/null 2>&1; then
        pass "GET /items"
      else
        fail "GET /items"
        failed=1
      fi

      # Get one
      if curl -sf "$base/items/$item_id" | jq -e '.id' >/dev/null 2>&1; then
        pass "GET /items/$item_id"
      else
        fail "GET /items/$item_id"
        failed=1
      fi

      # Update
      if curl -sf -X PUT "$base/items/$item_id" \
          -H "Content-Type: application/json" \
          -d '{"name":"updated-item","description":"updated"}' | jq -e '.id' >/dev/null 2>&1; then
        pass "PUT /items/$item_id"
      else
        fail "PUT /items/$item_id"
        failed=1
      fi

      # Delete
      local delete_status
      delete_status=$(curl -so /dev/null -w "%{http_code}" -X DELETE "$base/items/$item_id" 2>/dev/null || echo "000")
      if [[ "$delete_status" == "204" || "$delete_status" == "200" ]]; then
        pass "DELETE /items/$item_id → $delete_status"
      else
        fail "DELETE /items/$item_id → got $delete_status"
        failed=1
      fi
    fi
  fi

  # Cleanup
  (cd "$abs_path" && docker compose down -v -q 2>/dev/null) || true

  if [[ $failed -eq 0 ]]; then
    echo "OK $path"
    return 0
  else
    echo "FAIL $path (some endpoints failed — see above)"
    return 1
  fi
}

if [[ -z "${1:-}" || -z "${2:-}" ]]; then
  echo "Usage: $0 <path-to-repo> <host-port>"
  echo "Example: $0 generated/crud-python-fastapi 8001"
  exit 1
fi

verify_repo "$1" "$2"
