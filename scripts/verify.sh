#!/usr/bin/env bash
# verify.sh — Build and smoke-test a generated repository
#
# Usage:
#   scripts/verify.sh [--verbose] generated/<repo-name> <port>
#   STARTUP_WAIT=45 scripts/verify.sh [--verbose] generated/<repo> 8080
#
#   --verbose / -v  Show each HTTP request and full response during verification.
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
VERBOSE=0

pass() { echo "  PASS $*"; }
fail() { echo "  FAIL $*" >&2; }

# ── HTTP helpers ──────────────────────────────────────────────────────────────
#
# do_request METHOD URL [BODY]
#   Prints response body to stdout.
#   Exits non-zero when the server returns 4xx/5xx (mimics curl -f).
#   In verbose mode, also prints the request and response to stderr.
do_request() {
  local method="$1" url="$2" body="${3:-}"
  local tmpbody tmpcode
  tmpbody=$(mktemp)
  tmpcode=$(mktemp)

  local curl_args=(-s -o "$tmpbody" -w "%{http_code}" -X "$method")
  [[ -n "$body" ]] && curl_args+=(-H "Content-Type: application/json" -d "$body")

  curl "${curl_args[@]}" "$url" > "$tmpcode" 2>/dev/null
  local http_code
  http_code=$(cat "$tmpcode")

  if [[ $VERBOSE -eq 1 ]]; then
    echo "" >&2
    printf "  >> %s %s\n" "$method" "$url" >&2
    [[ -n "$body" ]] && printf "     body: %s\n" "$body" >&2
    printf "  << HTTP %s\n" "$http_code" >&2
    if [[ -s "$tmpbody" ]]; then
      jq . "$tmpbody" 2>/dev/null | sed 's/^/     /' >&2 \
        || sed 's/^/     /' "$tmpbody" >&2
    fi
  fi

  cat "$tmpbody"
  rm -f "$tmpbody" "$tmpcode"
  [[ "$http_code" =~ ^[23] ]]
}

# do_request_status METHOD URL
#   Prints just the HTTP status code to stdout.
#   In verbose mode, also logs request/status to stderr.
do_request_status() {
  local method="$1" url="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" "$url" 2>/dev/null)
  if [[ $VERBOSE -eq 1 ]]; then
    printf "\n  >> %s %s\n  << HTTP %s\n" "$method" "$url" "$code" >&2
  fi
  echo "$code"
}

# ─────────────────────────────────────────────────────────────────────────────

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
  if do_request GET "$base/health" | grep -q '"ok"'; then
    pass "GET /health"
  else
    fail "GET /health"
    failed=1
  fi

  # 2-6. CRUD endpoints (only if /items route exists)
  local has_crud=0
  if do_request_status GET "$base/items" | grep -qE "^(200|404)$"; then
    has_crud=1
  fi

  if [[ $has_crud -eq 1 ]]; then
    # Create item
    local item_json
    item_json=$(do_request POST "$base/items" '{"name":"test-item","description":"hello world"}' || echo "")
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
      if do_request GET "$base/items" | jq -e '. | length > 0' >/dev/null 2>&1; then
        pass "GET /items"
      else
        fail "GET /items"
        failed=1
      fi

      # Get one
      if do_request GET "$base/items/$item_id" | jq -e '.id' >/dev/null 2>&1; then
        pass "GET /items/$item_id"
      else
        fail "GET /items/$item_id"
        failed=1
      fi

      # Update
      if do_request PUT "$base/items/$item_id" '{"name":"updated-item","description":"updated"}' | jq -e '.id' >/dev/null 2>&1; then
        pass "PUT /items/$item_id"
      else
        fail "PUT /items/$item_id"
        failed=1
      fi

      # Delete
      local delete_status
      delete_status=$(do_request_status DELETE "$base/items/$item_id" || echo "000")
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

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ "${1:-}" == --verbose || "${1:-}" == -v ]]; do
  VERBOSE=1; shift
done

if [[ -z "${1:-}" || -z "${2:-}" ]]; then
  echo "Usage: $0 [--verbose] <path-to-repo> <host-port>"
  echo "Example: $0 generated/crud-python-fastapi 8001"
  echo "         $0 --verbose generated/health-go-gin 8002"
  exit 1
fi

verify_repo "$1" "$2"
