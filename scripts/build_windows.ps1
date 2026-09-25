param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

if (-not $SkipTests) {
    python -m pytest -q tests/test_api_smoke.py tests/xiangqi/ tests/test_final_fixes.py tests/test_desktop_launcher.py
    if ($LASTEXITCODE -ne 0) { throw "Tests failed" }
}

$stockfishUrl = "https://github.com/official-stockfish/Stockfish/releases/download/sf_19/stockfish-windows-x86-64-universal.zip"
$stockfishSha256 = "3c8bf1f9ea66a09350a40df4f632288285ac206d99f33ab5842c408fc30b48a7"
$vendorDir = Join-Path $projectRoot "build\stockfish"
New-Item -ItemType Directory -Force -Path $vendorDir | Out-Null
$archive = Join-Path $vendorDir "stockfish-19-upstream.zip"
Invoke-WebRequest -Uri $stockfishUrl -OutFile $archive
$actualSha256 = (Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant()
if ($actualSha256 -ne $stockfishSha256) {
    throw "Stockfish archive checksum mismatch"
}
Expand-Archive -Path $archive -DestinationPath (Join-Path $vendorDir "unpacked") -Force
$engine = Join-Path $vendorDir "unpacked\stockfish\stockfish-windows-x86-64-universal.exe"
if (-not (Test-Path $engine)) { throw "Stockfish executable missing from archive" }
$bundledEngine = Join-Path $vendorDir "stockfish.exe"
Copy-Item $engine $bundledEngine -Force
$license = Join-Path $vendorDir "unpacked\stockfish\Copying.txt"

$buildArgs = @(
    "--noconfirm", "--clean", "--onedir", "--windowed",
    "--name", "ChessCouncil",
    "--collect-submodules", "uvicorn",
    "--hidden-import", "webview.platforms.edgechromium",
    "--hidden-import", "webview.platforms.winforms",
    "--add-data", "frontend;frontend",
    "--add-binary", "$bundledEngine;bin",
    "--add-data", "$license;third_party\stockfish",
    "--add-data", "$archive;third_party\stockfish",
    "desktop/launcher.py"
)
python -m PyInstaller @buildArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

$appDir = Join-Path $projectRoot "dist\ChessCouncil"
Copy-Item "desktop\ChessCouncil.env.example" (Join-Path $appDir "ChessCouncil.env.example")
Copy-Item "desktop\README.md" (Join-Path $appDir "README.txt")

$exe = Join-Path $appDir "ChessCouncil.exe"
$process = Start-Process -FilePath $exe -ArgumentList "--self-test" -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Built application self-test failed. Check %LOCALAPPDATA%\ChessCouncil\desktop.log"
}

$zip = Join-Path $projectRoot "dist\ChessCouncil-Windows.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $appDir "*") -DestinationPath $zip
Write-Host "Built and verified: $zip"
