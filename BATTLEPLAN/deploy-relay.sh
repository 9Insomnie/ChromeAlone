#!/bin/bash
set -e

# Parse command line arguments
DOMAIN_NAME=""
AWS_REGION="us-east-2"  # Default region (matches build.sh default)
while [[ $# -gt 0 ]]; do
  case $1 in
    --domain)
      DOMAIN_NAME="$2"
      shift 2
      ;;
    --region)
      AWS_REGION="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--domain domain.example.com] [--region aws-region]"
      exit 1
      ;;
  esac
done

# Check for AWS CLI and Terraform
if ! command -v aws &> /dev/null; then
    echo "AWS CLI not found. Please install it first."
    exit 1
fi

if ! command -v terraform &> /dev/null; then
    echo "Terraform not found. Please install it first."
    exit 1
fi

# Configure AWS credentials if not already set
if ! aws sts get-caller-identity &> /dev/null; then
    echo "AWS credentials not found. Run aws configure first."
    exit 1
fi

# Create deployment directory
DEPLOY_DIR="../output/relay-deployment"
mkdir -p "$DEPLOY_DIR/files"

# Copy Terraform configuration files
cp main.tf variables.tf outputs.tf "$DEPLOY_DIR/"
cp -r files/* "$DEPLOY_DIR/files/"

cd "$DEPLOY_DIR"

# Create SSH key pair if it doesn't exist
KEY_NAME="relay-proxy-key"
if ! aws ec2 describe-key-pairs --region "$AWS_REGION" --key-names "$KEY_NAME" &> /dev/null; then
    echo "Creating new SSH key pair in region $AWS_REGION..."
    aws ec2 create-key-pair \
        --region "$AWS_REGION" \
        --key-name "$KEY_NAME" \
        --query 'KeyMaterial' \
        --output text > "${KEY_NAME}.pem"
    chmod 400 "${KEY_NAME}.pem"
fi

# Get current IP for "office_ip_range" 
CURRENT_IP=$(curl -s https://checkip.amazonaws.com)
OFFICE_IP_RANGE="${CURRENT_IP}/32"
echo "Detected IP address: $OFFICE_IP_RANGE"
echo "Using AWS region: $AWS_REGION"

# Generate secure random tokens
RELAY_TOKEN=$(openssl rand -hex 32)
PROXY_USER="admin"
PROXY_PASS=$(openssl rand -base64 32)

# Create terraform.tfvars
cat > terraform.tfvars << EOF
aws_region = "${AWS_REGION}"
office_ip_range = "${OFFICE_IP_RANGE}"
key_name = "${KEY_NAME}"
relay_token = "${RELAY_TOKEN}"
proxy_user = "${PROXY_USER}"
proxy_pass = "${PROXY_PASS}"
instance_type = "t3.micro"
domain_name = "${DOMAIN_NAME}"
EOF

# Initialize and apply Terraform
echo "Initializing Terraform..."
terraform init

echo "Validating Terraform configuration..."
terraform validate

echo "Applying Terraform configuration..."
terraform apply -auto-approve

# Save connection details
echo "Saving connection details..."
RELAY_IP=$(terraform output -raw relay_public_ip)

cat > relay-config.txt << EOF
Relay Server Details:
====================
SOCKS5 Proxy: ${RELAY_IP}:1080
Username: ${PROXY_USER}
Password: ${PROXY_PASS}
WebSocket URL: wss://${RELAY_IP}:443
Relay Token: ${RELAY_TOKEN}
SSH Key: ${PWD}/${KEY_NAME}.pem
SSH Command: ssh -i ${KEY_NAME}.pem ec2-user@${RELAY_IP}

Example SOCKS5 Configuration:
============================
Host: ${RELAY_IP}
Info Port: 1080
Port Range: 1081-1181
Username: ${PROXY_USER}
Password: ${PROXY_PASS}

For Datacenter Agent Configuration:
=================================
RELAY_SERVER=wss://${RELAY_IP}:443
RELAY_TOKEN=${RELAY_TOKEN}
EOF

chmod 600 relay-config.txt

echo "Deployment complete! Configuration saved to relay-config.txt"
echo "Allow a few minutes for the server to finish initialization."
echo "To test the connection: ssh -i ${KEY_NAME}.pem ec2-user@${RELAY_IP}"

# Add setup log viewing option
echo -e "\n\nTo view setup logs:"
echo "aws ec2 get-console-output --instance-id $(terraform output -raw relay_instance_id)"
echo "or"
echo "ssh -i ${KEY_NAME}.pem ec2-user@${RELAY_IP} 'sudo cat /var/log/cloud-init-output.log'"