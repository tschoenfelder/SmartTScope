#!/usr/bin/env python3
"""Delivery audit for SmartTScope development workflow.

Verifies that implementation milestones are backed by source, tests and
documentation that have been committed and pushed to the remote repository.
Appends a JSONL record to the delivery log on each run.

Acceptance: REQ-GIT-001, REQ-GIT-002, REQ-GIT-003; INC-012; TEST-007

Exit codes:
  0  all checks pass
  1  one or more checks failed
  2  git command error or not inside a repository

Usage:
    python scripts/delivery_audit.py             # audit only (read-only)
    python scripts/delivery_audit.py --push      # audit, then push if clean
    python scripts/delivery_audit.py --check     # dry-run: show plan without executing
    python scripts/delivery_audit.py --log PATH  # override JSONL log file path
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# File categorisation helpers
# ---------------------------------------------------------------------------

_SOURCE_DIRS = ("smart_telescope/", "scripts/")
_TEST_DIRS = ("tests/",)
_DOC_EXTENSIONS = {".md", ".rst", ".txt"}
_DOC_DIRS = ("docs/", "wiki/", "resources/")


def _categorise(path: str) -> str:
    for d in _TEST_DIRS:
        if path.startswith(d):
            return "test"
    for d in _SOURCE_DIRS:
        if path.startswith(d):
            return "source"
    ext = Path(path).suffix.lower()
    if ext in _DOC_EXTENSIONS:
        return "doc"
    for d in _DOC_DIRS:
        if path.startswith(d):
            return "doc"
    return "other"


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], check=check)


def _git_line(*args: str) -> str:
    return _git(*args).stdout.strip()


# ---------------------------------------------------------------------------
# Audit data
# ---------------------------------------------------------------------------


@dataclass
class AuditResult:
    branch: str = ""
    commit_hash: str = ""
    commit_message: str = ""
    remote_url: str = ""

    uncommitted_files: list[str] = field(default_factory=list)
    unpushed_commits: list[str] = field(default_factory=list)

    last_commit_source_files: list[str] = field(default_factory=list)
    last_commit_test_files: list[str] = field(default_factory=list)
    last_commit_doc_files: list[str] = field(default_factory=list)
    last_commit_other_files: list[str] = field(default_factory=list)

    push_result: str = "not_attempted"  # not_attempted | ok | failed | dry_run

    @property
    def is_docs_only_commit(self) -> bool:
        has_impl = bool(self.last_commit_source_files or self.last_commit_test_files)
        has_docs = bool(self.last_commit_doc_files or self.last_commit_other_files)
        return has_docs and not has_impl

    @property
    def has_uncommitted_changes(self) -> bool:
        return bool(self.uncommitted_files)

    @property
    def has_unpushed_commits(self) -> bool:
        return bool(self.unpushed_commits)

    @property
    def passed(self) -> bool:
        if self.is_docs_only_commit:
            return False
        if self.has_uncommitted_changes:
            return False
        if self.has_unpushed_commits:
            return False
        if self.push_result == "failed":
            return False
        return True


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def _collect(*, push: bool, dry_run: bool) -> AuditResult:
    r = AuditResult()

    # branch
    r.branch = _git_line("branch", "--show-current") or "HEAD_DETACHED"

    # last commit hash + message
    log_out = _git_line("log", "-1", "--format=%H%n%s")
    lines = log_out.splitlines()
    r.commit_hash = lines[0] if lines else ""
    r.commit_message = lines[1] if len(lines) > 1 else ""

    # remote URL
    remote_out = _git("remote", "-v", check=False).stdout
    for line in remote_out.splitlines():
        if "(fetch)" in line:
            parts = line.split()
            if len(parts) >= 2:
                r.remote_url = parts[1]
            break

    # uncommitted changes -- git status --short
    status_out = _git("status", "--short").stdout.strip()
    if status_out:
        r.uncommitted_files = [ln for ln in status_out.splitlines() if ln.strip()]

    # unpushed commits -- git log origin/branch..HEAD
    try:
        ahead_out = _git_line("log", f"origin/{r.branch}..HEAD", "--oneline")
        if ahead_out:
            r.unpushed_commits = [ln for ln in ahead_out.splitlines() if ln.strip()]
    except subprocess.CalledProcessError:
        # no upstream configured or first push -- treat as unpushed
        total = _git_line("log", "--oneline")
        if total:
            r.unpushed_commits = ["(no upstream -- all commits unpushed)"]

    # last commit file categories -- diff-tree lists files changed in commit
    diff_out = _git_line("diff-tree", "--no-commit-id", "-r", "--name-only", r.commit_hash)
    for path in diff_out.splitlines():
        path = path.strip()
        if not path:
            continue
        cat = _categorise(path)
        if cat == "source":
            r.last_commit_source_files.append(path)
        elif cat == "test":
            r.last_commit_test_files.append(path)
        elif cat == "doc":
            r.last_commit_doc_files.append(path)
        else:
            r.last_commit_other_files.append(path)

    if push and not dry_run:
        proc = _git("push", "origin", r.branch, check=False)
        if proc.returncode == 0:
            r.push_result = "ok"
        else:
            r.push_result = "failed"
            print(f"\n[push stderr]\n{proc.stderr.strip()}")
    elif push and dry_run:
        r.push_result = "dry_run"
    else:
        r.push_result = "not_attempted"

    return r


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_W = 60


def _section(title: str) -> None:
    print(f"\n{'-' * _W}")
    print(f"  {title}")
    print(f"{'-' * _W}")


def _ok(msg: str) -> None:
    print(f"  [PASS]  {msg}")


def _fail(msg: str) -> None:
    print(f"  [FAIL]  {msg}")


def _info(msg: str) -> None:
    print(f"          {msg}")


def _names(paths: list[str], limit: int = 3) -> str:
    if not paths:
        return ""
    shown = [Path(p).name for p in paths[:limit]]
    rest = len(paths) - limit
    result = ", ".join(shown)
    if rest > 0:
        result += f", +{rest} more"
    return f"({result})"


def _print_report(r: AuditResult) -> None:
    print(f"\n{'=' * _W}")
    print("  SmartTScope Delivery Audit")
    print("=" * _W)

    _section("Repository state")
    print(f"  Branch  : {r.branch}")
    print(f"  Commit  : {r.commit_hash[:12]}  {r.commit_message}")
    print(f"  Remote  : {r.remote_url or '(none configured)'}")

    _section("Last commit - file categories")
    total = (
        len(r.last_commit_source_files)
        + len(r.last_commit_test_files)
        + len(r.last_commit_doc_files)
        + len(r.last_commit_other_files)
    )
    print(f"  Source  : {len(r.last_commit_source_files):3d}  {_names(r.last_commit_source_files)}")
    print(f"  Tests   : {len(r.last_commit_test_files):3d}  {_names(r.last_commit_test_files)}")
    print(f"  Docs    : {len(r.last_commit_doc_files):3d}  {_names(r.last_commit_doc_files)}")
    print(f"  Other   : {len(r.last_commit_other_files):3d}  {_names(r.last_commit_other_files)}")
    print(f"  Total   : {total:3d}")

    _section("Audit checks")

    # 1. docs-only check (REQ-GIT-001)
    if r.is_docs_only_commit:
        _fail("Documentation-only commit -- not implementation-complete (REQ-GIT-001)")
        _info("Source or test files must accompany any implementation claim.")
    else:
        _ok("Commit contains source or test files -- implementation-complete flag valid")

    # 2. uncommitted changes
    if r.has_uncommitted_changes:
        _fail(f"Uncommitted changes ({len(r.uncommitted_files)} file(s)) -- working tree is dirty")
        for f in r.uncommitted_files[:10]:
            _info(f)
        if len(r.uncommitted_files) > 10:
            _info(f"... and {len(r.uncommitted_files) - 10} more")
    else:
        _ok("Working tree is clean -- no uncommitted changes")

    # 3. unpushed commits
    if r.has_unpushed_commits:
        _fail(f"Unpushed commits ({len(r.unpushed_commits)}) -- source not visible on remote")
        for c in r.unpushed_commits[:5]:
            _info(c)
        if len(r.unpushed_commits) > 5:
            _info(f"... and {len(r.unpushed_commits) - 5} more")
    else:
        _ok("No unpushed commits -- remote is up to date")

    # 4. push result
    if r.push_result == "ok":
        _ok("Push succeeded -- source visible on GitHub")
    elif r.push_result == "failed":
        _fail("Push failed -- source NOT visible on GitHub (see stderr above)")
    elif r.push_result == "dry_run":
        _info("(dry-run) push would be attempted")
    else:
        _info("Push not attempted (run with --push to push)")

    _section("Result")
    if r.passed:
        print("  DELIVERY AUDIT PASSED")
    else:
        print("  DELIVERY AUDIT FAILED -- see [FAIL] items above")

    _section("Pre-push checklist")
    print("  Before pushing, verify:")
    print("  [ ] Source files are committed alongside tests and docs")
    print("  [ ] All tests pass: python -m pytest tests/unit/ -x -q")
    print("  [ ] New config options have stubs in templates/config.toml")
    print("  [ ] wiki/log.md updated with a summary of changes")
    print("  [ ] wiki/index.md updated if new pages were added")
    print("  [ ] No secrets, credentials, or hardware-specific paths committed")


# ---------------------------------------------------------------------------
# Delivery log (JSONL)
# ---------------------------------------------------------------------------

_DEFAULT_LOG = Path.home() / ".SmartTScope" / "delivery_log.jsonl"


def _write_log(r: AuditResult, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "branch": r.branch,
        "commit_hash": r.commit_hash,
        "commit_message": r.commit_message,
        "files_changed": (
            len(r.last_commit_source_files)
            + len(r.last_commit_test_files)
            + len(r.last_commit_doc_files)
            + len(r.last_commit_other_files)
        ),
        "source_files_changed": len(r.last_commit_source_files),
        "test_files_changed": len(r.last_commit_test_files),
        "docs_changed": len(r.last_commit_doc_files),
        "push_result": r.push_result,
        "remote_url": r.remote_url,
        "audit_passed": r.passed,
        "docs_only_commit": r.is_docs_only_commit,
    }
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    print(f"\n  Log appended: {log_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--push", action="store_true", help="push to origin after audit")
    parser.add_argument("--check", action="store_true", help="dry-run: report only, no push")
    parser.add_argument(
        "--log",
        metavar="PATH",
        default=str(_DEFAULT_LOG),
        help=f"JSONL delivery log path (default: {_DEFAULT_LOG})",
    )
    args = parser.parse_args()

    try:
        result = _collect(push=args.push, dry_run=args.check)
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] git command failed: {exc.cmd}\n{exc.stderr}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print("[ERROR] git not found on PATH", file=sys.stderr)
        return 2

    _print_report(result)

    if not args.check:
        _write_log(result, Path(args.log))

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
