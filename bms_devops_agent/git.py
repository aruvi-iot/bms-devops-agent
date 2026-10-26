from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
        check=False, timeout=30,
    )
    if result.returncode:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def resolve_revision(repo_root: str, requested: str) -> str:
    repo = Path(repo_root).resolve(strict=True)
    if not (repo / ".git").exists():
        raise GitError(f"Not a Git repository: {repo}")
    resolved = _git(repo, "rev-parse", "--verify", f"{requested}^{{commit}}")
    if not resolved.startswith(requested) and not requested.startswith(resolved):
        raise GitError(f"Requested revision {requested!r} did not resolve exactly")
    return resolved


def current_head(repo_root: str) -> str:
    repo = Path(repo_root).resolve(strict=True)
    return _git(repo, "rev-parse", "--verify", "HEAD^{commit}")


def working_tree_status(repo_root: str) -> str:
    repo = Path(repo_root).resolve(strict=True)
    return _git(repo, "status", "--porcelain=v1", "--untracked-files=all")
