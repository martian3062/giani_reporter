[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Anchor,

    [Parameter(Mandatory = $true)]
    [string]$Voice,

    [Parameter(Mandatory = $true)]
    [string]$Captions,

    [Parameter(Mandatory = $true)]
    [string]$CueSheet,

    [Parameter(Mandatory = $true)]
    [string]$Output,

    [ValidateSet("vertical", "horizontal")]
    [string]$Aspect = "vertical",

    [ValidateSet("synced", "idle")]
    [string]$AnchorMode = "synced",

    [switch]$AllowUnsynced,

    [string]$CommandManifest,

    [switch]$DryRun,

    [switch]$KeepTemp
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "Python 3 was not found on PATH. Install Python 3.10+ from https://python.org, open a new PowerShell window, and retry."
}

$core = Join-Path $PSScriptRoot "assemble_video.py"
if (-not (Test-Path -LiteralPath $core -PathType Leaf)) {
    throw "Assembly core is missing: $core"
}

$cli = @(
    $core,
    "--anchor", $Anchor,
    "--voice", $Voice,
    "--captions", $Captions,
    "--cue-sheet", $CueSheet,
    "--output", $Output,
    "--aspect", $Aspect,
    "--anchor-mode", $AnchorMode
)
if ($CommandManifest) {
    $cli += @("--command-manifest", $CommandManifest)
}
if ($DryRun) {
    $cli += "--dry-run"
}
if ($AllowUnsynced) {
    $cli += "--allow-unsynced"
}
if ($KeepTemp) {
    $cli += "--keep-temp"
}

if ($python.Name -eq "py.exe" -or $python.Name -eq "py") {
    & $python.Source -3 @cli
} else {
    & $python.Source @cli
}
if ($LASTEXITCODE -ne 0) {
    throw "Assembly failed with exit code $LASTEXITCODE. Review the actionable error above."
}
