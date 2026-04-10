#!/bin/bash
# Reply to a PR review comment.
# Usage: reply-to-comment.sh <owner> <repo> <number> <comment_id> <body> [hostname]
set -euo pipefail

owner="${1:?}" repo="${2:?}" number="${3:?}" comment_id="${4:?}" body="${5:?}" hostname="${6:-}"
host_flag=()
[[ -n "$hostname" ]] && host_flag=(--hostname "$hostname")

gh api "repos/$owner/$repo/pulls/$number/comments" "${host_flag[@]}" \
  -f body="$body" \
  -F in_reply_to="$comment_id"
