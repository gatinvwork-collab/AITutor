param([Parameter(Mandatory=$true)][string]$PythonExecutable)
$ErrorActionPreference = 'Stop'
$projectDir = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location -LiteralPath $projectDir
try {
    & $PythonExecutable -m PyInstaller --noconfirm --onefile --windowed --name AI-Tutor-0.3.2 --add-data "$projectDir\ui;ui" --specpath "$projectDir\build" --workpath "$projectDir\build\pyinstaller-032" --distpath "$projectDir\dist" main.py
    if ($LASTEXITCODE -ne 0) { throw 'Portable build failed' }
    Get-FileHash -LiteralPath (Join-Path $projectDir 'dist\AI-Tutor-0.3.2.exe') -Algorithm SHA256
} finally { Pop-Location }
