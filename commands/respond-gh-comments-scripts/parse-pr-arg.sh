#!/bin/bash
# Parse a PR argument (URL, owner/repo#number, or plain number) into components.
# Usage: parse-pr-arg.sh <pr_arg>
# Output: OWNER REPO NUMBER HOSTNAME (space-separated)
#
# Examples:
#   parse-pr-arg.sh https://github.com/llvm/llvm-project/pull/187191
#   parse-pr-arg.sh llvm/llvm-project#187191
#   parse-pr-arg.sh 187191

set -euo pipefail

arg="${1:?Usage: parse-pr-arg.sh <pr_arg>}"

if [[ "$arg" =~ ^https?://([^/]+)/([^/]+)/([^/]+)/pull/([0-9]+) ]]; then
  hostname="${BASH_REMATCH[1]}"
  owner="${BASH_REMATCH[2]}"
  repo="${BASH_REMATCH[3]}"
  number="${BASH_REMATCH[4]}"
elif [[ "$arg" =~ ^([^/]+)/([^#]+)#([0-9]+)$ ]]; then
  owner="${BASH_REMATCH[1]}"
  repo="${BASH_REMATCH[2]}"
  number="${BASH_REMATCH[3]}"
  hostname=""
elif [[ "$arg" =~ ^[0-9]+$ ]]; then
  # Plain number — infer hostname and repo from git remote
  remote_url=$(git remote get-url origin 2>/dev/null || true)
  if [[ "$remote_url" =~ (github\.[^/:]+)[:/]([^/]+)/([^/.]+) ]]; then
    hostname="${BASH_REMATCH[1]}"
    owner="${BASH_REMATCH[2]}"
    repo="${BASH_REMATCH[3]}"
  else
    echo "ERROR: Cannot infer owner/repo from git remote: $remote_url" >&2
    exit 1
  fi
  number="$arg"
else
  echo "ERROR: Cannot parse PR argument: $arg" >&2
  echo "Expected: URL, owner/repo#number, or plain number" >&2
  exit 1
fi

echo "$owner $repo $number $hostname"
