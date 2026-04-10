---
description: Go through GitHub PR review comments one by one and respond/fix/resolve them
argument-hint: <PR number, URL, or owner/repo#number> [--user <username>]
---

Go through the review comments on the GitHub PR `$ARGUMENTS` one by one.

If `$ARGUMENTS` contains `--user <username>`, pass it through to `fetch-pr-comments.sh` to filter comments to that author only.

Helper scripts are in `.claude/commands/respond-gh-comments-scripts/`. All scripts accept an optional trailing `hostname` argument for enterprise GitHub instances.

## Preflight checks

Before doing anything else, verify the environment is ready. **Skip these checks if they have already passed earlier in this session** (e.g. from a previous invocation of this command):

1. **Check `gh` is installed:**
   ```
   gh --version
   ```
   If this fails, tell the user: "`gh` CLI is not installed. Install it via `brew install gh` (macOS) or see https://cli.github.com."

2. **Parse the PR argument** to extract owner, repo, number, and hostname:
   ```
   read OWNER REPO NUMBER HOSTNAME < <(.claude/commands/respond-gh-comments-scripts/parse-pr-arg.sh "$ARGUMENTS")
   ```

3. **Check authentication** against the correct host:
   ```
   gh auth status --hostname <HOSTNAME>
   ```
   If this fails or shows "not logged in", tell the user to run `gh auth login --hostname <HOSTNAME>` and stop.

## Steps

1. **Load the PR diff into context** so you understand the full set of changes under review. If the changes were already made during the current session, skip this step — you already have context. Otherwise:
   ```
   .claude/commands/respond-gh-comments-scripts/fetch-pr-diff.sh <OWNER> <REPO> <NUMBER> <HOSTNAME>
   ```
   Read through the diff to understand what files were changed and why before proceeding.

2. **Fetch all review comments** from the PR:
   ```
   .claude/commands/respond-gh-comments-scripts/fetch-pr-comments.sh <OWNER> <REPO> <NUMBER> <HOSTNAME> [--user <FILTER_USER>]
   ```
   Each comment block includes `ID` (comment database ID), `ThreadID` (GraphQL node ID needed for resolving), `Resolved`, `File`, `Line`, `Author`, `Diff hunk`, `Body`, and `In reply to`. If `FILTER_USER` is set, pass it via `--user` and the script will discard non-matching authors.

3. **For each comment, one at a time:**
   - Display the comment: file, line number, and full body.
   - Read the commented file and show the affected lines (use the `Diff hunk:`) so the user can understand the code without switching to an editor.
   - Decide together with the user whether to fix, skip, or note as a false alarm.
   - If fixing: read the relevant file, make the edit, confirm it looks correct.
   - If skipping: note the reason (false alarm, won't fix, etc.).
   - **Track** the decision for each comment (original comment ID, thread node ID, what was done and why) — but do NOT post replies or resolve threads yet.

4. **Optionally run tests** before committing:
   - Ask the user if they want to run tests before committing the changes.
   - If yes: ask which test suite to run (e.g. `check-odie-compiler`, `check-odie-ctest`, `check-odie-xctest`, or a specific LIT test). Run it and fix any failures before proceeding.
   - If no: continue to step 5.

5. **Commit and push** all changes before touching any PR threads:
   - Ask the user if they are ready to commit and push. Do not proceed until they confirm.
   - Only stage files that were actually modified while handling review comments. Do **not** use `git add -A` or `git add .` — add each changed file by name. If there were pre-existing unstaged or untracked changes before this workflow started, leave them alone.
   - Commit with a clear message summarizing which review comments were addressed.
   - Push the commit to the PR branch.
   - Do not proceed to step 6 until the push succeeds.

6. **After the commit is pushed**, go through the tracked decisions and for each addressed thread:

   First, reply to the thread:
   ```
   .claude/commands/respond-gh-comments-scripts/reply-to-comment.sh <OWNER> <REPO> <NUMBER> <COMMENT_ID> "<reply body>" <HOSTNAME>
   ```

   Then resolve the thread using the `ThreadID` already returned by `fetch-pr-comments.sh` (no separate fetch needed):
   ```
   .claude/commands/respond-gh-comments-scripts/resolve-thread.sh <THREAD_NODE_ID> <HOSTNAME>
   ```
   Only resolve threads that were actually addressed (fixed or confirmed as false alarms).
   Leave open any threads where action is deferred or unclear.

## Notes

- The `parse-pr-arg.sh` script auto-detects the hostname from the git remote when only a plain number is given.
- PROCESS COMMENTS STRICTLY ONE AT A TIME — DO NOT BATCH DECISIONS.
- After all comments are handled, report a summary: how many fixed, skipped, and left open.
