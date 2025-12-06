import os
import uuid
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from .mcp_client import MCPClient


# Task model 

@dataclass
class IssueTask:
    repo_url: str
    base_branch: str
    issue_number: int
    title: str
    body: str
    labels: List[str]


# LLM integration stubs

def call_llm_for_plan(
    task: IssueTask,
    repo_overview: str,
    file_snippets: Dict[str, str],
) -> Dict[str, Any]:
    """
    TODO: Wire this up to your LLM provider.

    It should return a JSON-like plan with fields like:
    {
      "branch_name": "issue-12-add-validation",
      "commit_message": "Add input validation to foo()",
      "pr_title": "Add input validation to foo()",
      "pr_body": "This PR adds ...",
      "edits": [
        {
          "path": "src/foo.py",
          "new_content": "<entire new file contents>",
          "rationale": "We need to check X before doing Y..."
        },
        ...
      ]
    }

    For now, this is just a stub so you can focus on the orchestrator.
    """
    raise NotImplementedError("Implement LLM call and planning here.")


# Agent orchestrator

class AgentOrchestrator:
    """
    High-level agent that uses MCPClient + LLM plan to go from Issue -> PR.
    """

    def __init__(self, mcp: Optional[MCPClient] = None):
        self.mcp = mcp or MCPClient()

    def run_issue_task(self, task: IssueTask) -> Dict[str, Any]:
        """
        Main entry point: given an issue, produce a PR (or decline).

        Returns a dict summarizing the result, e.g.
        {
          "status": "pr_created",
          "branch": "...",
          "commit_sha": "...",
          "pr_number": 42,
          "pr_url": "https://github.com/..."
        }
        """
        # 1. Clone repo
        clone_resp = self.mcp.clone_repo(task.repo_url, branch=task.base_branch)
        workdir = clone_resp["workdir"]
        base_branch = clone_resp["branch"]

        # 2. (Optional) Build a simple repo overview to give the LLM
        files = self.mcp.find_files(workdir, "**/*.py")  # adjust globs as needed
        # To avoid tons of tokens, maybe only sample / top-level files:
        files_to_sample = files[:10]

        file_snippets: Dict[str, str] = {}
        for path in files_to_sample:
            try:
                text = self.mcp.read_file(workdir, path)
                # Truncate long files before sending to LLM
                file_snippets[path] = text[:4000]
            except Exception:
                # Non-fatal; skip unreadable files
                continue

        repo_overview = (
            f"Repo URL: {task.repo_url}\n"
            f"Base branch: {base_branch}\n"
            f"Sample files:\n" +
            "\n".join(f"- {p}" for p in files_to_sample)
        )

        # 3. Ask LLM for a plan: which branch, which edits, commit/PR messages
        plan = call_llm_for_plan(task, repo_overview, file_snippets)

        branch_name = plan.get("branch_name") or self._default_branch_name(task)
        commit_message = plan.get("commit_message") or f"Automated fix for issue #{task.issue_number}"
        pr_title = plan.get("pr_title") or f"Automated PR for issue #{task.issue_number}"
        pr_body = plan.get("pr_body") or f"This PR attempts to address issue #{task.issue_number}."

        edits: List[Dict[str, Any]] = plan.get("edits", [])
        if not edits:
            return {
                "status": "no_edits_planned",
                "reason": "LLM returned no edits"
            }

        # 4. Create a new branch
        self.mcp.create_branch(workdir, base_branch, branch_name)

        # 5. Apply each edit via /repo/write_file
        for edit in edits:
            path = edit["path"]
            new_content = edit["new_content"]
            self.mcp.write_file(workdir, path, new_content)

        # 6. Commit + push
        commit_resp = self.mcp.commit_and_push(workdir, branch_name, commit_message)
        commit_sha = commit_resp.get("commit_sha")
        remote_ref = commit_resp.get("remote_ref")

        # 7. Create PR
        pr_resp = self.mcp.create_pr(
            repo_url=task.repo_url,
            title=pr_title,
            body=pr_body,
            head_branch=branch_name,
            base_branch=task.base_branch,
        )

        return {
            "status": "pr_created",
            "branch": branch_name,
            "commit_sha": commit_sha,
            "remote_ref": remote_ref,
            "pr_number": pr_resp.get("pr_number"),
            "pr_url": pr_resp.get("html_url"),
        }

    @staticmethod
    def _default_branch_name(task: IssueTask) -> str:
        slug_title = (
            task.title.lower()
            .replace(" ", "-")
            .replace("/", "-")
        )
        return f"issue-{task.issue_number}-{slug_title[:30]}-{uuid.uuid4().hex[:6]}"
