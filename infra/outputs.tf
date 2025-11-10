output "runs_bucket_name" {
  value = module.s3.bucket_name
}

output "instance_id" {
  value = module.ec2.instance_id
}

output "public_ip" {
  value = module.ec2.public_ip
}
