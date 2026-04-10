#!/bin/bash
# Tests for parse-pr-arg.sh and fetch-pr-comments.sh.
# Usage: test-scripts.sh
# Requires: gh auth for github.com (for live fetch tests)
set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

# ── helpers ──────────────────────────────────────────────────────────────────

green() { printf '\033[32m✓\033[0m %s\n' "$*"; }
red()   { printf '\033[31m✗\033[0m %s\n' "$*"; }

assert_eq() {
  local desc="$1" expected="$2" actual="$3"
  if [[ "$actual" == "$expected" ]]; then
    green "$desc"
    PASS=$((PASS + 1))
  else
    red "$desc"
    echo "    expected: $expected"
    echo "    actual:   $actual"
    FAIL=$((FAIL + 1))
  fi
}

assert_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -qF -- "$needle"; then
    green "$desc"
    PASS=$((PASS + 1))
  else
    red "$desc"
    echo "    expected to contain: $needle"
    echo "    actual output (first 5 lines):"
    echo "$haystack" | head -5 | sed 's/^/      /'
    FAIL=$((FAIL + 1))
  fi
}

assert_not_contains() {
  local desc="$1" needle="$2" haystack="$3"
  if ! echo "$haystack" | grep -qF -- "$needle"; then
    green "$desc"
    PASS=$((PASS + 1))
  else
    red "$desc"
    echo "    expected NOT to contain: $needle"
    FAIL=$((FAIL + 1))
  fi
}

assert_exits_nonzero() {
  local desc="$1"; shift
  if ! "$@" >/dev/null 2>&1; then
    green "$desc"
    PASS=$((PASS + 1))
  else
    red "$desc"
    echo "    expected non-zero exit but got 0"
    FAIL=$((FAIL + 1))
  fi
}

# ── parse-pr-arg.sh ───────────────────────────────────────────────────────────

echo ""
echo "=== parse-pr-arg.sh ==="
echo ""

PARSE="$SCRIPTS_DIR/parse-pr-arg.sh"

# Full URL — github.com
out=$("$PARSE" "https://github.com/llvm/llvm-project/pull/187191")
assert_eq "full github.com URL" "llvm llvm-project 187191 github.com" "$out"

# Full URL — enterprise host
out=$("$PARSE" "https://github.example.com/org/myrepo/pull/42")
assert_eq "enterprise URL" "org myrepo 42 github.example.com" "$out"

# owner/repo#number
out=$("$PARSE" "llvm/llvm-project#187191")
assert_contains "owner/repo#number: owner"  "llvm"       "$out"
assert_contains "owner/repo#number: repo"   "llvm-project" "$out"
assert_contains "owner/repo#number: number" "187191"     "$out"

# Plain number — inferred from git remote
out=$("$PARSE" "187191")
assert_contains "plain number: number" "187191" "$out"

# Invalid input
assert_exits_nonzero "invalid arg exits non-zero" "$PARSE" "not-a-pr"

# ── fetch-pr-comments.sh ─────────────────────────────────────────────────────

echo ""
echo "=== fetch-pr-comments.sh (live — https://github.com/llvm/llvm-project/pull/187191) ==="
echo ""

FETCH="$SCRIPTS_DIR/fetch-pr-comments.sh"
OWNER="llvm"
REPO="llvm-project"
NUMBER="187191"
HOST="github.com"

# Fetch all comments
all=$("$FETCH" "$OWNER" "$REPO" "$NUMBER" "$HOST")

assert_contains "output contains ID field"       "ID: "       "$all"
assert_contains "output contains ThreadID field" "ThreadID: " "$all"
assert_contains "output contains Resolved field" "Resolved: " "$all"
assert_contains "output contains File field"     "File: "     "$all"
assert_contains "output contains Author field"   "Author: "   "$all"
assert_contains "output contains Body field"     "Body: "     "$all"
assert_contains "output contains separator"      "---"        "$all"

# Confirm multiple comments are returned
comment_count=$(echo "$all" | grep -c '^ID: ' || true)
if [[ "$comment_count" -gt 1 ]]; then
  green "returns multiple comments ($comment_count)"
  PASS=$((PASS + 1))
else
  red "expected multiple comments, got $comment_count"
  FAIL=$((FAIL + 1))
fi

# --user filter: pick the first author from the output and filter by them
first_author=$(echo "$all" | grep '^Author: ' | head -1 | cut -d' ' -f2)
filtered=$("$FETCH" "$OWNER" "$REPO" "$NUMBER" "$HOST" --user "$first_author")
assert_contains     "--user $first_author: returns their comments"  "Author: $first_author" "$filtered"

# --user filter: nonexistent user returns no output
nobody=$("$FETCH" "$OWNER" "$REPO" "$NUMBER" "$HOST" --user nonexistent-user-xyz-abc 2>&1 || true)
assert_eq "--user nonexistent: empty output" "" "$nobody"

# ThreadID format check (base64-encoded GraphQL node ID)
first_thread=$(echo "$all" | grep '^ThreadID: ' | head -1 | cut -d' ' -f2)
if [[ "$first_thread" =~ ^[A-Za-z0-9+/=_-]+$ ]]; then
  green "ThreadID looks like a valid base64 node ID"
  PASS=$((PASS + 1))
else
  red "ThreadID format unexpected: $first_thread"
  FAIL=$((FAIL + 1))
fi

# ── summary ──────────────────────────────────────────────────────────────────

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
echo ""
[[ "$FAIL" -eq 0 ]]
