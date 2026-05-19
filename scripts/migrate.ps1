<#
.SYNOPSIS
    Apply Flood AI PostgreSQL migrations from any directory.

.DESCRIPTION
    - Adds PostgreSQL 18 bin to PATH for the current session (so psql / pg_dump are available).
    - cd's into the project root (the directory this script lives in).
    - Delegates to run_migration.py, which uses .env credentials and the
      schema_migrations tracking table so each migration runs at most once.

.PARAMETER File
    Optional path to a single migration file (relative to project root or absolute).
    Omit to apply all pending migrations.

.PARAMETER Status
    Show which migrations are applied / pending / drifted.

.EXAMPLE
    .\migrate.ps1
    .\migrate.ps1 -File "db\migrations\105_decision_l1_7_safety_floor.sql"
    .\migrate.ps1 -Status
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$File,

    [Parameter()]
    [switch]$Status
)

$ErrorActionPreference = 'Stop'

# scripts/ lives one level below the repo root; go up one to anchor everything.
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $ProjectRoot

# Add PostgreSQL 18 bin to PATH for this session
$PgBinCandidates = @(
    'C:\Program Files\PostgreSQL\18\bin',
    'C:\Program Files (x86)\PostgreSQL\18\bin'
)
$PgBin = $PgBinCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($PgBin) {
    if (-not (($env:Path -split ';') -contains $PgBin)) {
        $env:Path = "$PgBin;$env:Path"
    }
    Write-Host "[migrate] PostgreSQL bin on PATH: $PgBin"
} else {
    Write-Warning "[migrate] PostgreSQL 18 bin not found in standard locations. psql may not be available."
}

# Resolve Python
$PythonExe = $null
foreach ($candidate in @('python', 'py')) {
    $found = Get-Command $candidate -ErrorAction SilentlyContinue
    if ($found) { $PythonExe = $found.Source; break }
}
if (-not $PythonExe) {
    Write-Error "[migrate] python is not on PATH. Install Python 3 or activate your venv."
    exit 2
}

# Build args for run_migration.py (now lives under scripts/)
$RunnerArgs = @('scripts\run_migration.py')
if ($Status) {
    $RunnerArgs += '--status'
} elseif ($File) {
    $RunnerArgs += @('--file', $File)
}

Write-Host "[migrate] project root: $ProjectRoot"
Write-Host "[migrate] running: $PythonExe $($RunnerArgs -join ' ')"
Write-Host ''

& $PythonExe @RunnerArgs
$exit = $LASTEXITCODE

Write-Host ''
if ($exit -eq 0) {
    Write-Host "[migrate] SUCCESS" -ForegroundColor Green
} else {
    Write-Host "[migrate] FAILED (exit $exit)" -ForegroundColor Red
}
exit $exit
