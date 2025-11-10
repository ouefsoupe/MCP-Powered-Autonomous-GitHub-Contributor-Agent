variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "runs_bucket_name" {
  type        = string
  description = "S3 bucket for run artifacts"
  default     = "mcp-agent-runs-dev"
}

variable "instance_type" {
  type        = string
  default     = "t3.small"
}

variable "ec2_name" {
  type        = string
  default     = "mcp-agent-dev"
}

variable "allow_ssh_cidr" {
  type        = string
  description = "Optional: CIDR allowed for SSH (set to your IP/32). Leave empty to disable SSH ingress."
  default     = ""
}
