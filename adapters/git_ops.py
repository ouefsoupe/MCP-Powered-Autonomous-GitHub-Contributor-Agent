from typing import Optional, Tuple
from git import Repo
import os
import difflib
import re

def _inject_token_into_url(url: str, token: Optional[str]) -> str:
    """Inject PAT token into HTTPS GitHub URL for authentication."""
    if not token:
        return url

    # Remove any existing credentials from the URL first
    # Pattern: https://anything@github.com/... -> https://github.com/...
    url = re.sub(r'https://[^@]+@github\.com/', 'https://github.com/', url)

    # Pattern to match https://github.com/... URLs
    pattern = r'https://github\.com/'
    if re.match(pattern, url):
        # Inject token as https://token@github.com/...
        return re.sub(pattern, f'https://{token}@github.com/', url)
    return url

def clone_repo(url: str, dest: str, branch: Optional[str] = None, token: Optional[str] = None) -> str:
    """Clone a repository, optionally injecting a PAT token for authentication."""
    auth_url = _inject_token_into_url(url, token)
    repo = Repo.clone_from(auth_url, dest)
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

def commit_and_push(workdir: str, branch: str, message: str, *, push: bool = True, token: Optional[str] = None):
    """Commit changes and optionally push to remote, using PAT token for authentication."""
    repo = Repo(workdir)
    # ensure identity so local commits don't fail
    cw = repo.config_writer()
    try:
        _ = repo.config_reader().get_value("user", "name")
        _ = repo.config_reader().get_value("user", "email")
    except Exception:
        cw.set_value("user", "name", "mcp-bot")
        cw.set_value("user", "email", "mcp@example.com")
    cw.release()

    # Update remote URL with PAT token if provided
    if token and push:
        try:
            # Get the current remote URL
            remote_url = repo.remotes.origin.url
            print(f"[DEBUG] Original remote URL (sanitized): {remote_url.replace(token, 'TOKEN') if token in remote_url else remote_url}")

            # Inject token into the URL
            auth_url = _inject_token_into_url(remote_url, token)

            # Update the remote URL
            repo.remotes.origin.set_url(auth_url)
            print(f"[DEBUG] Updated remote URL with token: {auth_url.replace(token, 'TOKEN')}")
        except Exception as e:
            # If updating remote fails, log the error
            print(f"[ERROR] Failed to update remote URL: {e}")
            raise

    repo.git.add(all=True)
    if not repo.is_dirty():
        if push:
            repo.git.push("--set-upstream", "origin", branch)
        return repo.head.commit.hexsha, f"origin/{branch}"

    repo.index.commit(message)
    if push:
        repo.git.push("--set-upstream", "origin", branch)
    return repo.head.commit.hexsha, f"origin/{branch}"


