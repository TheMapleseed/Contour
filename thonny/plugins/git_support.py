# -*- coding: utf-8 -*-
"""
Git support for Contour/Thonny.

Default is pygit2 (faster; pulls libgit2 as its normal dependency). If pygit2
cannot be installed (e.g. no libgit2 on the system), install/Contour scripts
fall back to dulwich (pure-Python, https://github.com/jelmer/dulwich). At
runtime we use whichever is available: pygit2 first, then dulwich.

- Folder view: show git status (M, A, D, U, etc.) next to files when in a repo.
- AI assistant: provide branch and status summary in chat context.
"""

from __future__ import annotations

import os
from logging import getLogger
from typing import Any, Dict, List, Optional, Tuple

logger = getLogger(__name__)

_pygit2 = None
_dulwich = None


def _get_pygit2():
    global _pygit2
    if _pygit2 is None:
        try:
            import pygit2
            _pygit2 = pygit2
        except ImportError:
            _pygit2 = False  # type: ignore[assignment]
    return _pygit2 if _pygit2 is not False else None


def _get_dulwich():
    global _dulwich
    if _dulwich is None:
        try:
            import dulwich
            _dulwich = dulwich
        except ImportError:
            _dulwich = False  # type: ignore[assignment]
    return _dulwich if _dulwich is not False else None


def _find_repo_pygit2(path: str) -> Optional[str]:
    pygit2 = _get_pygit2()
    if not pygit2:
        return None
    path = os.path.abspath(path)
    if not os.path.exists(path):
        path = os.path.dirname(path)
    try:
        repo_path = pygit2.discover_repository(path)
        if repo_path:
            repo = pygit2.Repository(repo_path)
            return repo.workdir or repo.path
    except Exception:
        pass
    return None


def _find_repo_dulwich(path: str) -> Optional[str]:
    dulwich = _get_dulwich()
    if not dulwich:
        return None
    from dulwich.repo import NotGitRepository, Repo
    path = os.path.abspath(path)
    if not os.path.exists(path):
        path = os.path.dirname(path)
    current = path
    while current and current != os.path.dirname(current):
        try:
            repo = Repo(current)
            # workdir: repo.path is either work tree or .git dir
            if os.path.basename(repo.path) == ".git":
                return os.path.dirname(repo.path)
            return repo.path
        except NotGitRepository:
            pass
        current = os.path.dirname(current)
    return None


def find_repo(path: str) -> Optional[str]:
    """Return the git workdir (repo root) containing path, or None."""
    return _find_repo_pygit2(path) or _find_repo_dulwich(path)


def _get_repo_pygit2(path: str) -> Tuple[Any, str, str]:
    """Return (repo, workdir, 'pygit2') or (None, '', '')."""
    workdir = _find_repo_pygit2(path)
    if not workdir:
        return (None, "", "")
    pygit2 = _get_pygit2()
    if not pygit2:
        return (None, "", "")
    try:
        repo = pygit2.Repository(workdir)
        w = (repo.workdir or repo.path).rstrip(os.sep)
        return (repo, w, "pygit2")
    except Exception:
        return (None, "", "")


def _get_repo_dulwich(path: str) -> Tuple[Any, str, str]:
    """Return (repo, workdir, 'dulwich') or (None, '', '')."""
    workdir = _find_repo_dulwich(path)
    if not workdir:
        return (None, "", "")
    dulwich = _get_dulwich()
    if not dulwich:
        return (None, "", "")
    try:
        from dulwich.repo import Repo
        repo = Repo(workdir)
        w = repo.path
        if os.path.basename(w) == ".git":
            w = os.path.dirname(w)
        w = w.rstrip(os.sep)
        return (repo, w, "dulwich")
    except Exception:
        return (None, "", "")


def get_repo_for_path(path: str) -> Optional[Any]:
    """Return repo object (pygit2 or dulwich) for the repo containing path, or None."""
    repo, _, _ = _get_repo_pygit2(path)
    if repo:
        return repo
    repo, _, _ = _get_repo_dulwich(path)
    return repo


def _status_letter_pygit2(flags: int) -> str:
    if flags == 0:
        return ""
    pygit2 = _get_pygit2()
    if not pygit2:
        return "?"
    if flags & (pygit2.GIT_STATUS_WT_NEW | pygit2.GIT_STATUS_INDEX_NEW):
        return "U"
    if flags & (pygit2.GIT_STATUS_WT_MODIFIED | pygit2.GIT_STATUS_INDEX_MODIFIED):
        return "M"
    if flags & (pygit2.GIT_STATUS_WT_DELETED | pygit2.GIT_STATUS_INDEX_DELETED):
        return "D"
    if flags & (pygit2.GIT_STATUS_WT_RENAMED | pygit2.GIT_STATUS_INDEX_RENAMED):
        return "R"
    if flags & (pygit2.GIT_STATUS_WT_TYPECHANGE | pygit2.GIT_STATUS_INDEX_TYPECHANGE):
        return "T"
    if flags & getattr(pygit2, "GIT_STATUS_IGNORED", 1 << 14):
        return ""
    if flags & getattr(pygit2, "GIT_STATUS_CONFLICTED", 1 << 15):
        return "C"
    return "?"


def _decode_path(p: Any) -> str:
    return p.decode("utf-8", errors="replace") if isinstance(p, bytes) else str(p)


