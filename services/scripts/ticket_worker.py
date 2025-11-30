#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import json
import boto3
from dotenv import load_dotenv

from services.agent_orchestrator.tool_agent import ToolCallingAgent, IssueTask

load_dotenv(override=True)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
SQS_TICKET_QUEUE_URL = os.environ["SQS_TICKET_QUEUE_URL"]
UPSTREAM_REPO_URL = os.environ["UPSTREAM_REPO_URL"]
GITHUB_BASE_BRANCH = os.getenv("GITHUB_BASE_BRANCH", "main")

sqs = boto3.client("sqs", region_name=AWS_REGION)


def handle_ticket(msg_body: dict):
    issue_number = msg_body["issue_number"]
    title = msg_body["title"]
    body = msg_body.get("body") or ""
    labels = msg_body.get("labels", [])

    task = IssueTask(
        repo_url=UPSTREAM_REPO_URL,
        base_branch=GITHUB_BASE_BRANCH,
        issue_number=issue_number,
        title=title,
        body=body,
        labels=labels,
    )

    agent = ToolCallingAgent(max_steps=20)
    result = agent.run_issue_task(task)
    print(f"Agent result for issue #{issue_number}: {result}")


def main():
    print("Worker listening for tickets on SQS…")
    while True:
        resp = sqs.receive_message(
            QueueUrl=SQS_TICKET_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,          # long polling
            MessageAttributeNames=["All"],
        )

        msgs = resp.get("Messages", [])
        if not msgs:
            continue

        for msg in msgs:
            receipt_handle = msg["ReceiptHandle"]
            body = json.loads(msg["Body"])

            try:
                print(f"Processing ticket: issue #{body['issue_number']}")
                handle_ticket(body)
                # only delete on success
                sqs.delete_message(
                    QueueUrl=SQS_TICKET_QUEUE_URL,
                    ReceiptHandle=receipt_handle,
                )
                print(f"Deleted message for issue #{body['issue_number']}")
            except Exception as e:
                print(f"[ERROR] Failed to process message: {e}")


if __name__ == "__main__":
    main()
