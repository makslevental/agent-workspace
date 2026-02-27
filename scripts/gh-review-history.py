#!/usr/bin/env python3
"""Collect a user's GitHub code review history and output as markdown.

Usage:
    python3 gh-review-history.py USERNAME ORG [-d DAYS] [-n COUNT] [-o DIR] [-v]

Specify -d for time-based collection, -n for count-based, or both.
Defaults to -d 7 when neither is given.

Requires: gh CLI installed and authenticated.
"""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone


def log(msg, verbose=True):
    if verbose:
        print(msg, file=sys.stderr)


def run_gh(args, verbose=False):
    """Run a gh CLI command and return parsed JSON output."""
    cmd = ["gh"] + args
    if verbose:
        log(f"  $ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "rate limit" in stderr.lower() or "API rate limit" in stderr:
            raise RuntimeError(f"GitHub API rate limit hit: {stderr}")
        raise RuntimeError(f"gh command failed: {' '.join(cmd)}\n{stderr}")
    if not result.stdout.strip():
        return []
    return json.loads(result.stdout)


def check_gh():
    """Verify gh is installed and authenticated."""
    try:
        subprocess.run(["gh", "auth", "status"], capture_output=True, check=True)
    except FileNotFoundError:
        print("Error: 'gh' CLI not found. Install from https://cli.github.com/", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("Error: 'gh' not authenticated. Run 'gh auth login' first.", file=sys.stderr)
        sys.exit(1)


GH_SEARCH_MAX = 1000  # GitHub search API hard limit per query


def search_reviewed_prs(username, org, since_date, max_count, verbose):
    """Search for PRs reviewed by the user in the given org.

    Args:
        since_date: If set, only return PRs updated after this date.
        max_count: If set, return at most this many PRs. If None, fetch all (up to GH limits).

    When since_date is set and results might exceed 1000, the date range is
    chunked into smaller windows to work around the GitHub search API limit.
    """
    def _search(since_str=None, until_str=None, limit=GH_SEARCH_MAX):
        cmd = [
            "search", "prs",
            f"--reviewed-by={username}",
            f"--owner={org}",
            f"--limit={limit}",
            "--json=number,title,url,repository,state,updatedAt",
        ]
        if since_str and until_str:
            cmd.append(f"--updated={since_str}..{until_str}")
        elif since_str:
            cmd.append(f"--updated=>{since_str}")
        return run_gh(cmd, verbose)

    cap = max_count or GH_SEARCH_MAX

    if since_date:
        date_str = since_date.strftime("%Y-%m-%d")
        log(f"Searching PRs reviewed by {username} in {org} since {date_str}...", verbose)
    else:
        log(f"Searching last {cap} PRs reviewed by {username} in {org}...", verbose)

    try:
        if not since_date:
            # Count-only mode: single search, capped.
            data = _search(limit=min(cap, GH_SEARCH_MAX))
        else:
            # Time-based: try a single search first.
            data = _search(since_str=since_date.strftime("%Y-%m-%d"),
                           limit=min(cap, GH_SEARCH_MAX))
            # If we hit the 1000-result ceiling, chunk by month.
            if len(data) >= GH_SEARCH_MAX and (not max_count or cap > GH_SEARCH_MAX):
                log(f"  Hit {GH_SEARCH_MAX}-result limit, chunking by month...", verbose)
                data = _chunked_search(username, org, since_date, cap, verbose, _search)
    except RuntimeError as e:
        if "rate limit" in str(e).lower():
            print(f"Error: {e}", file=sys.stderr)
            print("The search API allows 30 requests/minute. Wait and retry.", file=sys.stderr)
            sys.exit(1)
        raise

    # Deduplicate by PR URL (chunks may overlap at boundaries).
    seen = set()
    unique = []
    for pr in data:
        url = pr.get("url", "")
        if url not in seen:
            seen.add(url)
            unique.append(pr)

    # Apply count cap.
    if max_count and len(unique) > max_count:
        unique = unique[:max_count]

    log(f"Found {len(unique)} PRs", verbose)
    return unique


def _chunked_search(username, org, since_date, cap, verbose, search_fn):
    """Break the date range into monthly chunks to get past the 1000-result limit."""
    now = datetime.now(timezone.utc)
    all_data = []
    chunk_start = since_date
    while chunk_start < now and len(all_data) < cap:
        chunk_end = min(chunk_start + timedelta(days=30), now)
        s = chunk_start.strftime("%Y-%m-%d")
        e = chunk_end.strftime("%Y-%m-%d")
        remaining = cap - len(all_data)
        log(f"  Chunk {s} .. {e} (have {len(all_data)}, need up to {remaining} more)", verbose)
        chunk = search_fn(since_str=s, until_str=e,
                          limit=min(remaining, GH_SEARCH_MAX))
        all_data.extend(chunk)
        if len(chunk) >= GH_SEARCH_MAX:
            log(f"  Warning: chunk {s}..{e} also hit {GH_SEARCH_MAX} results; "
                "some PRs may be missing. Try a shorter --days window.", verbose)
        chunk_start = chunk_end
    return all_data


def fetch_pr_reviews(owner, repo, number, verbose):
    """Fetch all reviews for a PR."""
    try:
        return run_gh([
            "api", f"repos/{owner}/{repo}/pulls/{number}/reviews",
            "--paginate",
        ], verbose)
    except RuntimeError as e:
        log(f"  Warning: failed to fetch reviews for {owner}/{repo}#{number}: {e}")
        return []


def fetch_pr_comments(owner, repo, number, verbose):
    """Fetch all review comments (inline) for a PR."""
    try:
        return run_gh([
            "api", f"repos/{owner}/{repo}/pulls/{number}/comments",
            "--paginate",
        ], verbose)
    except RuntimeError as e:
        log(f"  Warning: failed to fetch comments for {owner}/{repo}#{number}: {e}")
        return []


def parse_repo(pr):
    """Extract owner and repo name from a search result PR."""
    repo_info = pr.get("repository", {})
    name = repo_info.get("nameWithOwner", "") or repo_info.get("name", "")
    if "/" in name:
        return name.split("/", 1)
    owner = repo_info.get("owner", {}).get("login", "")
    return owner, name


def format_time(iso_str):
    """Format an ISO timestamp to a readable UTC string."""
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, TypeError):
        return iso_str


def format_date(iso_str):
    """Format an ISO timestamp to just a date."""
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return iso_str


def truncate_diff(diff_hunk, max_lines=20):
    """Truncate a diff hunk to max_lines."""
    if not diff_hunk:
        return ""
    lines = diff_hunk.split("\n")
    if len(lines) <= max_lines:
        return diff_hunk
    return "\n".join(lines[:max_lines]) + f"\n... ({len(lines) - max_lines} more lines)"


def build_threads(comments, username):
    """Group comments into threads. Keep threads where target user participated.

    Returns list of threads, each thread is a list of comments sorted chronologically.
    The first comment in each thread is the root (has diff_hunk context).
    """
    by_id = {c["id"]: c for c in comments}

    # Find root for each comment by following in_reply_to_id chains.
    def find_root(c):
        visited = set()
        while c.get("in_reply_to_id") and c["in_reply_to_id"] in by_id:
            if c["id"] in visited:
                break
            visited.add(c["id"])
            c = by_id[c["in_reply_to_id"]]
        return c["id"]

    # Group by root.
    groups = defaultdict(list)
    for c in comments:
        root_id = find_root(c)
        groups[root_id].append(c)

    # Sort each thread chronologically.
    threads = []
    for root_id, thread_comments in groups.items():
        thread_comments.sort(key=lambda c: c.get("created_at", ""))
        # Keep only threads where target user participated.
        user_in_thread = any(
            c.get("user", {}).get("login", "") == username
            for c in thread_comments
        )
        if user_in_thread:
            threads.append(thread_comments)

    # Sort threads by the first comment's time.
    threads.sort(key=lambda t: t[0].get("created_at", ""))
    return threads


def render_pr_markdown(pr, reviews, threads, username):
    """Render a single PR's review data as markdown."""
    owner, repo = parse_repo(pr)
    number = pr.get("number", "?")
    title = pr.get("title", "Untitled")
    url = pr.get("url", "")
    state = pr.get("state", "unknown").lower()
    updated = format_time(pr.get("updatedAt", ""))

    lines = []
    lines.append(f"# [{owner}/{repo}#{number}]({url}): {title}")
    lines.append(f"*State: {state} | Last updated: {updated}*")
    lines.append("")

    # User's reviews (verdicts).
    user_reviews = [
        r for r in reviews
        if r.get("user", {}).get("login", "") == username
        and r.get("state", "") != "PENDING"
    ]
    user_reviews.sort(key=lambda r: r.get("submitted_at", ""))

    for r in user_reviews:
        state_str = r.get("state", "COMMENTED")
        submitted = format_time(r.get("submitted_at", ""))
        lines.append(f"## Review: {state_str} ({submitted})")
        body = (r.get("body") or "").strip()
        if body:
            lines.append(body)
        lines.append("")

    # Review comment threads.
    if threads:
        lines.append("## Review Comments")
        lines.append("")

        for thread in threads:
            root = thread[0]
            path = root.get("path", "unknown")
            line = root.get("line") or root.get("original_line") or ""
            line_suffix = f":{line}" if line else ""

            lines.append(f"### `{path}{line_suffix}`")
            lines.append("")

            diff_hunk = root.get("diff_hunk", "")
            if diff_hunk:
                truncated = truncate_diff(diff_hunk)
                lines.append("```diff")
                lines.append(truncated)
                lines.append("```")
                lines.append("")

            for i, c in enumerate(thread):
                author = c.get("user", {}).get("login", "unknown")
                created = format_time(c.get("created_at", ""))
                comment_url = c.get("html_url", "")
                body = (c.get("body") or "").strip()
                if not body:
                    body = "*(empty)*"

                # Indent replies.
                is_reply = i > 0
                prefix = "> > " if is_reply else "> "
                body_lines = body.split("\n")
                quoted_body = "\n".join(f"{prefix}{l}" for l in body_lines)

                if is_reply:
                    lines.append(f"> > **{author}** ([{created}]({comment_url})):")
                else:
                    lines.append(f"> **{author}** ([{created}]({comment_url})):")
                lines.append(quoted_body)
                lines.append(">")

            lines.append("")
            lines.append("---")
            lines.append("")

    # If no reviews and no threads, note it.
    if not user_reviews and not threads:
        lines.append("*No review activity found for this user on this PR.*")
        lines.append("")

    return "\n".join(lines)


def render_index(username, index_data):
    """Render the index.md from the full index data structure.

    index_data is a dict with:
        "username": str
        "runs": [{"org": str, "period_desc": str}, ...]
        "summaries": [summary_dict, ...]   (keyed by relative_path for dedup)
    """
    runs = index_data.get("runs", [])
    summaries = index_data.get("summaries", [])

    lines = []
    lines.append(f"# Code Review History: {username}")

    # Build a combined description from all runs.
    if runs:
        run_descs = [f"{r['org']} ({r['period_desc']})" for r in runs]
        lines.append(f"*{" | ".join(run_descs)} | PRs reviewed: {len(summaries)}*")
    else:
        lines.append(f"*PRs reviewed: {len(summaries)}*")

    lines.append("")
    lines.append("| PR | Verdict | Comments | Updated |")
    lines.append("|----|---------|----------|---------|")

    for s in summaries:
        link = f"[{s['repo']}#{s['number']}]({s['relative_path']})"
        lines.append(f"| {link} | {s['verdict']} | {s['comment_count']} | {s['updated']} |")

    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Collect GitHub code review history as markdown."
    )
    parser.add_argument("username", help="GitHub username whose reviews to collect")
    parser.add_argument("org", help="GitHub org/owner to scope the search")
    parser.add_argument("-d", "--days", type=int, default=None,
                        help="Lookback period in days (default: 7 when -n not given)")
    parser.add_argument("-n", "--count", type=int, default=None,
                        help="Max number of PRs to fetch (no limit by default)")
    parser.add_argument("-o", "--output-dir", default="/tmp/gh-reviews",
                        help="Output directory (default: /tmp/gh-reviews)")
    parser.add_argument("-a", "--append", action="store_true",
                        help="Append to existing index (for multi-org collection)")
    parser.add_argument("-j", "--jobs", type=int, default=4,
                        help="Parallel workers for fetching PR data (default: 4)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress to stderr")
    args = parser.parse_args()

    # Default to 7 days when neither filter is given.
    if args.days is None and args.count is None:
        args.days = 7

    check_gh()

    since = None
    if args.days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)
    prs = search_reviewed_prs(args.username, args.org, since, args.count, args.verbose)

    if not prs:
        log("No PRs found.", True)
        sys.exit(0)

    # Process PRs in parallel.
    total = len(prs)
    counter = [0]
    counter_lock = threading.Lock()

    def process_pr(pr):
        owner, repo = parse_repo(pr)
        number = pr.get("number", 0)

        with counter_lock:
            counter[0] += 1
            idx = counter[0]
        log(f"[{idx}/{total}] Processing {owner}/{repo}#{number}...", args.verbose)

        reviews = fetch_pr_reviews(owner, repo, number, args.verbose)
        comments = fetch_pr_comments(owner, repo, number, args.verbose)
        threads = build_threads(comments, args.username)

        # Determine verdict(s) for this user.
        user_reviews = [
            r for r in reviews
            if r.get("user", {}).get("login", "") == args.username
            and r.get("state", "") != "PENDING"
        ]
        user_reviews.sort(key=lambda r: r.get("submitted_at", ""))
        if user_reviews:
            verdicts = [r.get("state", "COMMENTED") for r in user_reviews]
            significant = [v for v in verdicts if v != "COMMENTED"]
            verdict_str = significant[-1] if significant else verdicts[-1]
        else:
            verdict_str = "-"

        user_comment_count = sum(
            1 for t in threads for c in t
            if c.get("user", {}).get("login", "") == args.username
        )
        user_comment_count += sum(
            1 for r in user_reviews if (r.get("body") or "").strip()
        )

        # Write per-PR file.
        org_dir = os.path.join(args.output_dir, owner)
        os.makedirs(org_dir, exist_ok=True)
        filename = f"{repo}-PR{number}.md"
        filepath = os.path.join(org_dir, filename)

        md = render_pr_markdown(pr, reviews, threads, args.username)
        with open(filepath, "w") as f:
            f.write(md)

        return {
            "repo": repo,
            "number": number,
            "verdict": verdict_str,
            "comment_count": user_comment_count,
            "updated": format_date(pr.get("updatedAt", "")),
            "relative_path": f"{owner}/{filename}",
        }

    workers = max(1, args.jobs)
    log(f"Processing {total} PRs with {workers} workers...", args.verbose)

    # Submit all, collect results preserving original search order.
    pr_summaries = [None] * total
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(process_pr, pr): i for i, pr in enumerate(prs)}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            try:
                pr_summaries[idx] = future.result()
            except Exception as e:
                pr = prs[idx]
                owner, repo = parse_repo(pr)
                number = pr.get("number", 0)
                log(f"  Warning: failed to process {owner}/{repo}#{number}: {e}")
    pr_summaries = [s for s in pr_summaries if s is not None]

    # Build period description for this run.
    parts = []
    if args.days is not None:
        parts.append(f"last {args.days} days")
    if args.count is not None:
        parts.append(f"limit {args.count} PRs")
    period_desc = ", ".join(parts) if parts else "all time"

    # Load or create index data.
    index_json_path = os.path.join(args.output_dir, ".index.json")
    if args.append and os.path.exists(index_json_path):
        with open(index_json_path) as f:
            index_data = json.load(f)
        log(f"Appending to existing index ({len(index_data.get('summaries', []))} existing PRs)", args.verbose)
    else:
        index_data = {"username": args.username, "runs": [], "summaries": []}

    # Add this run's metadata.
    index_data["runs"].append({"org": args.org, "period_desc": period_desc})

    # Merge summaries, dedup by relative_path (newer run wins).
    existing = {s["relative_path"]: s for s in index_data.get("summaries", [])}
    for s in pr_summaries:
        existing[s["relative_path"]] = s
    index_data["summaries"] = sorted(existing.values(), key=lambda s: s["updated"], reverse=True)

    # Write .index.json and index.md.
    with open(index_json_path, "w") as f:
        json.dump(index_data, f, indent=2)

    index_md = render_index(args.username, index_data)
    index_path = os.path.join(args.output_dir, "index.md")
    with open(index_path, "w") as f:
        f.write(index_md)

    log(f"Done. Output: {args.output_dir}", True)
    log(f"  Index: {index_path}", True)
    log(f"  {len(pr_summaries)} PR files written ({len(index_data['summaries'])} total in index)", True)


if __name__ == "__main__":
    main()
