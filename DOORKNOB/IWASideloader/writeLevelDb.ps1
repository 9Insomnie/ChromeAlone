function Initialize-CRC32CTable {
    $polynomial = [uint32]::Parse("82F63B78", [System.Globalization.NumberStyles]::HexNumber)
    $table = [uint32[]]::new(256)

    for ($i = 0; $i -lt 256; $i++) {
        $crc = [uint32]$i
        for ($j = 0; $j -lt 8; $j++) {
            if (($crc -band 1) -eq 1) {
                $shifted = [uint32]($crc -shr 1)
                $crc = DoMath -Value1 $shifted -Value2 $polynomial
            } else {
                $crc = [uint32]($crc -shr 1)
            }
        }
        $table[$i] = $crc
    }
    return $table
}

function DoMath {
    param (
        [Parameter(Mandatory=$true)]
        [uint32]$Value1,
        [Parameter(Mandatory=$true)]
        [uint32]$Value2
    )
    
    $hex1 = [Convert]::ToString($Value1, 16).PadLeft(8, '0')
    $hex2 = [Convert]::ToString($Value2, 16).PadLeft(8, '0')
    $resultHex = ""
    
    for ($i = 0; $i -lt 8; $i++) {
        $digit1 = [Convert]::ToInt32($hex1[$i].ToString(), 16)
        $digit2 = [Convert]::ToInt32($hex2[$i].ToString(), 16)
        
        $xDigit = $xTable[$digit1, $digit2]
        $resultHex += [Convert]::ToString($xDigit, 16)
    }
    
    return [Convert]::ToUInt32($resultHex, 16)
}

$script:xTable = New-Object 'int[,]' 16,16
for ($i = 0; $i -lt 16; $i++) {
    for ($j = 0; $j -lt 16; $j++) {
        $and = $i -band $j
        $x = $i + $j - 2 * $and
        $script:xTable[$i, $j] = $x
    }
}

function Get-CRC32C {
    param (
        [Parameter(Mandatory=$true)]
        [byte[]]$Data
    )

    $table = Initialize-CRC32CTable
    $crc = [uint32]::Parse("FFFFFFFF", [System.Globalization.NumberStyles]::HexNumber)

    foreach ($byte in $Data) {
        # Safely convert byte to uint32 before operations
        [uint32]$byteValue = [uint32]$byte
        $temp = DoMath -Value1 $crc -Value2 $byteValue
        $index = [uint32]($temp -band 0xFF)
        
        $shifted = [uint32]($crc -shr 8)
        $crc = DoMath -Value1 $table[$index] -Value2 $shifted
        $crc = [uint32]($crc -band 0xFFFFFFFF)
    }

    $crc = DoMath -Value1 $crc -Value2 ([uint32]::Parse("FFFFFFFF", [System.Globalization.NumberStyles]::HexNumber))
    return $crc
}

function ConvertFrom-HexString {
    param (
        [Parameter(Mandatory=$true)]
        [string]$HexString
    )
    
    # Clean the hex string - remove any whitespace or invalid characters
    $HexString = $HexString.Replace(" ", "").Trim()
    
    # Validate hex string
    if ($HexString.Length % 2 -ne 0) {
        throw "Invalid hex string length. Must be even number of characters."
    }
    
    if (-not ($HexString -match '^[0-9A-Fa-f]+$')) {
        throw "Invalid hex string. Contains non-hex characters."
    }
    
    $bytes = [byte[]]::new($HexString.Length / 2)
    for($i=0; $i -lt $HexString.Length; $i+=2) {
        $hexByte = $HexString.Substring($i, 2)
        try {
            $bytes[$i/2] = [convert]::ToByte($hexByte, 16)
        }
        catch {
            throw "Failed to convert hex byte '$hexByte' at position $i : $_"
        }
    }
    return $bytes
}

function Add-UInt32 {
    param(
        [Parameter(Mandatory=$true)]
        [uint32]$A,
        [Parameter(Mandatory=$true)]
        [uint32]$B
    )
    return [uint32](($A + $B) -band [uint32]::MaxValue)
}

function Mask-CRC32C {
    param (
        [Parameter(Mandatory=$true)]
        [uint32]$CRC
    )
    
    $K_MASK_DELTA = [uint32]::Parse("A282EAD8", [System.Globalization.NumberStyles]::HexNumber)
    
    $rightShift = [uint32]($CRC -shr 15)
    $leftShift = [uint32]($CRC -shl 17)
    [uint32]$rotated = $rightShift -bor $leftShift
    
    $masked = Add-UInt32 -A $rotated -B $K_MASK_DELTA
    
    return $masked
}

function ConvertTo-LittleEndianHex {
    param (
        [Parameter(Mandatory=$true)]
        [uint32]$Value
    )
    
    $bytes = [BitConverter]::GetBytes($Value)
    $hexString = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ''
    return $hexString
}

function Calc-LevelDB-Hash {
    param (
        [Parameter(Mandatory=$true)]
        [string]$Data
    )

    $dataBytes = ConvertFrom-HexString -HexString $Data
    $crc32cHash = Get-CRC32C -Data $dataBytes
    $maskedCRC32C = Mask-CRC32C -CRC $crc32cHash
    $maskedCRC32CHex = ConvertTo-LittleEndianHex -Value $maskedCRC32C
    return $maskedCRC32CHex
}

