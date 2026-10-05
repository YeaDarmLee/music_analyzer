param([string]$InputWav)
$ErrorActionPreference = "Stop"
$projectPath = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) { throw "Run scripts/bootstrap.ps1 first" }
$smokeArguments = @("-m", "music_analyzer.cli", "smoke")
if ($InputWav) { $smokeArguments += @("--input", $InputWav) }
& $venvPython @smokeArguments
if ($LASTEXITCODE -ne 0) { throw "Smoke run failed; see data/separation/smoke/<run>/status.json" }
