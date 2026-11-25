# Run in PowerShell from any directory. Does not change execution policy or install tools.
param([int]$Frames = 240, [switch]$AllowSoftware, [switch]$NoBuild)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Python = Get-Command py -ErrorAction SilentlyContinue
$Prefix = @('-3')
if (-not $Python) { $Python = Get-Command python -ErrorAction Stop; $Prefix = @() }
$Arguments = @((Join-Path $PSScriptRoot 'validate_runtime.py'), '--modes', 'gpu', 'hybrid', '--capture', '--frames', "$Frames")
if (-not $NoBuild) { $Arguments += '--build' }
if ($AllowSoftware) { $Arguments += '--allow-software' }
& $Python.Source @Prefix @Arguments
$Result = $LASTEXITCODE
$Reports = Join-Path $Root 'reports/local/gpu-hybrid'
if (Test-Path $Reports) {
    $Archive = Join-Path $Root 'reports/gpu-hybrid-validation.zip'
    Compress-Archive -Path (Join-Path $Reports '*') -DestinationPath $Archive -Force
    Write-Host "Evidence archive: $Archive"
}
exit $Result
