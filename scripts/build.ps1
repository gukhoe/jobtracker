$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
& .\.venv\Scripts\python.exe -m unittest discover -s tests -v
if ($LASTEXITCODE) { throw 'Tests failed' }
& .\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name JobTracker --exclude-module setuptools --exclude-module pkg_resources --collect-all tzdata --collect-all pypdf --add-data 'LICENSE;.' --add-data 'THIRD_PARTY_NOTICES.txt;.' --add-data 'licenses;licenses' main.py
if ($LASTEXITCODE) { throw 'Build failed' }
Get-FileHash .\dist\JobTracker.exe -Algorithm SHA256 | Format-List
