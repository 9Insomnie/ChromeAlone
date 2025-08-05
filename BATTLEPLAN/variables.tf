variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-west-2"
}

variable "office_ip_range" {
  description = "CIDR block for office IP range"
  type        = string
  validation {
    condition     = can(cidrhost(var.office_ip_range, 0))
    error_message = "The office_ip_range must be a valid CIDR block"
  }
}

variable "ami_id" {
  description = "AMI ID for relay server"
  type        = string
  default     = "ami-0e0bf53f6def86294"  # Amazon Linux 2023 for us-east-2
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.micro"
}

variable "key_name" {
  description = "Name of SSH key pair"
  type        = string
}

variable "relay_token" {
  description = "Authentication token for relay server"
  type        = string
  sensitive   = true
}

variable "proxy_user" {
  description = "Username for SOCKS proxy"
  type        = string
  sensitive   = true
}

variable "proxy_pass" {
  description = "Password for SOCKS proxy"
  type        = string
  sensitive   = true
}

variable "domain_name" {
  description = "Domain name to use for the relay server (e.g., relay.example.com)"
  type        = string
  default     = ""  # Optional, deployment will work without a domain
}