function Convert-ToVarInt32 {
    param (
        [Parameter(Mandatory=$true)]
        [int]$Value
    )
    
    $bytes = New-Object System.Collections.ArrayList
    
    do {
        $byte = $Value -band 0x7F
        $Value = $Value -shr 7
        
        if ($Value -ne 0) {
            $byte = $byte -bor 0x80
        }
        
        $bytes.Add([byte]$byte) > $null
    } while ($Value -ne 0)
    
    return ($bytes | ForEach-Object { $_.ToString("x2") }) -join ''
}

function Create-LevelDBEntry {
    param (
        [Parameter(Mandatory=$true)]
        [int]$SequenceNumber,
        [Parameter(Mandatory=$true)]
        [string]$Key,
        [Parameter(Mandatory=$true)]
        [string]$ValueHex
    )
    
    # 1. Create Record Format Entry
    $keyBytes = [System.Text.Encoding]::ASCII.GetBytes($Key)
    $keyLength = Convert-ToVarInt32 -Value $keyBytes.Length
    $valueLength = Convert-ToVarInt32 -Value ($ValueHex.Length / 2)
    
    Write-Debug "Key Length (hex): $keyLength"
    Write-Debug "Key Bytes (hex): $(($keyBytes | ForEach-Object { $_.ToString("x2") }) -join '')"
    Write-Debug "Value Length (hex): $valueLength"
    Write-Debug "Value (hex): $ValueHex"
    
    # Construct record entry parts separately to ensure no spaces are introduced
    $keyHex = ($keyBytes | ForEach-Object { $_.ToString("x2") }) -join ''
    $cleanValueHex = $ValueHex.Replace(" ", "")
    
    $recordEntry = "01" +           # Live record state
                  $keyLength +      # Key length as VarInt32
                  $keyHex +         # Key bytes
                  $valueLength +    # Value length as VarInt32
                  $cleanValueHex    # Value bytes
    
    Write-Debug "Record Entry: $recordEntry"
    
    # 2. Create Batch Header
    $batchHeader = [BitConverter]::GetBytes([int64]$SequenceNumber) +
                  [BitConverter]::GetBytes([int32]1)  # Record count = 1
    $batchHeaderHex = ($batchHeader | ForEach-Object { $_.ToString("x2") }) -join ''
    
    Write-Debug "Batch Header: $batchHeaderHex"
    
    # 3. Calculate LevelDB Hash
    $dataToHash = "01" + $batchHeaderHex + $recordEntry
    Write-Debug "Data to Hash: $dataToHash"
    $hash = Calc-LevelDB-Hash -Data $dataToHash
    Write-Debug "Hash: $hash"
    
    # 4. Calculate content length
    $contentLength = ($batchHeaderHex.Length + $recordEntry.Length) / 2
    $lengthBytes = [BitConverter]::GetBytes([int16]$contentLength)
    $lengthHex = ($lengthBytes | ForEach-Object { $_.ToString("x2") }) -join ''
    Write-Debug "Content Length (hex): $lengthHex"
    
    # 5. Combine all parts
    $finalHex = ($hash +        # CRC32C hash
                $lengthHex +   # Content length
                "01" +         # Block type (FULL)
                $batchHeaderHex +
                $recordEntry).Replace(" ", "")
    
    return $finalHex
}

function Write-LevelDBEntry {
    param (
        [Parameter(Mandatory=$true)]
        [string]$FilePath,
        [Parameter(Mandatory=$true)]
        [int]$SequenceNumber,
        [Parameter(Mandatory=$true)]
        [string]$Key,
        [Parameter(Mandatory=$true)]
        [string]$ValueHex
    )

    # 1. Create the new entry
    $newEntry = Create-LevelDBEntry -SequenceNumber $SequenceNumber -Key $Key -ValueHex $ValueHex
    
    # 2. Convert hex string to bytes
    $entryBytes = ConvertFrom-HexString -HexString $newEntry
    
    # 3. Append bytes to file
    Add-Content -Path $FilePath -Value $entryBytes -Encoding Byte
}

# Create IWA directory structure
function Initialize-IWADirectory {
    param (
        [Parameter(Mandatory=$true)]
        [string]$AppInternalName,
        [Parameter(Mandatory=$true)]
        [string]$SwbmPath
    )
    
    $userDataDir = Join-Path $env:LOCALAPPDATA $env:APP_NAME
    $iwaDir = Join-Path $userDataDir "Default\iwa\$AppInternalName"
    
    # Create directories if they don't exist
    New-Item -ItemType Directory -Force -Path $iwaDir | Out-Null
    
    # Copy SWBM file
    Copy-Item -Path $SwbmPath -Destination (Join-Path $iwaDir "main.swbn") -Force
}

function Get-LevelDBLogFilePath {
    $userDataDir = Join-Path $env:LOCALAPPDATA $env:APP_NAME
    $syncDataDir = Join-Path $userDataDir "Default" 
    $syncDataDir = Join-Path $syncDataDir "Sync Data" 
    $syncDataLevelDBDir = Join-Path $syncDataDir "LevelDB"
    $logFiles = Get-ChildItem -Path $syncDataLevelDBDir -Filter "*.log"
    $logFile = $logFiles | Sort-Object { [int]($_.Name -replace '[^0-9]', '') } | Select-Object -Last 1
    return Join-Path $syncDataLevelDBDir $logFile.Name
}
