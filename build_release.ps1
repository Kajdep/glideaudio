$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$marketingVersion = "0.1.0"
$productName = "GlideAudio"

Remove-Item ".\\build", ".\\dist", ".\\release" -Recurse -Force -ErrorAction SilentlyContinue

python -m PyInstaller --noconfirm --clean .\glideaudio.spec

$releaseRoot = Join-Path $root "release"
$zipRoot = Join-Path $releaseRoot "win64"
New-Item -ItemType Directory -Force -Path $zipRoot | Out-Null

$exePath = Join-Path $root "dist\\$productName.exe"
if (-not (Test-Path $exePath)) {
    throw "Expected built executable at $exePath"
}

Copy-Item $exePath $zipRoot

foreach ($optionalFile in @("README.md", "PRODUCT-BRIEF.md", "PRIVACY_POLICY.md")) {
    $path = Join-Path $root $optionalFile
    if (Test-Path $path) {
        Copy-Item $path $zipRoot
    }
}

$ffmpegBin = Join-Path $root "ffmpeg\\bin"
if (Test-Path $ffmpegBin) {
    $targetFfmpeg = Join-Path $zipRoot "ffmpeg\\bin"
    New-Item -ItemType Directory -Force -Path $targetFfmpeg | Out-Null
    foreach ($filename in @("ffmpeg.exe", "ffprobe.exe")) {
        $source = Join-Path $ffmpegBin $filename
        if (Test-Path $source) {
            Copy-Item $source $targetFfmpeg
        }
    }
}

$zipPath = Join-Path $releaseRoot "$productName-$marketingVersion-win64.zip"
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $zipRoot "*") -DestinationPath $zipPath

Write-Host ""
Write-Host "Release artifacts created:"
Write-Host "  exe folder: $zipRoot"
Write-Host "  zip:        $zipPath"
