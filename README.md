# MCP-Powered-Autonomous-GitHub-Contributor-Agent
Project Proposal: MCP-Powered Autonomous GitHub Contributor Agent
Team: Grayson Richard

Project Description:
For my final project I plan to deploy a self-contained agent system that runs entirely on AWS and interacts with GitHub to create small, automated code contributions. The project will use the Model Context Protocol (MCP) as the central interface layer that allows a large language model based process to safely interact with compute, storage, and external APIs inside a controlled cloud environment. By hosting this workflow on a virtualized server and integrating it with services such as EC2, S3, CloudWatch, and Secrets Manager, the project will hopefully demo how an application can scale, monitor, and coordinate automated tasks in a distributed cloud setting.

Project Goals:
	I plan to build a cloud-hosted Model Context Protocol (MCP) server that can run autonomously and interact with GitHub through the GitHub API. The system will watch for new issues in a selected open-source repository and respond automatically. I plan to start with a fork of a pre-existing repository and make my own tickets. When a new ticket appears the MCP server will wake up a process that will do the following:
Clone the repository into a secure temporary workspace on an EC2 instance
Analyze the posted issue and related code sections
Make inline code changes. (As many LLM’s will do full file overwrites and determining which blocks of code need to be changed in a file may be exceedingly difficult this could be re-worked to just be full file overwrites)
Commit changes and open a pull request
Log all MCP activity for debugging and tracing
The goal of this project is to ultimately use the cloud to host a suite of MCP tools for an LLM to use. This will involve storage, logs, API calls, VPC’s, and complex permissions.


Software Components and Services:
Component
Purpose
Cloud Service
MCP Server
Main backend process that exposes developer tool to LLM (filesystem, GitHub API)
AWS EC2
Contributor Agent
Handles webhook trigger and requests MCP tool calls
Containerized in same EC2 instance as MCP server
GitHub API
Source of issues/ticket, repo data and pull request endpoint
External service accessed through MCP and thus EC2
Server log storage
Stores run logs, diffs 
AWS S3
Authenticator for API’s and MCP
Holds GitHub API tokens and credentials
AWS Secrets Manager
Server log display


Monitors and displays logs, for debugging later
AWS CloudWatch


System Architecture:

Software Interaction:
	A github webhook will act as an external trigger that activates the EC2 instance and MCP server. The MCP server will expose a set of tools that will be built upon the GitPython library which has functions for checking out code, reading files, writing to files, and submitting pull requests. Once the webhook trigger is hit the agent will start by using the GitHub API to fetch issue details from the posted ticket. It will next use the running MCP server to checkout or clone the indicated code. As this is happening all actions will be streamed to CloudWatch and subsequently stored in S3 for future reference. The credentials and access tokens specifically for the GitHub API calls and MCP permissions will be stored and made accessible through AWS Secrets Manager. Once the LLM is prompted with the issue and relevant code it will write up a code change which will be applied using an MCP tool that calls the GitPython function apply_llm_changes(). After this process is complete the diff will be committed, pushed and a pull request will be submitted.

Debugging Plan:
	For debugging and validation I will focus on both the system’s reliability and correctness of actions. During early testing I will operate the MCP server by separately testing each tool call individually before allowing the LLM to choose between them. I will also be implementing explicit logging to CloudWatch in order to trace the source of errors and faults. This way I can determine the source of errors whether it be the network calls, authentication, message routing, etc. For the functional testing of the code produced by the LLM I will use a sandbox GitHub repository, either a fork of an existing open source project or something like a simple react website. Additionally, all runtime errors will be captured by CloudWatch and stored in an S3 bucket for inspection.
  

Necessary Cloud Services: EC2, S3, CloudWatch, Secrets Manager, IAM.
Is the proposed project interesting to you or does it seem a joyless effort? Explain why or why not.

Yes, this project is interesting because it is combining automation, cloud deployment and intelligent agent workflows. 


Do you believe this project idea will meet the eventual project requirements (use of different cloud technologies)? If not, explain your concern.

Yes, it uses 5 AWS cloud technologies(EC2, S3, CloudWatch, Secrets Manager, IAM) and relates topics of compute, storage, monitoring, and security. 

Do you think the project is within scope for the class? Is it too ambitious? Too conservative?

Yes, my only concern is that it could be marked as too ambitious especially for one person but I feel confident that it is within scope especially with the help of pre-existing libraries like GitPython. Since there is already code developed to approach similar problems most of my development time will be spent on constructing the infrastructure to run it autonomously in the cloud.


Sources:
https://gitpython.readthedocs.io/en/stable/
https://www.anthropic.com/news/model-context-protocol
https://medium.com/the-internal-startup/how-to-draw-useful-technical-architecture-diagrams-2d20c9fda90d

