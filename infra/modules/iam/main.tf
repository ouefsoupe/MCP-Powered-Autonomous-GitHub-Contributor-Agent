data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals { type = "Service" identifiers = ["ec2.amazonaws.com"] }
  }
}

resource "aws_iam_role" "ec2_role" {
  name               = "mcp_agent_ec2_role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

# Policy for S3 put, CW logs, SecretsManager read
data "aws_iam_policy_document" "policy" {
  statement {
    actions = ["s3:PutObject", "s3:PutObjectAcl"]
    resources = ["${var.runs_bucket_arn}/*"]
  }
  statement {
    actions   = ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents","logs:DescribeLogStreams"]
    resources = ["*"]
  }
  statement {
    actions   = ["secretsmanager:GetSecretValue","secretsmanager:DescribeSecret"]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "inline" {
  name   = "mcp_agent_ec2_policy"
  policy = data.aws_iam_policy_document.policy.json
}

resource "aws_iam_role_policy_attachment" "attach" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = aws_iam_policy.inline.arn
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "mcp_agent_ec2_profile"
  role = aws_iam_role.ec2_role.name
}

output "instance_profile_name" {
  value = aws_iam_instance_profile.ec2_profile.name
}
