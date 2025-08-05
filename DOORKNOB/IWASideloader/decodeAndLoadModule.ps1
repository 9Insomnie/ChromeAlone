function Decode-And-Load-Module {
    param (
        [Parameter(Mandatory=$true)]
        [string]$assemblyBytesBase64,
        
        [Parameter(Mandatory=$true)]
        [string]$dllPath
    )

    $assemblyBytes = [System.Convert]::FromBase64String($assemblyBytesBase64)

    $encoding = [System.Text.Encoding]::GetEncoding(37)
    $ebcdicString = $encoding.GetString($assemblyBytes)

    $latin1Encoding = [System.Text.Encoding]::GetEncoding(28591)
    $binaryBytes = $latin1Encoding.GetBytes($ebcdicString)
    [System.IO.File]::WriteAllBytes($dllPath, $binaryBytes)

    # Import the module
    Write-Host "Importing module from: $dllPath" -ForegroundColor Cyan
    try {
        Import-Module $dllPath -ErrorAction Stop
        Write-Host "Module imported successfully" -ForegroundColor Green
        return $true
    } catch {
        Write-Error "Failed to import module: $_"
        return $false
    }
}