$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir
$DistDir = Join-Path $RootDir "dist"

$Python = if ($env:PYTHON) { $env:PYTHON } else { "py" }

Set-Location $RootDir

Write-Host "==> Cleaning dist/"
if (Test-Path $DistDir) {
    Remove-Item $DistDir -Recurse -Force
}
New-Item -ItemType Directory -Path $DistDir | Out-Null

Write-Host "==> Building wheel + source distribution"
& $Python -m build --wheel --sdist --outdir $DistDir
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "==> Building Nuitka executable"
& $Python -m nuitka `
    --onefile `
    --python-flag=-m `
    "--output-dir=$DistDir" `
    "--output-filename=cdpunpack.exe" `
    "$RootDir\cdpunpack"

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==> Build complete:"
Get-ChildItem $DistDir -File | Sort-Object Name