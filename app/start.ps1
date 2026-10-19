param([switch]$Restart)
$ErrorActionPreference = 'Stop'
$amigaRoot = Split-Path $PSScriptRoot -Parent
$amigaPython = Join-Path $amigaRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $amigaPython)) { throw 'Install the project .venv first; see app/README.md.' }
$listeners = @(Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count) {
    $amigaProcesses = @($listeners.OwningProcess | Select-Object -Unique | ForEach-Object {
        Get-CimInstance Win32_Process -Filter "ProcessId=$_"
    })
    foreach ($process in $amigaProcesses) {
        if (-not $process.CommandLine.Contains($amigaPython) -or $process.CommandLine -notmatch '-m app\.run') {
            throw 'Port 8787 is occupied by another application. No process was stopped.'
        }
    }
    if (-not $Restart) { Write-Output 'AMIGA is already running: http://127.0.0.1:8787'; exit 0 }
    $amigaProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId }
}
$null = New-Item -ItemType Directory -Path (Join-Path $amigaRoot '.appdata') -Force
$server = Start-Process -FilePath $amigaPython -ArgumentList '-B','-m','app.run' -WorkingDirectory $amigaRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $amigaRoot '.appdata/server.out.log') -RedirectStandardError (Join-Path $amigaRoot '.appdata/server.err.log') -PassThru
$server.Id | Set-Content (Join-Path $amigaRoot '.appdata/server.pid')
Write-Output 'AMIGA starting at http://127.0.0.1:8787; check /api/v1/health for readiness.'
