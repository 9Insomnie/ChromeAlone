variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-2"
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
  description = "AMI ID for relay server (leave empty to use latest Amazon Linux 2023)"
  type        = string
  default     = "" # Will be auto-detected using data source
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
  default     = "" # Optional, deployment will work without a domain
}

variable "existing_eip_allocation_id" {
  description = "Existing Elastic IP allocation ID to use instead of creating a new one"
  type        = string
  default     = "" # If empty, a new EIP will be created
}

