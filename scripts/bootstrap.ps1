param(
    [string]$PythonExecutable = "python"
)
$ErrorActionPreference = "Stop"
$projectPath = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $projectPath ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExecutable -m venv (Join-Path $projectPath ".venv")
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed; pass Python 3.11 or 3.12 with -PythonExecutable" }
}
& $venvPython -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121
if ($LASTEXITCODE -ne 0) { throw "PyTorch installation failed" }
$lockPath = Join-Path $projectPath "separation\requirements\windows-py312-cu121.lock.txt"
$projectPackage = (Join-Path $projectPath "separation") + "[demucs,roformer,test]"
if (Test-Path -LiteralPath $lockPath) {
    & $venvPython -m pip install -r $lockPath --extra-index-url https://download.pytorch.org/whl/cu121
    if ($LASTEXITCODE -ne 0) { throw "Locked dependencies failed" }
    & $venvPython -m pip install --no-deps -e $projectPackage
} else {
    & $venvPython -m pip install -e $projectPackage
}
if ($LASTEXITCODE -ne 0) { throw "Project dependency installation failed" }
& $venvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "Dependency check failed" }
