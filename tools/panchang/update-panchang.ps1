param(
    [switch]$RefreshRainmeter,
    [string]$RefreshConfig,
    [ValidateSet('north-indian', 'south-indian')]
    [string]$Region,
    [ValidateSet('amavasya', 'purnima')]
    [string]$MonthStart
)

$ErrorActionPreference = 'Stop'
$toolDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$skinDirectory = Split-Path -Parent (Split-Path -Parent $toolDirectory)
$calculator = Join-Path $toolDirectory 'calculate_panchang.py'
$variablesPath = Join-Path $skinDirectory '@Settings\Variables.inc'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found on PATH. Install Python 3.11+ and retry.'
}

if (-not (Test-Path $variablesPath)) {
    throw "Rainmeter variables file was not found: $variablesPath"
}

function Set-RainmeterVariable {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $lines = @(Get-Content -LiteralPath $variablesPath)
    $pattern = "^$([regex]::Escape($Name))=.*$"
    $updated = $false
    $lines = $lines | ForEach-Object {
        if ($_ -match $pattern) {
            $updated = $true
            "$Name=$Value"
        } else {
            $_
        }
    }
    if (-not $updated) {
        $lines += "$Name=$Value"
    }
    # Rainmeter does not reliably parse a UTF-8 BOM before the [Variables]
    # section header. Write UTF-8 without a BOM so substitutions resolve.
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllLines($variablesPath, $lines, $utf8NoBom)
}

if ($Region) {
    Set-RainmeterVariable -Name 'PANCHANG_REGION' -Value $Region
}
if ($MonthStart) {
    Set-RainmeterVariable -Name 'PANCHANG_MONTH_START' -Value $MonthStart
}

$calculatorArguments = @()
if ($Region) {
    $calculatorArguments += @('--region', $Region)
}
if ($MonthStart) {
    $calculatorArguments += @('--month-start', $MonthStart)
}

& python $calculator @calculatorArguments
if ($LASTEXITCODE -ne 0) {
    throw "Panchang calculation failed with exit code $LASTEXITCODE."
}

$jsonPath = Join-Path $skinDirectory '@Resources\panchang.json'
$includePath = Join-Path $skinDirectory '@Resources\plugins\PanchangData.inc'
if (-not (Test-Path $jsonPath) -or -not (Test-Path $includePath)) {
    throw 'The calculator did not create both the JSON and Rainmeter include outputs.'
}

if ($RefreshRainmeter) {
    $rainmeter = @(
        (Join-Path ${env:ProgramFiles} 'Rainmeter\Rainmeter.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Rainmeter\Rainmeter.exe')
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if ($rainmeter) {
        if ($RefreshConfig) {
            & $rainmeter '!Refresh' $RefreshConfig
        } else {
            & $rainmeter '!RefreshApp'
        }
        if ($LASTEXITCODE -ne 0) {
            throw "Rainmeter refresh failed with exit code $LASTEXITCODE."
        }
    } else {
        Write-Warning 'Rainmeter.exe was not found; refresh the skin manually.'
    }
}

Write-Output "Updated $jsonPath"
Write-Output "Updated $includePath"