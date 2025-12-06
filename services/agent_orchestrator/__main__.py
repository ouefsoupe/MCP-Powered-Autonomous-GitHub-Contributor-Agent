import json
import os
import sys

from .agent import AgentOrchestrator, IssueTask


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m services.agent-orchestrator issue.json", file=sys.stderr)
        sys.exit(1)

    issue_file = sys.argv[1]
    with open(issue_file, "r", encoding="utf-8") as f:
        issue_payload = json.load(f)

    task = IssueTask(
        repo_url=issue_payload["repo_url"],
        base_branch=issue_payload.get("base_branch", "main"),
        issue_number=issue_payload["issue_number"],
        title=issue_payload["title"],
        body=issue_payload.get("body", ""),
        labels=issue_payload.get("labels", []),
    )

    orchestrator = AgentOrchestrator()
    result = orchestrator.run_issue_task(task)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
