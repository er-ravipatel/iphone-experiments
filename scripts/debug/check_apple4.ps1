Write-Host "=== Searching for iTunes.exe ===" -ForegroundColor Cyan
$locations = @(
    "$env:ProgramFiles\iTunes\iTunes.exe",
    "$env:ProgramFiles(x86)\iTunes\iTunes.exe",
    "$env:LOCALAPPDATA\Microsoft\WindowsApps\iTunes.exe"
)
$found = $false
foreach ($p in $locations) {
    if (Test-Path $p) {
        Write-Host "iTunes.exe found: $p" -ForegroundColor Green
        $found = $true
    }
}

# Also search WindowsApps folder
$winApps = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WindowsApps" -Filter "iTunes.exe" -ErrorAction SilentlyContinue
foreach ($f in $winApps) {
    Write-Host "iTunes stub: $($f.FullName)" -ForegroundColor Yellow
}

if (-not $found) { Write-Host "iTunes.exe not found in standard paths" -ForegroundColor Red }

Write-Host ""
Write-Host "=== Checking AppleMobileDeviceService registry entry ===" -ForegroundColor Cyan
$reg = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\AppleMobileDeviceService" -ErrorAction SilentlyContinue
if ($reg) {
    Write-Host "Service registered. ImagePath: $($reg.ImagePath)" -ForegroundColor Green
} else {
    Write-Host "AppleMobileDeviceService NOT in registry" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== WindowsApps Apple packages ===" -ForegroundColor Cyan
Get-ChildItem "$env:ProgramFiles\WindowsApps" -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "Apple*" } | Select-Object Name
