from typing import Optional, Tuple
from git import Repo
import os
import difflib

def clone_repo(url: str, dest: str, branch: Optional[str] = None) -> str:
    repo = Repo.clone_from(url, dest)
    if branch:
        repo.git.checkout(branch)
    return branch or repo.active_branch.name

def create_branch(workdir: str, base: str, new_branch: str) -> None:
    repo = Repo(workdir)
    repo.git.checkout(base)
    repo.git.pull("--ff-only")
    repo.git.checkout("-b", new_branch)

def _file_path(workdir: str, path: str) -> str:
    return os.path.join(workdir, path)

def write_file_and_diff(workdir: str, path: str, new_text: str) -> Tuple[str, int]:
    fp = _file_path(workdir, path)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    old = ""
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            old = f.read()
    with open(fp, "w", encoding="utf-8") as f:
        f.write(new_text)
    diff = "".join(difflib.unified_diff(old.splitlines(keepends=True),
                                        new_text.splitlines(keepends=True),
                                        fromfile=f"a/{path}", tofile=f"b/{path}"))
    return diff, abs(len(new_text) - len(old))

def commit_and_push(workdir: str, branch: str, message: str, *, push: bool = True):
    repo = Repo(workdir)
    # ensure identity so local commits don’t fail
    cw = repo.config_writer()
    try:
        _ = repo.config_reader().get_value("user", "name")
        _ = repo.config_reader().get_value("user", "email")
    except Exception:
        cw.set_value("user", "name", "mcp-bot")
        cw.set_value("user", "email", "mcp@example.com")
    cw.release()

    repo.git.add(all=True)
    if not repo.is_dirty():
        if push:
            repo.git.push("--set-upstream", "origin", branch)
        return repo.head.commit.hexsha, f"origin/{branch}"

    repo.index.commit(message)
    if push:
        repo.git.push("--set-upstream", "origin", branch)
    return repo.head.commit.hexsha, f"origin/{branch}"


