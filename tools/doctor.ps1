#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Show which git hooks are active for this repository and whether its helper tools are in sync.

.DESCRIPTION
  A one-stop status check for when you come back to the repository after a long time:
  which hooks directory git uses, which hooks actually live there, which git aliases
  are configured, and whether README.md still matches the org files on disk.

.EXAMPLE
  pwsh tools/doctor.ps1
#>

$ErrorActionPreference = 'Stop'

$root = git rev-parse --show-toplevel 2>$null
if (-not $root) {
    Write-Error "Not inside a git repository."
    exit 1
}
Set-Location $root

Write-Host "Repository : $root"

# ---- hooks -------------------------------------------------------------
$hooksPath = git config --get core.hooksPath 2>$null
if ($LASTEXITCODE -eq 0 -and $hooksPath) {
    $origin = (git config --show-origin --get core.hooksPath) -replace "`t", '  '
    Write-Host "Hooks path : $hooksPath"
    Write-Host "  source   : $origin"
} else {
    Write-Host "Hooks path : (unset - using the default .git/hooks)"
}

# git resolves core.hooksPath for us, so this is the directory actually in use.
$hooksDir = git rev-parse --git-path hooks
$hooks = @(Get-ChildItem -LiteralPath (Join-Path $root $hooksDir) -File -ErrorAction SilentlyContinue |
           Where-Object { $_.Name -notlike '*.sample' })
if ($hooks.Count -gt 0) {
    Write-Host "Active hooks ($($hooks.Count)):"
    $hooks | ForEach-Object { Write-Host "  - $($_.Name)" }
} else {
    Write-Host "Active hooks: none"
}

# ---- git aliases -------------------------------------------------------
$aliases = @(git config --get-regexp '^alias\.' 2>$null)
if ($LASTEXITCODE -eq 0 -and $aliases.Count -gt 0) {
    Write-Host "Aliases ($($aliases.Count)):"
    $aliases | ForEach-Object { Write-Host "  - $_" }
} else {
    Write-Host "Aliases: none"
}

# ---- repository tools --------------------------------------------------
if (Test-Path (Join-Path $root 'tools/update-readme.py')) {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        Write-Host "update-readme: SKIPPED (python not found)"
    } else {
        $output = & python tools/update-readme.py --check 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "update-readme: README.md is up to date"
        } else {
            Write-Host "update-readme: STALE - run 'python tools/update-readme.py'"
            $output | ForEach-Object { Write-Host "  $_" }
        }
    }
}
