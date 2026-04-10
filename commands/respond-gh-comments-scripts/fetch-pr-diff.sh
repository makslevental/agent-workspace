#!/bin/bash
# Fetch the diff of a PR.
# Usage: fetch-pr-diff.sh <owner> <repo> <number> [hostname]
set -euo pipefail

owner="${1:?}" repo="${2:?}" number="${3:?}" hostname="${4:-}"
host_flag=()
[[ -n "$hostname" ]] && host_flag=(--hostname "$hostname")

gh api "repos/$owner/$repo/pulls/$number" "${host_flag[@]}" \
  -H "Accept: application/vnd.github.v3.diff"
