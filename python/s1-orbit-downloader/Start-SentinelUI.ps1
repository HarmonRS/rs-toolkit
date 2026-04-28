param(
    [int[]]$PreferredPorts = @(8011, 8010, 8012, 8013, 8014),
    [switch]$NoBrowser,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host "[launcher] $Message"
}

function Get-UvPath {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command -and $command.Source) {
        return $command.Source
    }

    $fallback = Join-Path $HOME ".local\bin\uv.exe"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }

    throw "uv.exe was not found. Install uv first or add it to PATH."
}

function Test-Health {
    param([int]$Port)

    try {
        $null = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 2
        return $true
    } catch {
        return $false
    }
}

function Get-FreePort {
    param([int[]]$Candidates)

    foreach ($port in $Candidates) {
        $listener = $null
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
            $listener.Start()
            return $port
        } catch {
            continue
        } finally {
            if ($listener) {
                $listener.Stop()
            }
        }
    }

    throw "No free port was found in: $($Candidates -join ', ')"
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

function Load-State {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Save-State {
    param(
        [string]$Path,
        [int]$ProcessId,
        [int]$Port,
        [string]$Url
    )

    $payload = [ordered]@{
        pid        = $ProcessId
        port       = $Port
        url        = $Url
        started_at = (Get-Date).ToString("s")
    }

    $payload | ConvertTo-Json | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Remove-State {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Force
    }
}

$projectRoot = Split-Path -Parent $PSCommandPath
$runtimeDir = Join-Path $projectRoot ".s1dl"
$statePath = Join-Path $runtimeDir "web-ui-state.json"
$stdoutPath = Join-Path $runtimeDir "web-ui.stdout.log"
$stderrPath = Join-Path $runtimeDir "web-ui.stderr.log"

New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$state = Load-State -Path $statePath

if ($state -and -not $ForceRestart) {
    $existingProcess = Get-RunningProcess -Id ([int]$state.pid)
    if ($existingProcess -and (Test-Health -Port ([int]$state.port))) {
        $existingUrl = "http://127.0.0.1:$($state.port)/"
        Write-Info "UI is already running at $existingUrl"
        if (-not $NoBrowser) {
            Start-Process $existingUrl | Out-Null
        }
        exit 0
    }
}

if ($ForceRestart -and $state) {
    $oldProcess = Get-RunningProcess -Id ([int]$state.pid)
    if ($oldProcess) {
        Write-Info "Stopping previous tracked process $($oldProcess.Id)"
        Stop-Process -Id $oldProcess.Id -Force
        Start-Sleep -Seconds 1
    }
    Remove-State -Path $statePath
}

if ($ForceRestart) {
    foreach ($port in $PreferredPorts) {
        if (Test-Health -Port $port) {
            $listenerProcessId = Get-ListeningProcessId -Port $port
            if ($listenerProcessId -gt 0) {
                Write-Info "Stopping existing UI listener $listenerProcessId on port $port"
                Stop-Process -Id $listenerProcessId -Force
                Start-Sleep -Seconds 1
            }
        }
    }
}

foreach ($port in $PreferredPorts) {
    if (Test-Health -Port $port) {
        $url = "http://127.0.0.1:$port/"
        Write-Info "Found an existing running UI at $url"
        Save-State -Path $statePath -ProcessId 0 -Port $port -Url $url
        if (-not $NoBrowser) {
            Start-Process $url | Out-Null
        }
        exit 0
    }
}

$uvPath = Get-UvPath
Write-Info "Using uv at $uvPath"
Write-Info "Syncing project environment"
& $uvPath sync --directory $projectRoot
if ($LASTEXITCODE -ne 0) {
    throw "uv sync failed with exit code $LASTEXITCODE"
}

$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python executable was not found at $pythonPath"
}

$portToUse = Get-FreePort -Candidates $PreferredPorts
$url = "http://127.0.0.1:$portToUse/"

if (Test-Path -LiteralPath $stdoutPath) {
    Remove-Item -LiteralPath $stdoutPath -Force
}
if (Test-Path -LiteralPath $stderrPath) {
    Remove-Item -LiteralPath $stderrPath -Force
}

$arguments = @(
    "-m",
    "uvicorn",
    "sentinel_orbit_downloader.api.app:app",
    "--host",
    "127.0.0.1",
    "--port",
    "$portToUse"
)

Write-Info "Starting UI at $url"
$process = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList $arguments `
    -WorkingDirectory $projectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

$started = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (Test-Health -Port $portToUse) {
        $started = $true
        break
    }
}

if (-not $started) {
    $running = Get-RunningProcess -Id $process.Id
    if ($running) {
        Stop-Process -Id $running.Id -Force
    }

    $stderrTail = ""
    if (Test-Path -LiteralPath $stderrPath) {
        $stderrTail = (Get-Content -LiteralPath $stderrPath -Tail 20) -join [Environment]::NewLine
    }

    if ($stderrTail) {
        throw "UI failed to start.`n$stderrTail"
    }

    throw "UI failed to start."
}

Save-State -Path $statePath -ProcessId $process.Id -Port $portToUse -Url $url
$listenerProcessId = Get-ListeningProcessId -Port $portToUse
if ($listenerProcessId -gt 0) {
    Save-State -Path $statePath -ProcessId $listenerProcessId -Port $portToUse -Url $url
} else {
    Save-State -Path $statePath -ProcessId $process.Id -Port $portToUse -Url $url
}
Write-Info "UI is ready: $url"

if (-not $NoBrowser) {
    Start-Process $url | Out-Null
}
