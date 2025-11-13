import os
import uuid
from typing import List, Dict, Any, Optional

import requests


MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")


class MCPClient:
    """
    Thin HTTP client for talking to the MCP server endpoints.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or MCP_SERVER_URL

    def _post(self, path: str, json: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}{path}"
        resp = requests.post(url, json=json, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def health(self) -> Dict[str, Any]:
        url = f"{self.base_url.rstrip('/')}/health"
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # ---------- REPO OPS ----------

    def clone_repo(self, url: str, branch: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"url": url}
        if branch:
            payload["branch"] = branch
        return self._post("/repo/clone", payload)

    def find_files(self, workdir: str, glob_pattern: str) -> List[str]:
        data = self._post("/repo/find_files", {
            "workdir": workdir,
            "glob": glob_pattern
        })
        return data.get("files", [])

    def read_file(self, workdir: str, path: str) -> str:
        data = self._post("/repo/read_file", {
            "workdir": workdir,
            "path": path
        })
        return data["text"]

    def write_file(self, workdir: str, path: str, new_text: str) -> Dict[str, Any]:
        return self._post("/repo/write_file", {
            "workdir": workdir,
            "path": path,
            "new_text": new_text
        })

    # ---------- GIT OPS ----------

    def create_branch(self, workdir: str, base: str, new_branch: str) -> Dict[str, Any]:
        return self._post("/git/create_branch", {
            "workdir": workdir,
            "base": base,
            "new_branch": new_branch
        })

    def commit_and_push(self, workdir: str, branch: str, message: str) -> Dict[str, Any]:
        return self._post("/git/commit_push", {
            "workdir": workdir,
            "branch": branch,
            "message": message
        })

    # ---------- GITHUB OPS ----------

    def create_pr(
        self,
        repo_url: str,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str
    ) -> Dict[str, Any]:
        return self._post("/github/create_pr", {
            "repo_url": repo_url,
            "title": title,
            "body": body,
            "head_branch": head_branch,
            "base_branch": base_branch
        })
