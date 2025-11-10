provider "aws" {
  region = var.aws_region
}

module "s3" {
  source      = "./modules/s3"
  bucket_name = var.runs_bucket_name
}

module "iam" {
  source          = "./modules/iam"
  runs_bucket_arn = module.s3.bucket_arn
  region          = var.aws_region
}

module "cloudwatch" {
  source           = "./modules/cloudwatch"
  log_group_prefix = "/mcp-agent"
}

module "ec2" {
  source            = "./modules/ec2"
  instance_profile  = module.iam.instance_profile_name
  region            = var.aws_region
  instance_type     = var.instance_type
  name              = var.ec2_name
  allow_ssh_cidr    = var.allow_ssh_cidr
}
