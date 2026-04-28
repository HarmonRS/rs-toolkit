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
    Write-Info "Tracked process is not running."
}

Remove-Item -LiteralPath $statePath -Force
Write-Info "Done."
