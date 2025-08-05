#!/bin/bash
set -e  # Exit on any error

# Log setup progress
exec 1> >(logger -s -t $(basename $0)) 2>&1

echo "Starting relay server setup..."

# Check if we're running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: Must run as root"
    exit 1
fi

yum update -y
echo "System packages updated"
yum install -y nodejs npm git libcap certbot
echo "Node.js and dependencies installed"

# Configure certbot if domain is provided
if [ -n "${domain_name}" ]; then
  echo "Configuring TLS certificate for ${domain_name}..."
  
  # Stop any service that might be using port 80
  systemctl stop nginx 2>/dev/null || true
  
  # Get certificate
  certbot certonly --standalone \
    --non-interactive \
    --agree-tos \
    --email admin@${domain_name} \
    --domains ${domain_name} \
    --preferred-challenges http
  
  # Create certbot group if it doesn't exist
  groupadd -f certbot
  
  # Add ec2-user to certbot group
  usermod -a -G certbot ec2-user
  
  # Set group permissions on Let's Encrypt directory
  chgrp -R certbot /etc/letsencrypt
  chmod -R g+rX /etc/letsencrypt
  
  # Set up auto-renewal
  echo "0 0,12 * * * root python -c 'import random; import time; time.sleep(random.random() * 3600)' && certbot renew -q" | sudo tee -a /etc/crontab > /dev/null
  
  # Create symlinks for Node.js
  mkdir -p /opt/relay-server/certs
  ln -sf /etc/letsencrypt/live/${domain_name}/fullchain.pem /opt/relay-server/certs/cert.pem
  ln -sf /etc/letsencrypt/live/${domain_name}/privkey.pem /opt/relay-server/certs/key.pem
  
  # Set permissions
  chown -R ec2-user:ec2-user /opt/relay-server/certs
fi

# Create app directory
echo "Creating application directory..."
mkdir -p /opt/relay-server
if [ ! -d "/opt/relay-server" ]; then
    echo "Error: Failed to create /opt/relay-server"
    exit 1
fi

cd /opt/relay-server
echo "Current directory: $(pwd)"

# Create environment file
echo "Creating environment file..."
cat << EOF > .env
RELAY_TOKEN=${relay_token}
PROXY_USER=${proxy_user}
PROXY_PASS=${proxy_pass}
PORT=443
NODE_ENV=production
EOF

if [ ! -f ".env" ]; then
    echo "Error: Failed to create .env file"
    exit 1
fi

# Copy server.js from the same directory
echo "Creating server.js..."
cat << 'EOFJS' > server.js
${server_js}
EOFJS

if [ ! -f "server.js" ]; then
    echo "Error: Failed to create server.js"
    exit 1
fi

# Create package.json
echo "Creating package.json..."
cat << 'EOF' > package.json
{
  "name": "relay-server",
  "version": "1.0.0",
  "description": "Secure SOCKS5 relay server",
  "main": "server.js",
  "scripts": {
    "start": "node server.js",
    "test": "echo \"Error: no test specified\" && exit 1"
  }
}
EOF

# Install dependencies
echo "Installing npm dependencies..."
npm install dotenv
npm install express
npm install socksv5
npm install winston
npm install ws
npm install selfsigned

# Allow Node.js to bind to privileged ports
echo "Setting capabilities for Node.js..."
NODEJS_BINARY=$(readlink -f $(which node))
echo "Node.js binary location: $NODEJS_BINARY"
setcap 'cap_net_bind_service=+ep' "$NODEJS_BINARY"

# Verify the capability was set
getcap "$NODEJS_BINARY"

# Set permissions
echo "Setting permissions..."
chown -R ec2-user:ec2-user /opt/relay-server
chmod 600 /opt/relay-server/.env

# Setup log rotation
echo "Configuring log rotation..."
cat << EOF > /etc/logrotate.d/relay-server
/opt/relay-server/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 640 ec2-user ec2-user
    size 10M
}
EOF

# Create systemd service
echo "Creating systemd service..."
cat << EOF > /etc/systemd/system/relay-server.service
[Unit]
Description=Relay Server
After=network.target

[Service]
Type=simple
User=ec2-user
WorkingDirectory=/opt/relay-server
Environment=PATH=/usr/bin:/usr/local/bin
ExecStart=/usr/bin/npm start
Restart=always
StandardOutput=append:/opt/relay-server/relay-server.log
StandardError=append:/opt/relay-server/relay-server-error.log

[Install]
WantedBy=multi-user.target
EOF

# Set permissions and enable service
chmod 644 /etc/systemd/system/relay-server.service
systemctl daemon-reload
systemctl enable relay-server
systemctl start relay-server

# Final checks
if [ ! -f "/opt/relay-server/server.js" ] || [ ! -f "/opt/relay-server/.env" ]; then
    echo "Error: Critical files missing after setup"
    ls -la /opt/relay-server/
    exit 1
fi

echo "Setup complete"