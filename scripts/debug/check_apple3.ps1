Write-Host "=== Checking usbmuxd named pipe ===" -ForegroundColor Cyan
$pipe = Get-ChildItem -Path "\\.\pipe\" -ErrorAction SilentlyContinue | Where-Object { $_.Name -like '*usbmux*' -or $_.Name -like '*apple*' -or $_.Name -like '*mux*' }
if ($pipe) { $pipe | Format-Table Name } else { Write-Host "No usbmuxd pipe found" }

Write-Host ""
Write-Host "=== AppleMobileDeviceService alternatives ===" -ForegroundColor Cyan
sc.exe query state= all | Select-String "Apple" -Context 0,2

Write-Host ""
Write-Host "=== Checking ports 27015, 62078 ===" -ForegroundColor Cyan
netstat -ano | Select-String "27015|62078"

Write-Host ""
Write-Host "=== iTunes install path check ===" -ForegroundColor Cyan
$paths = @(
    "$env:ProgramFiles\iTunes",
    "$env:ProgramFiles(x86)\iTunes",
    "$env:LOCALAPPDATA\Microsoft\WindowsApps\AppleInc.iTunes_nzyj5cx40ttqa"
)
foreach ($p in $paths) {
    if (Test-Path $p) { Write-Host "Found: $p" -ForegroundColor Green }
}
