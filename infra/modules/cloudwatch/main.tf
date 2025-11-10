resource "aws_cloudwatch_log_group" "server" {
  name              = "${var.log_group_prefix}/server"
  retention_in_days = 14
}

resource "aws_cloudwatch_log_group" "agent" {
  name              = "${var.log_group_prefix}/agent"
  retention_in_days = 14
}
