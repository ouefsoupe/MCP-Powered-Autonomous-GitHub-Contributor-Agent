import os
import json
import tempfile
import uuid
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from adapters.git_ops import clone_repo, create_branch, write_file_and_diff, commit_and_push
from adapters.github_client import GitHubClient
from adapters.secrets import get_secret

load_dotenv(override=True)

PORT = int(os.getenv("MCP_SERVER_PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
ALLOWED_REPOS = set([s.strip() for s in os.getenv("ALLOWED_REPOS", "").split(",") if s.strip()])
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"

app = FastAPI(title="MCP Server", version="0.1.0")

# ------------ Models -------------
class Health(BaseModel):
    status: str = "ok"
    message: str = "mcp-server alive"

class RepoCloneReq(BaseModel):
    url: str
    branch: Optional[str] = None

class RepoCloneResp(BaseModel):
    workdir: str
    branch: Optional[str] = None
    trace_id: str

class FindFilesReq(BaseModel):
    workdir: str
    glob: str = "**/*"

class FindFilesResp(BaseModel):
    files: List[str]

class ReadFileReq(BaseModel):
    workdir: str
    path: str

class ReadFileResp(BaseModel):
    text: str

class WriteFileReq(BaseModel):
    workdir: str
    path: str
    new_text: str

class WriteFileResp(BaseModel):
    diff: str
    bytes_changed: int

class CreateBranchReq(BaseModel):
    workdir: str
    base: str
    new_branch: str

class CommitPushReq(BaseModel):
    workdir: str
    branch: str
    message: str

class CommitPushResp(BaseModel):
    commit_sha: str
    remote_ref: str

class CreatePRReq(BaseModel):
    repo_url: str
    title: str
    body: str = ""
    head_branch: str
    base_branch: str

class CreatePRResp(BaseModel):
    pr_number: int
    html_url: str

# ------------ Helpers -------------
def _ensure_allowed_repo(url: str):
    if ALLOWED_REPOS and url not in ALLOWED_REPOS:
        raise HTTPException(status_code=403, detail="Repo not allowlisted " + url,)

def _github_client() -> GitHubClient:
    # Prefer Secrets Manager if ARN present
    pat_arn = os.getenv("SECRETS_MANAGER_GITHUB_PAT_ARN")
    token = None
    if pat_arn:
        try:
            token = get_secret(pat_arn, from_aws=True)
        except Exception:
            pass
    if not token:
        token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="GitHub token not configured")
    return GitHubClient(token)

# ------------ Endpoints -------------
@app.get("/health", response_model=Health)
def health():
    return Health()

@app.post("/repo/clone", response_model=RepoCloneResp)
def repo_clone(req: RepoCloneReq):
    _ensure_allowed_repo(req.url)
    tmpdir = tempfile.mkdtemp(prefix="mcp-")
    branch = clone_repo(req.url, tmpdir, branch=req.branch)
    trace_id = uuid.uuid4().hex
    return RepoCloneResp(workdir=tmpdir, branch=branch, trace_id=trace_id)

@app.post("/repo/find_files", response_model=FindFilesResp)
def repo_find_files(req: FindFilesReq):
    import glob, os as _os
    pattern = _os.path.join(req.workdir, req.glob)
    files = [p for p in glob.glob(pattern, recursive=True) if os.path.isfile(p)]
    return FindFilesResp(files=files)

@app.post("/repo/read_file", response_model=ReadFileResp)
def repo_read_file(req: ReadFileReq):
    file_path = os.path.join(req.workdir, req.path)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="file not found")
    with open(file_path, "r", encoding="utf-8") as f:
        return ReadFileResp(text=f.read())

@app.post("/repo/write_file", response_model=WriteFileResp)
def repo_write_file(req: WriteFileReq):
    diff, delta = write_file_and_diff(req.workdir, req.path, req.new_text)
    return WriteFileResp(diff=diff, bytes_changed=delta)

@app.post("/git/create_branch")
def git_create_branch(req: CreateBranchReq):
    create_branch(req.workdir, req.base, req.new_branch)
    return {"status": "ok"}

@app.post("/git/commit_push", response_model=CommitPushResp)
def git_commit_push(req: CommitPushReq):
    sha, ref = commit_and_push(
        req.workdir, req.branch, req.message,
        push=not DRY_RUN
    )
    if DRY_RUN:
        ref = f"(dry-run) {ref}"
    return CommitPushResp(commit_sha=sha, remote_ref=ref)

@app.post("/github/create_pr", response_model=CreatePRResp)
def github_create_pr(req: CreatePRReq):
    _ensure_allowed_repo(req.repo_url)
    if DRY_RUN:
        return CreatePRResp(pr_number=0, html_url="(dry-run) not created")
    gh = _github_client()
    pr = gh.create_pr(
        repo_url=req.repo_url,
        title=req.title,
        body=req.body,
        head=req.head_branch,
        base=req.base_branch,
    )
    return CreatePRResp(pr_number=pr["number"], html_url=pr["html_url"])



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=PORT, log_level="info")
