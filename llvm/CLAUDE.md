# LLVM Project Organization

LLVM is a compiler framework, implemented in C++, Python, and C. The git repo
uses worktrees placed in `~/llvm/`. The primary cmake build dir is under `build/`.

Enabled projects: `mlir;clang;clang-tools-extra;flang;lld;lldb`.
Targets: `X86;AMDGPU`. Build type: `RelWithDebInfo`.

To rebuild: `ninja -C build`.
To run tests for a specific project: `ninja -C build check-mlir` (or `check-clang`, `check-llvm`, etc.).

## Beads Workflow (MANDATORY)

<!-- br-agent-instructions-v1 -->

This project uses [beads_rust](https://github.com/Dicklesworthstone/beads_rust) (`br`/`bd`) for local issue tracking. Issues are stored in `.beads/` and are local only.

CRITICAL: NEVER MENTION BEADS IN CODE. Beads are for your local work tracking only and do not persist. Always write proper TODOs or use github issues for long term/persistent tracking. 95% of all work you do should be tracked in beads. Think of it like a memory.

### Commands

```bash
br ready                  # Unblocked, actionable work
br list --status=open     # All open issues
br list --status=in_progress  # What you're supposed to be working on
br show <id>              # Full issue details
br search "keyword"       # Full-text search

br create --title="..." --description="..." --type=task --priority=2
br update <id> --status=in_progress
br close <id> --reason="Completed"
br close <id1> <id2>      # Close multiple at once
br dep add <issue> <depends-on>
br sync --flush-only       # Flush local state
```

### Mandatory trigger points

Bead updates are NOT optional. They are part of the task. You MUST execute
these at the specified moments — not "when convenient", not "if you remember":

1. **Session start**: Run `br ready`. State which bead(s) you will work on.
2. **Before writing code for a task**: `br update <id> --status=in_progress`.
   Do this BEFORE opening the file, not after.
3. **When you discover new work mid-task**: `br create` immediately, before
   continuing with your current work.
4. **After a successful test run or commit**: `br close <id> --reason="<what you did>"`.
5. **Before telling the user something is "done"**: Run `br list --status=in_progress`
   and close or update every stale bead. A task is NOT complete until its bead
   is closed.
6. **Session end**: `br sync --flush-only`.

A hook injects current bead state into every prompt. READ IT. If you see
in_progress beads that you are not actively working on, close or update them
before doing anything else.

### Priority and types

- **Priority**: P0=critical, P1=high, P2=medium, P3=low, P4=backlog (use numbers 0-4)
- **Types**: task, bug, feature, epic, chore, docs, question
- **Dependencies**: `br ready` shows only unblocked work

<!-- end-br-agent-instructions -->
