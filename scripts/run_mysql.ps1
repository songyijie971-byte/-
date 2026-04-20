param(
  [string]$Host = "127.0.0.1",
  [int]$Port = 3306,
  [string]$User = "root",
  [string]$Password = "",
  [string]$Database = "classroom_demo",
  [string]$Charset = "utf8mb4"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

if (-not $env:DATABASE_URL) {
  $env:MYSQL_HOST = $Host
  $env:MYSQL_PORT = "$Port"
  $env:MYSQL_USER = $User
  $env:MYSQL_PASSWORD = $Password
  $env:MYSQL_DATABASE = $Database
  $env:MYSQL_CHARSET = $Charset
}

python app.py

