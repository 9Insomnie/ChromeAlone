#!/usr/bin/env python3
r"""
Chrome Extension Sideloader Builder

This script creates a self-contained PowerShell script that embeds extension content
and optionally a native messaging host, then deploys them to the specified location.

Usage:
    python build_sideloader.py <extension_folder> <install_path>

Example:
    python build_sideloader.py ./myextension "%LOCALAPPDATA%\Google\com.chrome.alone"
"""

import os
import sys
import zipfile
import base64
import argparse
from pathlib import Path
from io import BytesIO


def zip_folder(folder_path):
    """Create a ZIP file from a folder and return it as bytes."""
    folder_path = Path(folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        raise ValueError(f"Extension folder does not exist: {folder_path}")
    
    zip_data = BytesIO()
    
    with zipfile.ZipFile(zip_data, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = Path(root) / file
                arc_name = file_path.relative_to(folder_path)
                zipf.write(file_path, arc_name)
    
    return zip_data.getvalue()


def read_file_as_base64(file_path):
    """Read a file and return its base64 encoded content."""
    file_path = Path(file_path)
    if not file_path.exists():
        raise ValueError(f"File does not exist: {file_path}")
    
    with open(file_path, 'rb') as f:
        content = f.read()
    
    return base64.b64encode(content).decode('utf-8')


def create_extraction_functions(extension_base64):
    """Create the PowerShell extraction functions."""
    
    extract_extension_func = f'''
function Extract-EmbeddedExtension {{
    param([string]$ExtensionPath)
    
    Write-Host "Extracting embedded extension to: $ExtensionPath" -ForegroundColor Cyan
    
    # Create directory if it doesn't exist, or clear existing content
    if (Test-Path $ExtensionPath) {{
        Write-Host "Clearing existing extension directory..." -ForegroundColor Yellow
        Remove-Item $ExtensionPath -Recurse -Force
    }}
    New-Item -ItemType Directory -Path $ExtensionPath -Force | Out-Null
    
    # Decode and extract the embedded extension
    $extensionZipBase64 = "{extension_base64}"
    $extensionZipBytes = [System.Convert]::FromBase64String($extensionZipBase64)
    
    # Create temporary ZIP file
    $tempZipPath = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllBytes($tempZipPath, $extensionZipBytes)
    
    try {{
        # Extract ZIP contents
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($tempZipPath, $ExtensionPath)
        Write-Host "Extension extracted successfully" -ForegroundColor Green
    }}
    finally {{
        # Clean up temp file
        if (Test-Path $tempZipPath) {{
            Remove-Item $tempZipPath -Force
        }}
    }}
}}
'''
        
    return extract_extension_func


def read_template_script():
    """Read the template PowerShell script."""
    script_path = Path(__file__).parent / "ChromeExtensionSideloader.ps1"
    with open(script_path, 'r', encoding='utf-8') as f:
        return f.read()


def build_sideloader_script(extension_folder, install_path, output_path=None):
    """Build the complete sideloader script."""
    
    print(f"Building sideloader script...")
    print(f"  Extension folder: {extension_folder}")
    print(f"  Install path: {install_path}")
    
    # Create ZIP of extension folder
    print("Creating extension ZIP...")
    extension_zip_bytes = zip_folder(extension_folder)
    extension_base64 = base64.b64encode(extension_zip_bytes).decode('utf-8')
    
    # Read template script
    print("Reading template script...")
    template_script = read_template_script()
    
    # Create extraction functions
    print("Creating extraction functions...")
    extraction_functions = create_extraction_functions(extension_base64)
    
    # Replace placeholder functions in template
    script_content = template_script.replace(
        '# These functions will be replaced by the Python builder with actual extraction logic\n'
        'function Extract-EmbeddedExtension {\n'
        '    param([string]$ExtensionPath)\n'
        '    # This will be replaced by the Python builder\n'
        '    throw "Extract-EmbeddedExtension function not implemented - this should be replaced by the Python builder"\n'
        '}\n\n',
        extraction_functions
    )
    
    # Set default parameters
    script_content = script_content.replace(
        '[string]$ExtensionInstallDir = "%LOCALAPPDATA%\\Google\\Chrome\\User Data\\Default\\Extensions\\myextension"',
        f'[string]$ExtensionInstallDir = "{install_path}"'
    )
    
    # Write output
    if output_path:
        output_file = Path(output_path)
    else:
        extension_name = Path(extension_folder).name
        output_file = Path(f"{extension_name}_sideloader.ps1")
    
    print(f"Writing output to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(script_content)
    
    print(f"✅ Sideloader script created successfully: {output_file}")
    print(f"📦 Extension size: {len(extension_zip_bytes):,} bytes")
    
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description="Build a Chrome Extension Sideloader PowerShell script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "extension_folder",
        help="Path to the extension folder to deploy"
    )
    
    parser.add_argument(
        "install_path",
        help="Installation path for the extension (can include environment variables like %%LOCALAPPDATA%%)"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: <extension_name>_sideloader.ps1)"
    )
    
    args = parser.parse_args()
    
    try:
        output_file = build_sideloader_script(
            args.extension_folder,
            args.install_path,
            args.output
        )
        
        print(f"\n🎉 Build completed successfully!")
        print(f"📄 Generated: {output_file}")
        print(f"\nTo deploy the extension, run:")
        print(f"  powershell -ExecutionPolicy Bypass -File {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main() 