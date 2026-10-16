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

function Invoke-UiShutdown {
    param(
        [string]$Url,
        [string]$ShutdownToken
    )

    if ([string]::IsNullOrWhiteSpace($Url) -or [string]::IsNullOrWhiteSpace($ShutdownToken)) {
        return $false
    }

    try {
        $headers = @{
            "X-S1DL-Shutdown-Token" = $ShutdownToken
        }
        $shutdownUrl = $Url.TrimEnd("/") + "/api/shutdown"
        $null = Invoke-RestMethod -Uri $shutdownUrl -Method Post -Headers $headers -TimeoutSec 5 -ErrorAction Stop
        return $true
    } catch {
        return $false
    }
}

function Wait-ForUiShutdown {
    param(
        [int]$ProcessId,
        [int]$Port,
        [int]$TimeoutSeconds = 10
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $running = Get-RunningProcess -Id $ProcessId
        $listenerProcessId = 0
        if ($Port -gt 0) {
            $listenerProcessId = Get-ListeningProcessId -Port $Port
        }
        if (-not $running -and $listenerProcessId -le 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    return $false
}

$projectRoot = Split-Path -Parent $PSCommandPath
$statePath = Join-Path $projectRoot ".s1dl\web-ui-state.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Info "No tracked UI process was found."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$stopped = $false

if ($state.url -and $state.shutdown_token) {
    Write-Info "Requesting UI shutdown via API"
    if (Invoke-UiShutdown -Url $state.url -ShutdownToken $state.shutdown_token) {
        $stopped = Wait-ForUiShutdown -ProcessId ([int]$state.pid) -Port ([int]$state.port)
    }
}

if (-not $stopped) {
    $process = Get-RunningProcess -Id ([int]$state.pid)

    if ($process) {
        Write-Info "Stopping UI process $($process.Id)"
        try {
            Stop-Process -Id $process.Id -Force -ErrorAction Stop
            $stopped = $true
        } catch {
            throw "Failed to stop UI process $($process.Id). It may have been started from an elevated shell. Start or stop it with the same privilege level, or restart it with the updated launcher once so it can use API shutdown. $($_.Exception.Message)"
        }
    } else {
        $listenerProcessId = 0
        if ($state.port) {
            $listenerProcessId = Get-ListeningProcessId -Port ([int]$state.port)
        }
        if ($listenerProcessId -gt 0) {
            Write-Info "Stopping listener process $listenerProcessId"
            try {
                Stop-Process -Id $listenerProcessId -Force -ErrorAction Stop
                $stopped = $true
            } catch {
                throw "Failed to stop UI listener process $listenerProcessId. It may have been started from an elevated shell. Start or stop it with the same privilege level, or restart it with the updated launcher once so it can use API shutdown. $($_.Exception.Message)"
            }
        } else {
            Write-Info "Tracked process is not running."
            $stopped = $true
        }
    }
}

if (-not $stopped) {
    throw "UI shutdown did not complete."
}

Remove-Item -LiteralPath $statePath -Force
Write-Info "Done."
