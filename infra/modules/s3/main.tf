resource "aws_s3_bucket" "runs" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "block" {
  bucket                  = aws_s3_bucket.runs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "bucket_name" { value = aws_s3_bucket.runs.bucket }
output "bucket_arn"  { value = aws_s3_bucket.runs.arn }
