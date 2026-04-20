param(
  [string]$DatabaseUrl = "sqlite:///classroom_demo.db"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:DATABASE_URL = $DatabaseUrl

python app.py

