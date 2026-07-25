param(
    [int]$MinHistory = 104,
    [int]$RidgeMinTrain = 156,
    [double]$RidgeAlpha = 8.0
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    throw "Python was not found on PATH. Install Python 3.11 or newer and rerun."
}

& $Python.Source -m pip install --upgrade numpy pandas
& $Python.Source -m py_compile analysis/cot_extended_predictivity.py
& $Python.Source analysis/cot_extended_predictivity.py `
    --min-history $MinHistory `
    --ridge-min-train $RidgeMinTrain `
    --ridge-alpha $RidgeAlpha

Write-Host ""
Write-Host "Extended backtest completed."
Write-Host "Results: analysis/cot_extended_predictivity_output/"
