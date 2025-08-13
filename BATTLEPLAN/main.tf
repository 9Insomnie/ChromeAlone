terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
  required_version = ">= 1.2.0"
}

provider "aws" {
  region = var.aws_region
}

# Random ID for unique resource names
resource "random_id" "deployment" {
  byte_length = 4
}

# Data source to find the latest Amazon Linux 2023 AMI
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Security Group
resource "aws_security_group" "relay_sg" {
  name        = "relay-security-group-${random_id.deployment.hex}"
  description = "Security group for relay server"

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.office_ip_range]
    description = "SSH access from office"
  }

  ingress {
    from_port   = 1080
    to_port     = 1181
    protocol    = "tcp"
    cidr_blocks = [var.office_ip_range]
    description = "SOCKS proxy access from office"
  }

  ingress {
    from_port   = 8080
    to_port     = 8080
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "WebSocket access for agents"
  }

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS access for WebSocket over TLS"
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTP for LetsEncrypt validation"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  tags = {
    Name = "relay-sg"
  }
}

# EC2 Instance
resource "aws_instance" "relay_server" {
  ami           = var.ami_id != "" ? var.ami_id : data.aws_ami.amazon_linux.id
  instance_type = var.instance_type

  vpc_security_group_ids      = [aws_security_group.relay_sg.id]
  key_name                    = var.key_name
  associate_public_ip_address = true

  root_block_device {
    volume_size = 30
    volume_type = "gp3"
    encrypted   = true
  }

  user_data_base64 = base64gzip(templatefile("${path.module}/files/setup.sh", {
    relay_token = var.relay_token
    proxy_user  = var.proxy_user
    proxy_pass  = var.proxy_pass
    server_js   = file("${path.module}/files/server.js")
    domain_name = var.domain_name
  }))

  user_data_replace_on_change = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = {
    Name = "relay-server"
  }
}

# Elastic IP (only create if not using existing one)
resource "aws_eip" "relay_ip" {
  count = var.existing_eip_allocation_id == "" ? 1 : 0
  tags = {
    Name = "relay-eip"
  }
}

# Data source for existing EIP (if provided)
data "aws_eip" "existing" {
  count = var.existing_eip_allocation_id != "" ? 1 : 0
  id    = var.existing_eip_allocation_id
}

resource "aws_eip_association" "relay_eip_assoc" {
  instance_id   = aws_instance.relay_server.id
  allocation_id = var.existing_eip_allocation_id != "" ? data.aws_eip.existing[0].id : aws_eip.relay_ip[0].id
}

# Get the hosted zone ID if domain is provided
data "aws_route53_zone" "selected" {
  count        = var.domain_name != "" ? 1 : 0
  name         = regex(".[^.]+.[^.]+$", var.domain_name) # Get parent domain
  private_zone = false
}

# Create DNS record if domain is provided
resource "aws_route53_record" "relay" {
  count   = var.domain_name != "" ? 1 : 0
  zone_id = data.aws_route53_zone.selected[0].zone_id
  name    = var.domain_name
  type    = "A"
  ttl     = "300"
  records = [var.existing_eip_allocation_id != "" ? data.aws_eip.existing[0].public_ip : aws_eip.relay_ip[0].public_ip]
}