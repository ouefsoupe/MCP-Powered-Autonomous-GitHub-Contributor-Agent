#!/usr/bin/env python3

import sys
from pathlib import Path

# Force project root (…/MCP-Powered-Autonomous-GitHub-Contributor-Agent) onto sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import json

import boto3
import requests
from dotenv import load_dotenv

from adapters.secrets import get_secret

# Load .env so we get SECRETS_MANAGER_GITHUB_PAT_ARN, SQS_TICKET_QUEUE_URL, AWS_REGION, etc.
load_dotenv(override=True)

GITHUB_API = "https://api.github.com"

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

GITHUB_OWNER = os.getenv("GITHUB_OWNER", "ouefsoupe")
GITHUB_REPO = os.getenv("GITHUB_REPO", "javaLearning")

# SQS ticket queue URL (required)
SQS_TICKET_QUEUE_URL = os.environ["SQS_TICKET_QUEUE_URL"]

# Label → normalized status
STATUS_LABEL_MAP = {
    "status: todo": "todo",
    "status: in-progress": "in_progress",
    "status: dev-complete": "dev_complete",
    "status: done": "done",
}


def _get_github_token() -> str:
    """
    - Prefer Secrets Manager via SECRETS_MANAGER_GITHUB_PAT_ARN
    - Fallback to GITHUB_TOKEN env for local dev

    Handles JSON secrets like:
      {"GITHUB_TOKEN": "github_pat_..."}
    """

    def _extract_token(raw: str) -> str:
        raw = raw.strip()
        # Try JSON first
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "GITHUB_TOKEN" in data:
                    return str(data["GITHUB_TOKEN"]).strip()
                # Single-key dict: just take the value
                if len(data) == 1:
                    return str(next(iter(data.values()))).strip()
        except json.JSONDecodeError:
            pass  # not JSON, fall through

        # Not JSON or couldn't extract – treat raw as the token
        return raw

    pat_arn = os.getenv("SECRETS_MANAGER_GITHUB_PAT_ARN")
    if pat_arn:
        try:
            raw = get_secret(pat_arn, from_aws=True)
            return _extract_token(raw)
        except Exception as e:
            print(f"[WARNING] Failed to retrieve GitHub token from Secrets Manager: {e}")

    raw_env = os.getenv("GITHUB_TOKEN")
    if not raw_env:
        raise RuntimeError("GitHub token not configured (no secret ARN and no GITHUB_TOKEN)")

    return _extract_token(raw_env)


GITHUB_TOKEN = _get_github_token()

session = requests.Session()
session.headers.update(
    {
        # Works for both classic + fine-grained PATs
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
)

sqs = boto3.client("sqs", region_name=AWS_REGION)


def fetch_open_issues():
    """
    Fetch open issues for the repo.
    NOTE: This returns both issues and PRs; we filter PRs out.
    """
    issues = []
    page = 1

    while True:
        url = f"{GITHUB_API}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
        resp = session.get(
            url,
            params={"state": "open", "per_page": 100, "page": page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break

        issues.extend(batch)
        page += 1

    return issues


def infer_status_from_labels(issue) -> str | None:
    """
    Look at an issue's labels and map them to a normalized status.
    Returns:
      - "todo", "in_progress", "dev_complete", "done", or
      - None if no known status label is present.
    """
    labels = [lbl["name"] for lbl in issue.get("labels", [])]
    for label in labels:
        normalized = STATUS_LABEL_MAP.get(label)
        if normalized:
            return normalized
    return None


def enqueue_issue(issue, status: str):
    """
    Put the issue into the SQS ticket queue with metadata.
    """
    payload = {
        "source": "github",
        "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "issue_number": issue["number"],
        "status": status,
        "title": issue["title"],
        "body": issue.get("body") or "",
        "labels": [lbl["name"] for lbl in issue.get("labels", [])],
        "html_url": issue["html_url"],
    }

    print(f"Enqueueing issue #{issue['number']} with status '{status}'")

    sqs.send_message(
        QueueUrl=SQS_TICKET_QUEUE_URL,
        MessageBody=json.dumps(payload),
        MessageAttributes={
            "status": {"DataType": "String", "StringValue": status},
            "repo": {
                "DataType": "String",
                "StringValue": f"{GITHUB_OWNER}/{GITHUB_REPO}",
            },
        },
    )


def sync_issues_to_sqs():
    """
    Main sync:
    - Fetch all open issues
    - Infer status from labels
    - Enqueue everything that is NOT 'done'
    """
    print(f"Fetching open issues for {GITHUB_OWNER}/{GITHUB_REPO}...")
    issues = fetch_open_issues()
    print(f"Found {len(issues)} open items (issues + PRs).")

    count_enqueued = 0
    count_skipped_prs = 0
    count_skipped_no_status = 0
    count_skipped_done = 0

    for issue in issues:
        # Skip PRs (they have 'pull_request' field)
        if "pull_request" in issue:
            count_skipped_prs += 1
            continue

        status = infer_status_from_labels(issue)
        if status is None:
            count_skipped_no_status += 1
            print(f"  [WARN] Issue #{issue['number']} has no status:* label, skipping")
            continue

        if status == "done":
            count_skipped_done += 1
            print(f"  Skipping issue #{issue['number']} with status 'done'")
            continue

        enqueue_issue(issue, status)
        count_enqueued += 1

    print("Sync complete.")
    print(f"  Enqueued:          {count_enqueued}")
    print(f"  Skipped PRs:       {count_skipped_prs}")
    print(f"  Skipped no status: {count_skipped_no_status}")
    print(f"  Skipped done:      {count_skipped_done}")


if __name__ == "__main__":
    sync_issues_to_sqs()
