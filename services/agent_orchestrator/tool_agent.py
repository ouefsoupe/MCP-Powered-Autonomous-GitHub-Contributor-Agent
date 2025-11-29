# services/agent-orchestrator/tool_agent.py

import json
import os
import sys
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

from .mcp_client import MCPClient

# Anthropic client (Claude)
from anthropic import Anthropic

# Import the secrets helper - add parent directory to path
_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

try:
    from adapters.secrets import get_secret
except ImportError:
    # Fallback if import fails (for testing or different deployment scenarios)
    def get_secret(identifier: str, *, from_aws: bool = False) -> str:
        if not from_aws:
            val = os.getenv(identifier)
            if not val:
                raise RuntimeError(f"Secret {identifier} not found in environment")
            return val
        raise RuntimeError("AWS Secrets Manager not available")

# If you’re using OpenAI:
# import openai
# openai.api_key = os.getenv("OPENAI_API_KEY")


@dataclass
class IssueTask:
    repo_url: str
    base_branch: str
    issue_number: int
    title: str
    body: str
    labels: List[str]


class ToolCallingAgent:
    """
    Agent that uses LLM tool-calling to iteratively:
    - clone repo
    - inspect files
    - edit files
    - commit + push
    - open a PR
    via MCP endpoints.
    """

    def __init__(
        self,
        mcp: Optional[MCPClient] = None,
        model: str = None,
        max_steps: int = 20,
    ):
        self.mcp = mcp or MCPClient()
        # Default model: read from env or fallback
        self.model = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
        self.max_steps = max_steps

        # Get Anthropic API key from Secrets Manager or environment variable
        api_key = None
        api_key_arn = os.getenv("SECRETS_MANAGER_ANTHROPIC_API_KEY_ARN")
        if api_key_arn:
            try:
                api_key = get_secret(api_key_arn, from_aws=True)
                print("[DEBUG] Retrieved Anthropic API key from Secrets Manager")
            except Exception as e:
                print(f"[WARNING] Failed to retrieve Anthropic API key from Secrets Manager: {e}")

        if not api_key:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if api_key:
                print("[DEBUG] Using Anthropic API key from ANTHROPIC_API_KEY env var")

        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not found in Secrets Manager or environment variables.")

        self.anthropic = Anthropic(api_key=api_key)

    # ---------- Public entry point ----------

    def run_issue_task(self, task: IssueTask) -> Dict[str, Any]:
        """
        Orchestrate an interactive session with the LLM (or fake LLM).

        Returns a summary like:
        {
          "status": "pr_created" | "no_action" | "error" | "max_steps_reached",
          "pr_number": ...,
          "pr_url": ...,
          "branch": ...,
          "details": ...
        }
        """
        # Save current task for the fake LLM to reference
        self._current_task = task
        self._fake_step = 0  # state machine step

        messages = self._initial_messages(task)
        tools = self._tool_definitions()

        last_tool_results: Dict[str, Any] = {}

        for step in range(self.max_steps):
            response = self._llm_chat(messages, tools=tools)

            message = response["choices"][0]["message"]

            tool_calls = message.get("tool_calls")
            if tool_calls:
                messages.append(message)  # keep the assistant message with tool_calls

                for tool_call in tool_calls:
                    name = tool_call["function"]["name"]
                    arguments_str = tool_call["function"]["arguments"]
                    args = json.loads(arguments_str) if arguments_str else {}

                    result = self._dispatch_tool(name, args)
                    last_tool_results[name] = result

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": name,
                        "content": json.dumps(result),
                    })

                continue  # give the LLM (fake or real) the tool results and loop

            # No tool calls: treat as final answer
            content = message.get("content") or ""
            summary = self._extract_summary_from_text(content)
            return summary

        return {
            "status": "max_steps_reached",
            "details": "Agent hit max_steps without finalizing.",
        }

    # ---------- System + user messages ----------

    def _initial_messages(self, task: IssueTask) -> List[Dict[str, Any]]:
        system_prompt = (
            "You are an autonomous coding agent with access to tools that operate on a Git "
            "repository via an MCP server. You ONLY interact with the repo via tools.\n\n"
            "High-level goal:\n"
            f"- Address GitHub issue #{task.issue_number} by performing small, safe code changes.\n"
            "\n"
            "FOR THIS TEST REPOSITORY, YOU MUST ALWAYS PERFORM THE FULL WORKFLOW:\n"
            "  1) Call clone_repo exactly once at the beginning.\n"
            "  2) Use find_files and read_file as needed to inspect the repo.\n"
            "  3) Create a new branch from the base branch using create_branch.\n"
            "  4) Make a SMALL, HARMLESS change using write_file (for example, create or update\n"
            "     a file named MCP_AUTOGEN.md with a short note about the issue).\n"
            "  5) Call commit_and_push once you are satisfied with the edits.\n"
            "  6) Call create_pr to open a pull request for that branch.\n"
            "\n"
            "Do NOT stop before calling create_pr unless the tools fail in a way that makes it "
            "impossible to continue. In normal circumstances for this repository, you SHOULD open a PR.\n"
            "\n"
            "Rules:\n"
            "- Never assume file contents; always read_file before writing.\n"
            "- Keep diffs small and focused on the issue.\n"
            "- Use create_branch before committing changes.\n"
            "- Use commit_and_push only once you are satisfied with edits.\n"
            "- Use create_pr as the final step when the branch is pushed.\n"
            "- After successfully calling create_pr, respond with a short explanation "
            "  followed by a JSON object on the last line with this shape:\n"
            '  {\"status\": \"pr_created\" | \"no_action\", \"branch\": \"...\", '
            '\"pr_number\": <int or null>, \"pr_url\": \"... or null\"}\n"'
            "- The final assistant message MUST end with that JSON object on the last line. "
            "  Do not include any extra text after the JSON.\n"
            "TEST MODE DIRECTIVE:\n"
            
            "For this specific test run, your goal is to modify README.md by appending "
            "a short 5-sentence summary describing what this project is. "
            "Keep it concise, professional, and under 120 words total.\n"
            "After updating README.md, proceed with: create_branch → write_file → commit_and_push → create_pr.\n"
            "Do NOT generate or modify other files for this test.\n"

        )

        user_prompt = (
            f"Repository URL: {task.repo_url}\n"
            f"Base branch: {task.base_branch}\n"
            f"Issue #{task.issue_number}: {task.title}\n"
            f"Issue body:\n{task.body}\n\n"
            f"Labels: {', '.join(task.labels) if task.labels else '(none)'}\n\n"
            "Your job is to decide whether a small, automated code change is appropriate. "
            "If yes, use the tools to:\n"
            "- clone_repo (once)\n"
            "- explore with find_files/read_file\n"
            "- create a new branch based on the base branch\n"
            "- edit files via write_file\n"
            "- commit_and_push\n"
            "- create_pr\n\n"
            "If no safe/actionable change is possible, do NOT call commit_and_push or create_pr. "
            "Instead, respond with status \"no_action\" in the final JSON."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # ---------- Tool definitions (LLM-visible) ----------

    def _tool_definitions(self) -> List[Dict[str, Any]]:
        """
        Tools schema for the LLM. Each maps to an MCPClient method.
        """
        return [
            {
                "name": "clone_repo",
                "description": "Clone the target repository via MCP. Call this before accessing files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "Git URL of the repository to clone.",
                        },
                        "branch": {
                            "type": "string",
                            "description": "Base branch to check out, e.g., 'main'.",
                        },
                    },
                    "required": ["url", "branch"],
                },
            },
            {
                "name": "find_files",
                "description": "Find files in the working directory using a glob pattern.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workdir": {"type": "string"},
                        "glob_pattern": {
                            "type": "string",
                            "description": "Glob pattern, e.g. '**/*.py'.",
                        },
                    },
                    "required": ["workdir", "glob_pattern"],
                },
            },
            {
                "name": "read_file",
                "description": "Read a file from the repository working directory.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workdir": {"type": "string"},
                        "path": {"type": "string"},
                    },
                    "required": ["workdir", "path"],
                },
            },
            {
                "name": "write_file",
                "description": "Overwrite a file with new content.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workdir": {"type": "string"},
                        "path": {"type": "string"},
                        "new_text": {
                            "type": "string",
                            "description": "Full new content of the file.",
                        },
                    },
                    "required": ["workdir", "path", "new_text"],
                },
            },
            {
                "name": "create_branch",
                "description": "Create a new branch from an existing base branch in the repo.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workdir": {"type": "string"},
                        "base": {"type": "string"},
                        "new_branch": {"type": "string"},
                    },
                    "required": ["workdir", "base", "new_branch"],
                },
            },
            {
                "name": "commit_and_push",
                "description": "Commit current changes and push to remote.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "workdir": {"type": "string"},
                        "branch": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    "required": ["workdir", "branch", "message"],
                },
            },
            {
                "name": "create_pr",
                "description": "Create a pull request on GitHub for the pushed branch.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string"},
                        "title": {"type": "string"},
                        "body": {"type": "string"},
                        "head_branch": {"type": "string"},
                        "base_branch": {"type": "string"},
                    },
                    "required": ["repo_url", "title", "head_branch", "base_branch"],
                },
            },
        ]

    # ---------- Tool dispatcher (Python side) ----------

    def _dispatch_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map a tool name from the LLM to an MCPClient call.
        """
        if name == "clone_repo":
            resp = self.mcp.clone_repo(
                url=args["url"],
                branch=args.get("branch"),
            )
            # includes workdir + branch
            return resp

        if name == "find_files":
            files = self.mcp.find_files(
                workdir=args["workdir"],
                glob_pattern=args["glob_pattern"],
            )
            return {"files": files}

        if name == "read_file":
            text = self.mcp.read_file(
                workdir=args["workdir"],
                path=args["path"],
            )
            return {"text": text}

        if name == "write_file":
            resp = self.mcp.write_file(
                workdir=args["workdir"],
                path=args["path"],
                new_text=args["new_text"],
            )
            return resp

        if name == "create_branch":
            resp = self.mcp.create_branch(
                workdir=args["workdir"],
                base=args["base"],
                new_branch=args["new_branch"],
            )
            return resp

        if name == "commit_and_push":
            resp = self.mcp.commit_and_push(
                workdir=args["workdir"],
                branch=args["branch"],
                message=args["message"],
            )
            return resp

        if name == "create_pr":
            resp = self.mcp.create_pr(
                repo_url=args["repo_url"],
                title=args["title"],
                body=args.get("body", ""),
                head_branch=args["head_branch"],
                base_branch=args["base_branch"],
            )
            return resp

        # Fallback
        return {"error": f"Unknown tool: {name}"}

        # ---------- LLM call wrapper (Claude) ----------

    def _llm_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Call Claude with tool support using the Anthropic Messages API.

        - Takes the current conversation (messages) and tool schema (tools).
        - Returns a response dict in the same shape as OpenAI's:
          { "choices": [ { "message": { "role": "...", "content": "...", "tool_calls": [...] } } ] }
        """

        # Anthropic expects messages as a list of {role, content}, where content is
        # a list of text blocks. We also need to pass tools and tool_choice.

        # Convert OpenAI-style messages -> Anthropic Messages API format
        anthro_messages: List[Dict[str, Any]] = []
        system_message = None
        tool_results_for_anthro: Dict[str, Any] = {}
        
        # Debug: print the messages we're processing
        print(f"DEBUG: Processing {len(messages)} messages:")
        for i, msg in enumerate(messages):
            print(f"  {i}: {msg.get('role')} - {str(msg.get('content', ''))[:100]}...")

        for msg in messages:
            role = msg["role"]

            # Extract system message separately
            if role == "system":
                system_message = msg.get("content", "")
                continue

            # Skip tool messages here; Anthropic uses "tool_result" messages,
            # but we’ll reconstruct those below, so keep them separate.
            if role == "tool":
                # Handle tool messages - Anthropic expects them as user messages with tool_result content
                tool_use_id = msg.get("tool_call_id") or msg.get("id", "")
                if tool_use_id:  # Only add tool result if we have a valid ID
                    anthro_messages.append({
                        "role": "user", 
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_id,
                                "content": str(msg.get("content", "")),
                            }
                        ],
                    })
                continue

            # Normal system/user/assistant messages
            content = msg.get("content")
            content_blocks = []
            
            # Add text content if present
            if content is not None:
                content_blocks.append({"type": "text", "text": str(content)})
            
            # For assistant messages, check if there are tool_calls to convert to tool_use blocks
            if role == "assistant" and msg.get("tool_calls"):
                for tool_call in msg["tool_calls"]:
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tool_call["id"],
                        "name": tool_call["function"]["name"],
                        "input": json.loads(tool_call["function"]["arguments"]) if tool_call["function"]["arguments"] else {}
                    })

            anthro_messages.append({
                "role": role,
                "content": content_blocks,
            })

        # Call Anthropic with system message as separate parameter
        create_args = {
            "model": self.model,
            "max_tokens": 1024,
            "tools": tools,
            "messages": anthro_messages,
        }
        
        if system_message:
            create_args["system"] = system_message
            
        resp = self.anthropic.messages.create(**create_args)

        # Anthropic returns a top-level response with a "content" array
        # that may include text blocks and/or tool_use blocks.
        tool_calls = []
        assistant_text_parts = []

        for block in resp.content:
            if block.type == "text":
                assistant_text_parts.append(block.text)
            elif block.type == "tool_use":
                # Convert Anthropic tool_use -> OpenAI-style tool_call
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input or {}),
                    },
                })

        assistant_text = "\n".join(assistant_text_parts) if assistant_text_parts else None

        # Build an OpenAI-style response object that our existing
        # run_issue_task loop already expects.
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": assistant_text,
                        # If there are tool calls, include them; otherwise None
                        "tool_calls": tool_calls if tool_calls else None,
                    }
                }
            ]
        }

    # ---------- Final summary parsing ----------

    def _extract_summary_from_text(self, content: str) -> Dict[str, Any]:
        """
        Parse the final message from the LLM to extract the JSON summary.
        We told it to put a JSON object on the last line.
        """
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if not lines:
            return {"status": "no_action", "details": "Empty final response from LLM."}

        last = lines[-1].strip()
        try:
            data = json.loads(last)
            # Sanity defaults
            data.setdefault("status", "no_action")
            data.setdefault("pr_number", None)
            data.setdefault("pr_url", None)
            return data
        except json.JSONDecodeError:
            # Couldn’t parse; treat as no_action but preserve raw content
            return {
                "status": "no_action",
                "details": "Could not parse final JSON summary.",
                "raw_response": content,
            }
            

    def _extract_tool_state(self, messages: List[Dict[str, Any]], tool_name: str) -> Dict[str, Any]:
        """
        Find the last tool-message for a given tool_name and return its JSON content.
        """
        for msg in reversed(messages):
            if msg.get("role") == "tool" and msg.get("name") == tool_name:
                try:
                    return json.loads(msg.get("content") or "{}")
                except json.JSONDecodeError:
                    return {}
        return {}