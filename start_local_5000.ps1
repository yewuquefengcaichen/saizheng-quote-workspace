$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "Starting Saizheng Quote Workspace on http://127.0.0.1:5000" -ForegroundColor Cyan
python app.py
