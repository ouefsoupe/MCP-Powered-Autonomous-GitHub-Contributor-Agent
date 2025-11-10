import os
import time
import uuid
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8080")
REPO_URL = os.getenv("GITHUB_REPO_URL")
BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")

def _post(path, json):
    r = requests.post(f"{MCP_URL}{path}", json=json, timeout=60)
    r.raise_for_status()
    return r.json()

def trivial_readme_change(workdir: str) -> str:
    """Demo: append a one-line badge to README.md (creates README if missing)."""
    path = "README.md"
    # Try read; if missing, treat as empty
    try:
        current = _post("/repo/read_file", {"workdir": workdir, "path": path})["text"]
    except requests.HTTPError:
        current = ""
    new_line = f"\n\n_Updated by MCP agent run {uuid.uuid4().hex[:8]}_\n"
    new_text = (current or "# Project\n") + new_line
    resp = _post("/repo/write_file", {"workdir": workdir, "path": path, "new_text": new_text})
    return resp["diff"]

def main():
    if not REPO_URL:
        raise SystemExit("Set GITHUB_REPO_URL in environment")
    run_id = uuid.uuid4().hex[:8]
    feature_branch = f"mcp/update-{run_id}"

    # 1) Clone
    clone = _post("/repo/clone", {"url": REPO_URL, "branch": BASE_BRANCH})
    workdir = clone["workdir"]

    # 2) New branch
    _post("/git/create_branch", {"workdir": workdir, "base": BASE_BRANCH, "new_branch": feature_branch})

    # 3) Make a trivial change
    _ = trivial_readme_change(workdir)

    # 4) Commit & push
    commit = _post("/git/commit_push", {
        "workdir": workdir,
        "branch": feature_branch,
        "message": f"chore: MCP demo change ({run_id})"
    })

    # 5) Open PR
    pr = _post("/github/create_pr", {
        "repo_url": REPO_URL,
        "title": f"MCP demo change ({run_id})",
        "body": "Automated trivial update via MCP agent.",
        "head_branch": feature_branch,
        "base_branch": BASE_BRANCH
    })
    print(f"[agent] PR opened: #{pr['pr_number']} {pr['html_url']}")

if __name__ == "__main__":
    main()
