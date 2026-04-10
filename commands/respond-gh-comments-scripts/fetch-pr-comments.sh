#!/bin/bash
# Fetch review thread comments from a PR via GraphQL (paginated).
# Usage: fetch-pr-comments.sh <owner> <repo> <number> [hostname] [--user <login>]
# Output: One block per comment with ID, ThreadID, File, Line, Author, Body, InReplyTo
#
# Includes thread node ID in output, so fetch-thread-ids.sh is not needed separately.
set -euo pipefail

owner="${1:?}" repo="${2:?}" number="${3:?}"

# Parse remaining args for hostname and --user
hostname=""
filter_user=""
shift 3
while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) filter_user="${2:?'--user requires a value'}"; shift 2 ;;
    *)      hostname="$1"; shift ;;
  esac
done

host_flag=()
[[ -n "$hostname" ]] && host_flag=(--hostname "$hostname")

cursor=""
all_threads="[]"

while true; do
  after_clause=""
  [[ -n "$cursor" ]] && after_clause=", after: \\\"$cursor\\\""

  result=$(gh api graphql "${host_flag[@]}" -f query="
  {
    repository(owner: \"$owner\", name: \"$repo\") {
      pullRequest(number: $number) {
        reviewThreads(first: 50$after_clause) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            isResolved
            comments(first: 50) {
              nodes {
                databaseId
                author { login }
                body
                path
                line
                originalLine
                startLine
                diffHunk
                replyTo { databaseId }
              }
            }
          }
        }
      }
    }
  }")

  read -r has_next end_cursor < <(echo "$result" | python3 -c "
import json, sys
data = json.load(sys.stdin)
threads = data['data']['repository']['pullRequest']['reviewThreads']
pi = threads['pageInfo']
print(pi['hasNextPage'], pi.get('endCursor', ''))
")

  all_threads=$(echo "$result" | python3 -c "
import json, sys
data = json.load(sys.stdin)
existing = json.loads('''$all_threads''')
new = data['data']['repository']['pullRequest']['reviewThreads']['nodes']
existing.extend(new)
print(json.dumps(existing))
")

  [[ "$has_next" != "True" ]] && break
  cursor="$end_cursor"
done

echo "$all_threads" | python3 -c "
import json, sys

threads = json.load(sys.stdin)
filter_user = '''$filter_user'''

for thread in threads:
    thread_id = thread['id']
    is_resolved = thread['isResolved']
    for c in thread['comments']['nodes']:
        author = c['author']['login'] if c.get('author') else 'unknown'
        if filter_user and author != filter_user:
            continue
        reply_to = c['replyTo']['databaseId'] if c.get('replyTo') else 'N/A'
        line = c.get('line') or c.get('originalLine') or 'N/A'
        start_line = c.get('startLine') or 'N/A'
        print(f'ID: {c[\"databaseId\"]}')
        print(f'ThreadID: {thread_id}')
        print(f'Resolved: {is_resolved}')
        print(f'File: {c[\"path\"]}')
        print(f'Line: {line}')
        print(f'Start line: {start_line}')
        print(f'Author: {author}')
        hunk = c.get('diffHunk', '')
        if hunk:
            print('Diff hunk:')
            print(hunk)
        print(f'Body: {c[\"body\"]}')
        print(f'In reply to: {reply_to}')
        print('---')
"
