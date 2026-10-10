# Builds dist\Aion2PetOverlay.exe (single file, no console) and tests it.
# Usage: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) { python -m venv .venv }
.venv\Scripts\python -m pip install -q -r requirements.txt pyinstaller==6.21.0

.venv\Scripts\python selftest.py
if ($LASTEXITCODE -ne 0) { throw "selftest failed (source)" }

.venv\Scripts\pyinstaller --noconfirm --clean --onefile --windowed `
    --name Aion2PetOverlay `
    --icon assets\icon.ico `
    --add-data "data\pets.json;data" `
    --collect-submodules scapy.layers `
    pet_overlay.py
if ($LASTEXITCODE -ne 0) { throw "pyinstaller failed" }

# Run the same checks inside the built exe (bundled data, scapy, Tk).
$run = Start-Process dist\Aion2PetOverlay.exe -ArgumentList "--selftest" -WorkingDirectory dist -Wait -PassThru
if ($run.ExitCode -ne 0) {
    if (Test-Path dist\pet_overlay.log) { Get-Content dist\pet_overlay.log }
    throw "selftest failed (exe), exit code $($run.ExitCode)"
}
Remove-Item dist\pet_overlay.log -ErrorAction SilentlyContinue

# Self-update path: the exe swaps itself for a copy, relaunches, and the copy must pass --selftest.
$t = Join-Path ([IO.Path]::GetTempPath()) ("swaptest-" + [guid]::NewGuid())
New-Item -ItemType Directory $t | Out-Null
Copy-Item dist\Aion2PetOverlay.exe $t
$run = Start-Process "$t\Aion2PetOverlay.exe" -ArgumentList "--selftest-update" -WorkingDirectory $t -Wait -PassThru
if ($run.ExitCode -ne 0) { throw "swap test failed to start, exit code $($run.ExitCode)" }
$deadline = (Get-Date).AddSeconds(90)
while (-not (Select-String -Path "$t\pet_overlay.log" -Pattern "selftest (passed|failed)" -Quiet -ErrorAction SilentlyContinue)) {
    if ((Get-Date) -gt $deadline) { break }
    Start-Sleep 1
}
$log = Get-Content "$t\pet_overlay.log" -ErrorAction SilentlyContinue
$log
if (-not ($log -match "selftest passed") -or -not (Test-Path "$t\Aion2PetOverlay.exe.old")) {
    throw "self-update swap test failed"
}

$hash = (Get-FileHash dist\Aion2PetOverlay.exe -Algorithm SHA256).Hash.ToLower()
"$hash  Aion2PetOverlay.exe" | Set-Content dist\SHA256SUMS.txt -Encoding ascii
Write-Host "OK  $hash  dist\Aion2PetOverlay.exe"
