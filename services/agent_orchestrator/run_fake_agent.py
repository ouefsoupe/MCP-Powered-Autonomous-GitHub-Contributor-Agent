# run_fake_agent.py
import os
from dotenv import load_dotenv
from .tool_agent import ToolCallingAgent, IssueTask

# Load .env so ANTHROPIC_API_KEY, UPSTREAM_REPO_URL, etc. are available
load_dotenv()


def main():
    task = IssueTask(
        repo_url=os.environ["UPSTREAM_REPO_URL"],
        base_branch=os.environ.get("GITHUB_BASE_BRANCH", "main"),
        issue_number=1,
        title="Fake test issue",
        body="This is a fake issue used to test the MCP agent.",
        labels=["mcp-fake", "testing"],
    )

    agent = ToolCallingAgent(max_steps=20)
    result = agent.run_issue_task(task)
    print("Agent result:", result)

if __name__ == "__main__":
    main()
