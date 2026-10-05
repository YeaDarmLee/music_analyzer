param(
    [Parameter(Mandatory = $true)]
    [string]$InputAudio,
    [ValidateSet("baseline", "memory_safe", "quality", "quality_6s", "quality_ft", "vocal_roformer", "pipeline")]
    [string]$Preset = "pipeline"
)
$ErrorActionPreference = "Stop"
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project venv is missing. Run scripts/bootstrap.ps1 first."
}
if ($Preset -eq "pipeline") {
    & $pythonPath -m music_analyzer.cli separate-pipeline --input $InputAudio
} else {
    & $pythonPath -m music_analyzer.cli separate --input $InputAudio --preset $Preset
}
exit $LASTEXITCODE
