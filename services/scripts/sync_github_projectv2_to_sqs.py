#!/usr/bin/env python3
"""
Sync GitHub Projects V2 (new Projects) to SQS.

This script uses the GitHub GraphQL API to fetch project data,
since Projects V2 is not available via REST API.
"""

import sys
from pathlib import Path

# Force project root onto sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import os
import json

import boto3
import requests
from dotenv import load_dotenv

from adapters.secrets import get_secret

# Load .env
load_dotenv(override=True)

GITHUB_GRAPHQL_API = "https://api.github.com/graphql"

GITHUB_OWNER = os.getenv("GITHUB_OWNER", "ouefsoupe")
GITHUB_REPO = os.getenv("GITHUB_REPO", "javaLearning")
GITHUB_PROJECT_NAME = os.getenv("GITHUB_PROJECT_NAME", "mcp-java-board")
SQS_TICKET_QUEUE_URL = os.environ["SQS_TICKET_QUEUE_URL"]

# Status mapping (customize based on your project columns)
COLUMN_STATUS_MAP = {
    "Todo": "todo",
    "To do": "todo",
    "In Progress": "in_progress",
    "Dev Complete": "dev_complete",
    "Done": "done",
}


def _get_github_token() -> str:
    """Get GitHub PAT from Secrets Manager or environment."""
    pat_arn = os.getenv("SECRETS_MANAGER_GITHUB_PAT_ARN")
    if pat_arn:
        try:
            return get_secret(pat_arn, from_aws=True)
        except Exception as e:
            print(f"[WARNING] Failed to retrieve GitHub token from Secrets Manager: {e}")

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GitHub token not configured")
    return token


GITHUB_TOKEN = _get_github_token()

# Get AWS region
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
sqs = boto3.client("sqs", region_name=AWS_REGION)


def graphql_query(query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query against GitHub API."""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if variables:
        payload["variables"] = variables

    resp = requests.post(GITHUB_GRAPHQL_API, json=payload, headers=headers)
    resp.raise_for_status()

    data = resp.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data["data"]


def get_repo_projects_v2():
    """Fetch all Projects V2 for the repository using GraphQL."""
    query = """
    query($owner: String!, $repo: String!) {
      repository(owner: $owner, name: $repo) {
        projectsV2(first: 10) {
          nodes {
            id
            title
            number
            url
          }
        }
      }
    }
    """

    variables = {"owner": GITHUB_OWNER, "repo": GITHUB_REPO}
    data = graphql_query(query, variables)

    projects = data["repository"]["projectsV2"]["nodes"]
    print(f"Found {len(projects)} Projects V2")
    return projects


def find_project_by_name(name: str):
    """Find a project by name."""
    projects = get_repo_projects_v2()
    for p in projects:
        if p["title"] == name:
            return p
    raise RuntimeError(f"Project named '{name}' not found on {GITHUB_OWNER}/{GITHUB_REPO}")


def get_project_items(project_id: str):
    """
    Fetch all items (issues/PRs) from a Projects V2 board.

    Note: Projects V2 uses a different structure than classic projects.
    Items have fields and values, not columns.
    """
    query = """
    query($projectId: ID!, $cursor: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100, after: $cursor) {
            pageInfo {
              hasNextPage
              endCursor
            }
            nodes {
              id
              fieldValues(first: 20) {
                nodes {
                  ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field {
                      ... on ProjectV2SingleSelectField {
                        name
                      }
                    }
                  }
                }
              }
              content {
                ... on Issue {
                  number
                  title
                  body
                  url
                  labels(first: 10) {
                    nodes {
                      name
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    all_items = []
    cursor = None

    while True:
        variables = {"projectId": project_id, "cursor": cursor}
        data = graphql_query(query, variables)

        items_data = data["node"]["items"]
        all_items.extend(items_data["nodes"])

        if not items_data["pageInfo"]["hasNextPage"]:
            break

        cursor = items_data["pageInfo"]["endCursor"]

    print(f"Found {len(all_items)} items in project")
    return all_items


def extract_status_from_item(item: dict) -> str:
    """
    Extract the status field value from a project item.
    Projects V2 uses custom fields instead of columns.
    """
    field_values = item.get("fieldValues", {}).get("nodes", [])

    for field_value in field_values:
        field = field_value.get("field", {})
        field_name = field.get("name", "")

        # Look for a field named "Status" (customize if your field has a different name)
        if field_name.lower() == "status":
            status_name = field_value.get("name", "")
            return COLUMN_STATUS_MAP.get(status_name, "unknown")

    return "unknown"


def enqueue_issue(issue_content: dict, project: dict, status: str):
    """Send an issue to SQS queue."""
    if not issue_content:
        return

    if status == "unknown":
        print(f"  [WARN] Unknown status for issue #{issue_content.get('number')}, skipping")
        return

    labels = [lbl["name"] for lbl in issue_content.get("labels", {}).get("nodes", [])]

    payload = {
        "source": "github",
        "repo": f"{GITHUB_OWNER}/{GITHUB_REPO}",
        "issue_number": issue_content["number"],
        "project_id": project["number"],
        "project_name": project["title"],
        "status": status,
        "title": issue_content["title"],
        "body": issue_content.get("body") or "",
        "labels": labels,
        "html_url": issue_content["url"],
    }

    print(f"Enqueueing issue #{issue_content['number']} with status '{status}'")
    sqs.send_message(
        QueueUrl=SQS_TICKET_QUEUE_URL,
        MessageBody=json.dumps(payload),
        MessageAttributes={
            "status": {"DataType": "String", "StringValue": status},
            "repo": {"DataType": "String", "StringValue": f"{GITHUB_OWNER}/{GITHUB_REPO}"},
        },
    )


def sync_project_to_sqs():
    """Main sync function."""
    project = find_project_by_name(GITHUB_PROJECT_NAME)
    print(f"Found project '{project['title']}' (#{project['number']})")
    print(f"URL: {project['url']}")

    items = get_project_items(project["id"])

    for item in items:
        content = item.get("content")
        if not content:
            # Skip items without content (e.g., draft issues)
            continue

        status = extract_status_from_item(item)

        # Skip done items
        if status == "done":
            print(f"  Skipping issue #{content['number']} (status: done)")
            continue

        enqueue_issue(content, project, status)


if __name__ == "__main__":
    print(f"Syncing GitHub Projects V2 for {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"Project name: {GITHUB_PROJECT_NAME}")
    print(f"SQS Queue: {SQS_TICKET_QUEUE_URL}")
    print()
    sync_project_to_sqs()
    print("\nSync complete!")
