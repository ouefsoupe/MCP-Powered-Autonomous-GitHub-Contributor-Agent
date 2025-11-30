#!/usr/bin/env python3

import sys
from pathlib import Path

# Force project root (…/MCP-Powered-Autonomous-GitHub-Contributor-Agent) onto sys.path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# print("DEBUG: ROOT =", ROOT)
# print("DEBUG: sys.path[0] =", sys.path[0])
# print("DEBUG: looking for:", Path(ROOT, "adapters/secrets.py"))

import os
import json

import boto3
import requests
from dotenv import load_dotenv

from adapters.secrets import get_secret


# Load .env so we get SECRETS_MANAGER_GITHUB_PAT_ARN, SQS_TICKET_QUEUE_URL, etc.
load_dotenv(override=True)

GITHUB_API = "https://api.github.com"

GITHUB_OWNER = os.getenv("GITHUB_OWNER", "ouefsoupe")
GITHUB_REPO = os.getenv("GITHUB_REPO", "javaLearning")
GITHUB_PROJECT_NAME = os.getenv("GITHUB_PROJECT_NAME", "mcp-java-board")
SQS_TICKET_QUEUE_URL = os.environ["SQS_TICKET_QUEUE_URL"]  # required

# Board → normalized status
COLUMN_STATUS_MAP = {
    "Todo": "todo",
    "To do": "todo",
    "In Progress": "in_progress",
    "Dev Complete": "dev_complete",
    "Done": "done",
}


def _get_github_token() -> str:
    """
    Same logic as in app.py:
    - Prefer Secrets Manager via SECRETS_MANAGER_GITHUB_PAT_ARN
    - Fallback to GITHUB_TOKEN env if present (e.g. for local dev)
    """
    pat_arn = os.getenv("SECRETS_MANAGER_GITHUB_PAT_ARN")
    if pat_arn:
        try:
            return get_secret(pat_arn, from_aws=True)
        except Exception as e:
            print(f"[WARNING] Failed to retrieve GitHub token from Secrets Manager: {e}")

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token not configured (no secret ARN and no GITHUB_TOKEN)")
    return token


GITHUB_TOKEN = _get_github_token()

session = requests.Session()
session.headers.update(
    {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        # Required for classic Projects API
        "Accept": "application/vnd.github.inertia+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
)

# Get AWS region from environment, default to us-east-1
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
sqs = boto3.client("sqs", region_name=AWS_REGION)


def get_repo_projects():
    """Get classic projects (Projects V1) for the repository."""
    url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/projects"
    print(f"Fetching classic projects from: {url}")
    resp = session.get(url)

    if resp.status_code == 404:
        print("[ERROR] Classic Projects API returned 404")
        print("This repository likely uses GitHub Projects V2 (new Projects Beta)")
        print("Projects V2 requires GraphQL API instead of REST API")
        print("\nTo check if the repo has Projects V2:")
        print(f"  Visit: https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/projects")
        raise RuntimeError(
            "Classic Projects not found. This repository may be using Projects V2, "
            "which requires GraphQL API. Please check the GitHub repository."
        )

    resp.raise_for_status()
    projects = resp.json()
    print(f"Found {len(projects)} classic projects")
    return projects


def find_project_by_name(name: str):
    for p in get_repo_projects():
        if p["name"] == name:
            return p
    raise RuntimeError(f"Project named '{name}' not found on {GITHUB_OWNER}/{GITHUB_REPO}")


def get_project_columns(project_id: int):
    url = f"{GITHUB_API}/projects/{project_id}/columns"
    resp = session.get(url)
    resp.raise_for_status()
    return resp.json()


def get_column_cards(column_id: int):
    url = f"{GITHUB_API}/projects/columns/{column_id}/cards"
    resp = session.get(url, params={"per_page": 100})
    resp.raise_for_status()
    return resp.json()


def fetch_issue_from_card(card):
    """
    Skip note cards; only process cards linked to issues.
    """
    content_url = card.get("content_url")
    if not content_url:
        return None

    resp = session.get(content_url)
    resp.raise_for_status()
    issue = resp.json()

    # Ignore PRs for now; only issues
    if "pull_request" in issue:
        return None
    return issue


def enqueue_issue(issue, project, column_name: str):
    status = COLUMN_STATUS_MAP.get(column_name)
    if not status:
        print(f"  [WARN] Unknown column '{column_name}', skipping issue #{issue['number']}")
        return

    payload = {
        "source": "github",
        "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "issue_number": issue["number"],
        "project_id": project["id"],
        "project_name": project["name"],
        "column_name": column_name,
        "status": status,
        "title": issue["title"],
        "body": issue.get("body") or "",
        "labels": [lbl["name"] for lbl in issue.get("labels", [])],
        "html_url": issue["html_url"],
    }

    print(f"Enqueueing issue #{issue['number']} in '{column_name}' as status '{status}'")
    sqs.send_message(
        QueueUrl=SQS_TICKET_QUEUE_URL,
        MessageBody=json.dumps(payload),
        MessageAttributes={
            "status": {"DataType": "String", "StringValue": status},
            "repo": {"DataType": "String", "StringValue": f"{GITHUB_OWNER}/{GITHUB_REPO}"},
        },
    )


def sync_project_to_sqs():
    project = find_project_by_name(GITHUB_PROJECT_NAME)
    print(f"Found project {project['name']} (id={project['id']})")

    columns = get_project_columns(project["id"])
    print(f"Found {len(columns)} columns")

    for col in columns:
        col_name = col["name"]
        print(f"Processing column '{col_name}' (id={col['id']})")
        cards = get_column_cards(col["id"])
        print(f"  {len(cards)} cards in this column")

        for card in cards:
            issue = fetch_issue_from_card(card)
            if not issue:
                continue

            # Example policy: enqueue everything not in Done
            if COLUMN_STATUS_MAP.get(col_name) != "done":
                enqueue_issue(issue, project, col_name)
            else:
                print(f"  Skipping issue #{issue['number']} in 'Done'")


if __name__ == "__main__":
    sync_project_to_sqs()
