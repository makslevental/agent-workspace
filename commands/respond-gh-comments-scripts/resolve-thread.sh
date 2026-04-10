#!/bin/bash
# Resolve a PR review thread by its GraphQL node ID.
# Usage: resolve-thread.sh <thread_node_id> [hostname]
set -euo pipefail

thread_id="${1:?Usage: resolve-thread.sh <thread_node_id> [hostname]}"
hostname="${2:-}"
host_flag=()
[[ -n "$hostname" ]] && host_flag=(--hostname "$hostname")

gh api graphql "${host_flag[@]}" -f query="
  mutation {
    resolveReviewThread(input: {threadId: \"$thread_id\"}) {
      thread { isResolved }
    }
  }"
