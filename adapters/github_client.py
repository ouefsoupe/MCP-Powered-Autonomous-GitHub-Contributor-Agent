import base64
import re
from typing import Any, Dict, Tuple
import requests

class GitHubClient:
    def __init__(self, token: str):
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })

    @staticmethod
    def _parse_repo(repo_url: str) -> Tuple[str, str]:
        # supports https://github.com/owner/name(.git)
        m = re.match(r"https?://github\.com/([^/]+)/([^/.]+)(?:\.git)?$", repo_url)
        if not m:
            raise ValueError(f"Unsupported repo URL: {repo_url}")
        return m.group(1), m.group(2)

    def create_pr(self, *, repo_url: str, title: str, body: str, head: str, base: str) -> Dict[str, Any]:
        owner, name = self._parse_repo(repo_url)
        url = f"https://api.github.com/repos/{owner}/{name}/pulls"
        r = self.session.post(url, json={"title": title, "body": body, "head": head, "base": base}, timeout=60)
        r.raise_for_status()
        return r.json()

    def get_issue(self, *, repo_url: str, issue_number: int) -> Dict[str, Any]:
        owner, name = self._parse_repo(repo_url)
        url = f"https://api.github.com/repos/{owner}/{name}/issues/{issue_number}"
        r = self.session.get(url, timeout=60)
        r.raise_for_status()
        return r.json()
