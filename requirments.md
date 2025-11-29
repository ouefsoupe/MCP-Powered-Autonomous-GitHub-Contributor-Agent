# MCP-Powered Autonomous GitHub Contributor Agent

## Project Overview

This project implements a **self-contained autonomous agent system** designed to run on AWS and interact with GitHub repositories using the **Model Context Protocol (MCP)**.  
The goal is to demonstrate an automated workflow where a large language model (LLM) can autonomously **check out code**, **make edits**, **commit changes**, **push branches**, and **submit pull requests (PRs)** to a repository — all through an MCP server that provides a controlled interface for these operations.

## Core Requirements

### 1. MCP Server
- The **MCP Server** acts as the bridge between the LLM and the Git environment.
- It exposes a set of HTTP endpoints that the LLM can call to perform controlled git operations.
- The server must be able to:
  - **Clone repositories** (with repo allowlisting for security)
  - **Create and switch branches**
  - **Read and write files**
  - **Commit and push changes**
  - **Create pull requests** via the GitHub API
- All git operations are executed within isolated working directories, using the server’s environment-configured credentials (e.g., SSH key + GitHub token).
- The MCP server runs locally and exposes its endpoints (typically on `http://localhost:8080`) for the LLM or automation script to call.

### 2. Authentication
- Git operations are authenticated using an SSH key configured as a **deploy key** or **user key** with write permissions.
- The server also requires a **GitHub Personal Access Token (PAT)** with `public_repo` or equivalent scope to open pull requests via the GitHub REST API.
- Both the SSH key and token are stored securely as environment variables within the MCP server environment. 

### 3. Large Language Model Integration
- The **LLM acts as the “coder”** — it determines what changes to make and when to perform git operations.
- The **LLM communicates exclusively through the MCP server API**, ensuring it cannot directly access the file system or GitHub credentials.
- The LLM can:
  1. Receive context from GitHub (via webhook events or polling)
  2. Call the MCP server’s `/repo/clone` endpoint to clone the target repo
  3. Modify or create files by calling `/repo/read_file` and `/repo/write_file`
  4. Commit and push changes via `/git/commit_push`
  5. Open a pull request via `/github/create_pr`

### 4. Webhooks
- A **GitHub webhook** triggers the LLM process whenever new issues, PRs, or relevant events occur in the target repository.
- When triggered, the webhook sends an event payload (e.g., “new issue created”) to a small listener service or queue that the LLM can access.
- The LLM uses the context of this event to determine its next action (e.g., analyze issue text, generate code, or create a branch for a fix).

### 5. Workflow Summary

**End-to-end flow:**
1. A GitHub **webhook** notifies the LLM process (e.g., new issue or task).
2. The LLM retrieves context from the event and decides what code changes are needed.
3. The LLM calls the **MCP server** to:
   - Clone the target repository (`/repo/clone`)
   - Create a new branch (`/git/create_branch`)
   - Read/write files (`/repo/read_file`, `/repo/write_file`)
   - Commit and push changes (`/git/commit_push`)
4. Finally, the LLM calls `/github/create_pr` to open a pull request back to the main branch.
5. The GitHub repository then contains a new PR ready for review — fully generated and submitted by the autonomous agent.

### 6. Configuration & Environment

**Required Environment Variables:**
```bash
export GITHUB_BASE_BRANCH="main"
export GITHUB_REPO_URL="git@github-mcp:<user>/<repo>.git"
export UPSTREAM_REPO_URL="https://github.com/<user>/<repo>.git"
export ALLOWED_REPOS="https://github.com/<user>/<repo>.git,git@github-mcp:<user>/<repo>.git,git@github.com:<user>/<repo>.git,ssh://git@github.com/<user>/<repo>.git"
export GITHUB_TOKEN=<your_personal_access_token>
