$dllPath = Join-Path $env:LOCALAPPDATA $env:APP_NAME
$dllPath = Join-Path $dllPath "ProcessHelper.dll"
Import-Module $dllPath

# Launch Chrome app
$chromePath = $env:CHROME_PATH
if (-not $chromePath) {
    # Check multiple possible Chrome installation paths
    $chromePaths = @(
        "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "${env:LocalAppData}\Google\Chrome\Application\chrome.exe"
    )
    
    foreach ($path in $chromePaths) {
        if (Test-Path $path) {
            $chromePath = $path
            break
        }
    }
    
    # Fallback to default if not found
    if (-not $chromePath) {
        $chromePath = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    }
}

$userDataDir = $env:USER_DATA_DIR
if (-not $userDataDir) {{
    $userDataDir = Join-Path $env:LOCALAPPDATA $env:APP_NAME
}}

$chromeArgs = "--allow-no-sandbox-job --disable-3d-apis --disable-gpu " +
              "--disable-d3d11 --disable-accelerated-layers --disable-accelerated-plugins " +
              "--disable-accelerated-2d-canvas --disable-deadline-scheduling " +
              "--disable-ui-deadline-scheduling --aura-no-shadows " +
              "--user-data-dir=`"$userDataDir`" --profile-directory=Default"

$chromeAppArgs = "$chromeArgs --app-id=$env:IWA_APP_ID"

# Launch Chrome app on hidden desktop - we don't care about the PID output
Start-ProcessOnDesktop -ProcessPath $chromePath -ProcessArgs $chromeAppArgs -DesktopName $sharedDesktopName 
Start-ProcessOnDesktop -ProcessPath $chromePath -ProcessArgs $chromeArgs -DesktopName $sharedDesktopName