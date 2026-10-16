# HydroSim EXPO stand (FTI) setup — run ONCE, while the PC still has internet,
# AFTER windows\install.ps1:
#     powershell -ExecutionPolicy Bypass -File windows\install-fti.ps1
#
# It writes autopilot\autopilot.ini (token + a fresh admin code), finds
# Assetto Corsa and the Radical, downloads the fonts for offline use and puts
# start-fti.bat in the Startup folder.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
Write-Host "== HydroSim expo stand setup ==" -ForegroundColor Cyan

if (-not (Test-Path ".venv\Scripts\python.exe") -or -not (Test-Path ".env")) {
    Write-Error "Run windows\install.ps1 first."
}

function Write-Utf8NoBom($Path, $Content) {
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText("$PWD\$Path", $Content, $enc)
}

# --- dependencies (pull a fresh requirements set while we have internet) -----
& .venv\Scripts\python -m pip install -r requirements.txt --quiet

# --- Assetto Corsa -----------------------------------------------------------
$acDir = $null
$steam = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
$candidates = @()
if ($steam) {
    $candidates += (Join-Path $steam "steamapps\common\assettocorsa")
    $vdf = Join-Path $steam "steamapps\libraryfolders.vdf"
    if (Test-Path $vdf) {
        Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"' | ForEach-Object {
            $candidates += (Join-Path ($_.Matches[0].Groups[1].Value -replace '\\\\', '\') "steamapps\common\assettocorsa")
        }
    }
}
$candidates += "C:\Program Files (x86)\Steam\steamapps\common\assettocorsa"
foreach ($c in $candidates) { if (Test-Path (Join-Path $c "acs.exe")) { $acDir = $c; break } }
if (-not $acDir) {
    $acDir = Read-Host "Assetto Corsa folder (the one with acs.exe)"
}
Write-Host "Assetto Corsa: $acDir"

$cars = Get-ChildItem (Join-Path $acDir "content\cars") -Directory -ErrorAction SilentlyContinue
$radicals = @($cars | Where-Object { $_.Name -like "*radical*" } | ForEach-Object { $_.Name })
if ($radicals.Count -eq 1) {
    $car = $radicals[0]
    Write-Host "Car: $car"
} else {
    if ($radicals.Count -gt 1) { Write-Host "Radical cars found: $($radicals -join ', ')" }
    else { Write-Host "No car folder with 'radical' in its name found." -ForegroundColor Yellow }
    $car = Read-Host "Car folder name to use (under content\cars)"
}

# --- autopilot.ini -----------------------------------------------------------
$envMap = @{}
Get-Content .env | Where-Object { $_ -match "^\s*([A-Z_]+)=(.*)$" } |
    ForEach-Object { $envMap[$Matches[1]] = $Matches[2] }
if (-not (Test-Path "autopilot\autopilot.ini")) {
    $code = "hydro" + (Get-Random -Minimum 1000 -Maximum 9999)
    $ini = (Get-Content -Raw "autopilot\autopilot.example.ini") `
        -replace "token = CHANGE-ME", "token = $($envMap['API_TOKEN'])" `
        -replace "admin_code = CHANGE-ME", "admin_code = $code" `
        -replace "(?m)^install_dir = .*$", "install_dir = $acDir" `
        -replace "(?m)^car =\s*$", "car = $car" `
        -replace "8088", $envMap['PORT']
    Write-Utf8NoBom "autopilot\autopilot.ini" $ini
    Write-Host ""
    Write-Host "  ADMIN CODE: $code" -ForegroundColor Yellow
    Write-Host "  Type it on the keyboard at any time to release the keyboard for 10 minutes."
    Write-Host "  (Also in autopilot\autopilot.ini - write it down, the stand is locked without it.)"
    Write-Host ""
} else {
    Write-Host "autopilot\autopilot.ini already exists - leaving it untouched."
}

# --- the expo event (active, Radical @ Spa, track limits ignored) -----------
& .venv\Scripts\python -m flask --app app create-expo --name "FTI 2026" --slug fti-2026 --car $car --track spa --min-lap 100
if ($LASTEXITCODE -ne 0) { Write-Warning "Could not create the expo event - create it in /admin (kind 'expo')." }

# --- fonts for offline use ---------------------------------------------------
$fonts = @{
    "montserrat-latin-wght-normal.woff2"     = "https://cdn.jsdelivr.net/npm/@fontsource-variable/montserrat@5/files/montserrat-latin-wght-normal.woff2"
    "montserrat-latin-ext-wght-normal.woff2" = "https://cdn.jsdelivr.net/npm/@fontsource-variable/montserrat@5/files/montserrat-latin-ext-wght-normal.woff2"
    "montserrat-latin-wght-italic.woff2"     = "https://cdn.jsdelivr.net/npm/@fontsource-variable/montserrat@5/files/montserrat-latin-wght-italic.woff2"
    "jetbrains-mono-latin-wght-normal.woff2" = "https://cdn.jsdelivr.net/npm/@fontsource-variable/jetbrains-mono@5/files/jetbrains-mono-latin-wght-normal.woff2"
}
foreach ($f in $fonts.Keys) {
    $dest = "static\fonts\$f"
    if (-not (Test-Path $dest)) {
        try { Invoke-WebRequest -Uri $fonts[$f] -OutFile $dest -UseBasicParsing; Write-Host "font: $f" }
        catch { Write-Warning "Could not download $f - the screen falls back to Segoe UI." }
    }
}

# --- autostart ---------------------------------------------------------------
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "HydroSim expo.lnk"
$answer = Read-Host "Start the expo stand automatically at logon? (y/n)"
if ($answer -match "^[yYjJ]") {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($lnk)
    $s.TargetPath = Join-Path $root "windows\start-fti.bat"
    $s.WorkingDirectory = $root
    $s.WindowStyle = 7
    $s.Save()
    Write-Host "Autostart: $lnk"
}

Write-Host ""
Write-Host "Next steps (FTI.md has the full checklist):" -ForegroundColor Cyan
Write-Host "  1. .venv\Scripts\python -m autopilot --learn   -> press the start button on the wheel,"
Write-Host "     put its numbers in autopilot\autopilot.ini [wheel] (or leave empty = any button)"
Write-Host "  2. Steam: log in once, then Steam > Go Offline"
Write-Host "  3. As administrator: windows\lockdown.ps1  (Ctrl+Alt+Del / Win+L / sleep)"
Write-Host "  4. windows\start-fti.bat"
