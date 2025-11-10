variable "instance_profile" { type = string }
variable "region" { type = string }
variable "instance_type" { type = string }
variable "name" { type = string }
variable "allow_ssh_cidr" { type = string }

resource "aws_security_group" "sg" {
  name        = "${var.name}-sg"
  description = "MCP agent SG"
  vpc_id      = data.aws_vpc.default.id

  # Optional SSH ingress
  dynamic "ingress" {
    for_each = length(var.allow_ssh_cidr) > 0 ? [1] : []
    content {
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [var.allow_ssh_cidr]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["137112412989"]
  filter { name = "name" values = ["al2023-ami-*-kernel-6.*-x86_64"] }
}

resource "aws_instance" "mcp" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  iam_instance_profile   = var.instance_profile
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.sg.id]
  user_data              = file("${path.module}/user_data.sh")

  tags = { Name = var.name }
}

output "instance_id" { value = aws_instance.mcp.id }
output "public_ip"   { value = aws_instance.mcp.public_ip }
