param()

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[launcher] $Message"
}

function Get-RunningProcess {
    param([int]$Id)

    if ($Id -le 0) {
        return $null
    }

    try {
        return Get-Process -Id $Id -ErrorAction Stop
    } catch {
        return $null
    }
}

function Get-ListeningProcessId {
    param([int]$Port)

    try {
        $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
            Select-Object -First 1
        if ($connection) {
            return [int]$connection.OwningProcess
        }
    } catch {
    }

    $lines = netstat -ano -p tcp | Select-String "LISTENING"
    foreach ($line in $lines) {
        $parts = ($line.Line.Trim() -split "\s+")
        if ($parts.Count -ge 5 -and $parts[1].EndsWith(":$Port")) {
            return [int]$parts[4]
        }
    }

    return 0
}

$projectRoot = Split-Path -Parent $PSCommandPath
$statePath = Join-Path $projectRoot ".s1dl\web-ui-state.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Info "No tracked UI process was found."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-RunningProcess -Id ([int]$state.pid)

if ($process) {
    Write-Info "Stopping UI process $($process.Id)"
    Stop-Process -Id $process.Id -Force
} else {
    $listenerProcessId = 0
    if ($state.port) {
        $listenerProcessId = Get-ListeningProcessId -Port ([int]$state.port)
    }
    if ($listenerProcessId -gt 0) {
        Write-Info "Stopping listener process $listenerProcessId"
        Stop-Process -Id $listenerProcessId -Force
    } else {
        Write-Info "Tracked process is not running."
    }
}

Remove-Item -LiteralPath $statePath -Force
Write-Info "Done."
