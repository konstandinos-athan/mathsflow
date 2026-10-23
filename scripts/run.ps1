param([int]$Port = 5000)
$ErrorActionPreference = 'Stop'
$projectPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}
Push-Location $projectPath
try {
    & $pythonPath -B -m database init
    if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed; see the error above.' }
    & $pythonPath -m flask --app app run --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Application exited with an error.' }
} finally { Pop-Location }
