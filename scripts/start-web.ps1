param([ValidateRange(1024,65535)][int]$Port = 8780, [switch]$SkipBuild, [switch]$LocalOnly)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts/bootstrap.ps1 first.' }
if (-not $SkipBuild) {
    Push-Location (Join-Path $projectPath 'frontend')
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
        }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    } finally { Pop-Location }
}
if ($LocalOnly) {
    & $pythonPath -m music_analyzer.web_server --port $Port
} else {
    & $pythonPath -m music_analyzer.web_server --port $Port --host 0.0.0.0 --public-access
}
exit $LASTEXITCODE
