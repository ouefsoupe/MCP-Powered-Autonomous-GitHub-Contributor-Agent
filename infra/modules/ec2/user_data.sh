#!/bin/bash
set -euxo pipefail
yum update -y
amazon-linux-extras enable docker
yum install -y docker git
systemctl enable docker
systemctl start docker

# Install docker-compose plugin
curl -SL https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

echo "EC2 ready. Clone your repo to /opt/mcp and run docker compose."