def get_status_for_dir(dir_path: str) -> Dict[str, str]:
    """
    Return a dict mapping child name (file or dir) to status letter
    (M, A, D, U, R, T, C, or "") for items in dir_path.
    """
    repo, workdir, backend = _get_repo_pygit2(dir_path)
    if not repo:
        repo, workdir, backend = _get_repo_dulwich(dir_path)
    if not repo or not workdir:
        return {}

    result: Dict[str, str] = {}
    dir_path_n = os.path.normpath(dir_path).rstrip(os.sep)
    prefix = dir_path_n + os.sep

    if backend == "pygit2":
        try:
            status = repo.status()
        except Exception as e:
            logger.debug("git status failed for %s: %s", dir_path, e)
            return {}
        for filepath, flags in status.items():
            if flags == 0:
                continue
            fp = _decode_path(filepath)
            full = os.path.normpath(os.path.join(workdir, fp))
            if not full.startswith(prefix):
                continue
            rel = full[len(prefix) :].lstrip(os.sep)
            name = rel.split(os.sep)[0] if os.sep in rel else rel
            if name and name not in result:
                result[name] = _status_letter_pygit2(flags)
    else:
        # dulwich
        try:
            from dulwich import porcelain
            st = porcelain.status(repo)
        except Exception as e:
            logger.debug("dulwich status failed for %s: %s", dir_path, e)
            return {}
        # GitStatus: staged={'add': [], 'delete': [], 'modify': []}, unstaged=[], untracked=[]
        def add_paths(paths: List[Any], letter: str) -> None:
            for p in paths:
                fp = _decode_path(p)
                full = os.path.normpath(os.path.join(workdir, fp))
                if not full.startswith(prefix):
                    continue
                rel = full[len(prefix) :].lstrip(os.sep)
                name = rel.split(os.sep)[0] if os.sep in rel else rel
                if name and (name not in result or letter == "M"):
                    result[name] = letter
        for fp in st.staged.get("add", []):
            add_paths([fp], "A")
        for fp in st.staged.get("delete", []):
            add_paths([fp], "D")
        for fp in st.staged.get("modify", []):
            add_paths([fp], "M")
        for fp in st.unstaged:
            add_paths([fp], "M")
        for fp in st.untracked:
            add_paths([fp], "U")
    return result


def get_branch_name(repo_path: Optional[str] = None) -> Optional[str]:
    """Return current branch name for repo at repo_path or None."""
    if not repo_path:
        return None
    repo, _, backend = _get_repo_pygit2(repo_path)
    if repo:
        try:
            ref = repo.head
            if ref and ref.shorthand:
                return ref.shorthand
        except Exception:
            pass
        return None
    repo, _, backend = _get_repo_dulwich(repo_path)
    if not repo:
        return None
    try:
        ref = repo.refs.read_ref(b"HEAD")
        if not ref:
            return "detached"
        ref = _decode_path(ref)
        if ref.startswith("refs/heads/"):
            return ref[len("refs/heads/"):]
        return ref
    except Exception:
        return None


def get_git_context_summary(cwd: str) -> Optional[str]:
    """
    Return a short summary string for the AI context: branch and status lines.
    None if not a git repo or neither pygit2 nor dulwich available.
    """
    repo, workdir, backend = _get_repo_pygit2(cwd)
    if not repo:
        repo, workdir, backend = _get_repo_dulwich(cwd)
    if not repo or not workdir:
        return None

    try:
        if backend == "pygit2":
            branch = repo.head.shorthand if repo.head else "detached"
            status = repo.status()
            lines = [f"Git repo: {workdir}", f"Branch: {branch}"]
            if status:
                lines.append("Status:")
                for path, flags in sorted(status.items()):
                    if flags != 0:
                        letter = _status_letter_pygit2(flags)
                        if letter:
                            lines.append(f"  {letter} {_decode_path(path)}")
        else:
            from dulwich import porcelain
            branch = get_branch_name(cwd) or "detached"
            st = porcelain.status(repo)
            lines = [f"Git repo: {workdir}", f"Branch: {branch}"]
            status_lines: List[str] = []
            for fp in st.staged.get("add", []):
                status_lines.append(f"  A {_decode_path(fp)}")
            for fp in st.staged.get("delete", []):
                status_lines.append(f"  D {_decode_path(fp)}")
            for fp in st.staged.get("modify", []):
                status_lines.append(f"  M {_decode_path(fp)}")
            for fp in st.unstaged:
                status_lines.append(f"  M {_decode_path(fp)}")
            for fp in st.untracked:
                status_lines.append(f"  U {_decode_path(fp)}")
            if status_lines:
                lines.append("Status:")
                lines.extend(sorted(status_lines))
        return "\n".join(lines)
    except Exception:
        return None


def enrich_dir_children_with_git(
    dir_path: str,
    children_data: Optional[Dict[str, Dict[str, Any]]],
) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Mutate children_data in place: add git status to each child's label.
    dir_path is the parent directory path; children_data is the result of
    get_single_dir_child_data for that path.
    """
    if not children_data or not isinstance(children_data, dict):
        return children_data
    status_map = get_status_for_dir(dir_path)
    for name, data in children_data.items():
        if not isinstance(data, dict):
            continue
        letter = status_map.get(name, "")
        label = data.get("label", name)
        if letter:
            data["label"] = f"{label} ({letter})"
        data["git_status"] = letter
    return children_data
