param([Parameter(Mandatory=$true)][string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
$projectDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location -LiteralPath $projectDir
try {
    & $PythonExecutable -m PyInstaller --noconfirm --onefile --windowed --name Tutor-AI-0.4.0 --add-data "$projectDir\ui;ui" --specpath "$projectDir\build" --workpath "$projectDir\build\pyinstaller-040" --distpath "$projectDir\dist" main.py
    if ($LASTEXITCODE -ne 0) { throw 'Portable build failed' }
    Get-FileHash -LiteralPath (Join-Path $projectDir 'dist\Tutor-AI-0.4.0.exe') -Algorithm SHA256
} finally { Pop-Location }
