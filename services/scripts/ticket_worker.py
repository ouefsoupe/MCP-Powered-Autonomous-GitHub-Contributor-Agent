#!/usr/bin/env python3

import sys
from pathlib import Path

# Force project root (…/MCP-Powered-Autonomous-GitHub-Contributor-Agent) onto sys.path
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import json
import os
import time
import traceback

import boto3
from dotenv import load_dotenv

from adapters.secrets import get_secret
from services.agent_orchestrator.tool_agent import ToolCallingAgent, IssueTask

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Logging setup for agent worker

ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

WORKER_LOG_FILE = LOG_DIR / "agent-worker.log"

worker_logger = logging.getLogger("agent_worker")
worker_logger.setLevel(logging.INFO)

if not worker_logger.handlers:
    handler = RotatingFileHandler(WORKER_LOG_FILE, maxBytes=5_000_000, backupCount=3)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    worker_logger.addHandler(handler)


# Env + AWS clients

load_dotenv(override=True)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SQS_TICKET_QUEUE_URL = os.environ["SQS_TICKET_QUEUE_URL"]  # required

UPSTREAM_REPO_URL = os.environ["UPSTREAM_REPO_URL"]
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")

sqs = boto3.client("sqs", region_name=AWS_REGION)


# Anthropic API key handling

def _get_anthropic_api_key() -> str:
    """
    Get the Anthropic API key from Secrets Manager or env.

    Handles both:
      - raw: "sk-ant-api03-..."
      - JSON blob: {"ANTHROPIC_API_KEY": "sk-ant-api03-..."}
    """

    def _extract_key(raw: str) -> str:
        raw = raw.strip()
        # Try JSON first
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                if "ANTHROPIC_API_KEY" in data:
                    return str(data["ANTHROPIC_API_KEY"]).strip()
                # If it's a single-key dict, just take its value
                if len(data) == 1:
                    return str(next(iter(data.values()))).strip()
        except json.JSONDecodeError:
            pass  # Not JSON; fall through

        # Fallback: assume raw key
        return raw

    arn = os.getenv("SECRETS_MANAGER_ANTHROPIC_API_KEY_ARN")
    if arn:
        try:
            raw = get_secret(arn, from_aws=True)
            key = _extract_key(raw)
            worker_logger.info("[DEBUG] Retrieved Anthropic API key from Secrets Manager")
            return key
        except Exception as e:
            worker_logger.info(f"[WARNING] Failed to retrieve Anthropic key from Secrets Manager: {e}")

    raw_env = os.getenv("ANTHROPIC_API_KEY")
    if not raw_env:
        raise RuntimeError(
            "Anthropic API key not configured "
            "(no SECRETS_MANAGER_ANTHROPIC_API_KEY_ARN and no ANTHROPIC_API_KEY env var)"
        )

    key = _extract_key(raw_env)
    worker_logger.info("[DEBUG] Using Anthropic API key from environment")
    return key


# SQS helpers

def receive_ticket():
    """Long-poll SQS for a single ticket message."""
    resp = sqs.receive_message(
        QueueUrl=SQS_TICKET_QUEUE_URL,
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20,
        MessageAttributeNames=["All"],
    )
    messages = resp.get("Messages", [])
    if not messages:
        return None
    return messages[0]


def delete_ticket(receipt_handle: str):
    sqs.delete_message(QueueUrl=SQS_TICKET_QUEUE_URL, ReceiptHandle=receipt_handle)


def parse_ticket(msg_body: str) -> IssueTask:
    """
    Convert the JSON payload from sync_github_project_to_sqs.py
    into an IssueTask for ToolCallingAgent.
    """
    payload = json.loads(msg_body)

    return IssueTask(
        repo_url=UPSTREAM_REPO_URL,
        base_branch=GITHUB_BASE_BRANCH,
        issue_number=payload["issue_number"],
        title=payload.get("title") or f"Issue #{payload['issue_number']}",
        body=payload.get("body") or "",
        labels=payload.get("labels", []),
    )


# Main worker loop

def main():
    # Make sure the underlying orchestrator sees a clean key value
    anthropic_key = _get_anthropic_api_key()
    os.environ["ANTHROPIC_API_KEY"] = anthropic_key

    from services.agent_orchestrator.tool_agent import ToolCallingAgent  # re-import after env set

    agent = ToolCallingAgent(max_steps=40)

    worker_logger.info("Worker listening for tickets on SQS…")
    while True:
        msg = receive_ticket()
        if msg is None:
            # No messages, loop again
            continue

        receipt = msg["ReceiptHandle"]
        body = msg["Body"]

        try:
            task = parse_ticket(body)
            worker_logger.info(f"Processing ticket: issue #{task.issue_number}")

            result = agent.run_issue_task(task)
            worker_logger.info("Agent result:", result)

            # Only delete on success
            delete_ticket(receipt)
        except Exception as e:
            worker_logger.info(f"[ERROR] Failed to process message: {e}")
            traceback.print_exc()
            # Optionally: move to a DLQ or leave it to be retried
            time.sleep(2)


if __name__ == "__main__":
    main()
