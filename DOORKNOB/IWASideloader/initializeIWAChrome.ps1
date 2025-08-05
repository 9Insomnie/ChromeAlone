$appName = $env:APP_NAME
if ($null -eq $appName) {
    $appName = "DOORKNOB"
}

# Check if Chrome is installed by looking in common installation paths
$chromePaths = @(
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
)

$chromePath = $null
foreach ($path in $chromePaths) {
    if (Test-Path $path) {
        $chromePath = $path
        break
    }
}

if ($null -eq $chromePath) {
    Write-Host "Chrome is not installed on this system."
    exit 1
}

#set chrome path environment variable
$env:CHROME_PATH = $chromePath
Write-Host "Chrome found at: $chromePath"

# Create user data directory path
$userDataDir = Join-Path $env:LOCALAPPDATA $env:APP_NAME
$env:USER_DATA_DIR = $userDataDir

$chromeArgs = "--allow-no-sandbox-job --disable-3d-apis --disable-gpu " +
              "--disable-d3d11 --disable-accelerated-layers --disable-accelerated-plugins " +
              "--disable-accelerated-2d-canvas --disable-deadline-scheduling " +
              "--disable-ui-deadline-scheduling --aura-no-shadows " +
              "--user-data-dir=`"$userDataDir`" --profile-directory=Default"
              
# Launch Chrome on hidden desktop and store the result in a variable
$process = Start-ProcessOnDesktop -ProcessPath $chromePath -ProcessArgs $chromeArgs


# Wait 5 seconds
Start-Sleep -Seconds 10

Write-Host "Chrome launched on hidden desktop - PID: $($process.Id)"
$chromePid = $process.Id

if ($chromePid -gt 0) {
    try {
        $process = Get-Process -Id $chromePid -ErrorAction SilentlyContinue
        if ($process) {
            # Kill the Chrome process
            if (!$process.HasExited) {
                $process.Kill()
                Write-Debug "Successfully killed Chrome process with PID: $chromePid"
            }
        }
    }
    catch {
        Write-Debug "Failed to kill Chrome process with PID: $chromePid"
        Write-Debug "Error: $_"
    }
} else {
    Write-Debug "Failed to capture Chrome PID"
    exit 1
}

Write-Host "Waiting 5 seconds for Chrome to fully close and release the file\n"

# Wait a moment for Chrome to fully close and release the file
Start-Sleep -Seconds 5

# Get current time in milliseconds since epoch
$currentTimeMs = [Math]::Floor([decimal](Get-Date(Get-Date).ToUniversalTime()-uformat "%s")) * 1000

# Path to Local State file
$localStatePath = Join-Path $userDataDir "Local State"

# Read and parse the existing JSON file
$jsonContent = Get-Content $localStatePath -Raw | ConvertFrom-Json

# Ensure browser object exists first
if (-not ($jsonContent.PSObject.Properties['browser'])) {
    $jsonContent | Add-Member -Type NoteProperty -Name 'browser' -Value (@{})
}

# Create and set all browser properties at once
$jsonContent.browser = @{
    default_browser_infobar_declined_count = 1
    default_browser_infobar_last_declined_time = $currentTimeMs
    enabled_labs_experiments = @(
        "enable-isolated-web-app-dev-mode@1"
        "enable-isolated-web-apps@1"
    )
    first_run_finished = $true
}

# Write the updated JSON back to the file
$jsonContent | ConvertTo-Json -Depth 10 | Set-Content $localStatePath 