Write-Host "=== Looking for AppleMobileDeviceService.exe ===" -ForegroundColor Cyan
$paths = @(
    "$env:ProgramFiles\Common Files\Apple\Mobile Device Support\AppleMobileDeviceService.exe",
    "$env:ProgramFiles(x86)\Common Files\Apple\Mobile Device Support\AppleMobileDeviceService.exe"
)
foreach ($p in $paths) {
    if (Test-Path $p) { Write-Host "FOUND: $p" -ForegroundColor Green }
    else { Write-Host "NOT found: $p" -ForegroundColor Red }
}

Write-Host ""
Write-Host "=== Common Files Apple folder ===" -ForegroundColor Cyan
$cf = "$env:ProgramFiles\Common Files\Apple"
if (Test-Path $cf) {
    Get-ChildItem $cf -Recurse -Filter "*.exe" | Select-Object FullName
} else {
    Write-Host "Folder not found: $cf" -ForegroundColor Red
}

Write-Host ""
Write-Host "=== All Apple-named services (any state) ===" -ForegroundColor Cyan
sc.exe query type= service state= all 2>&1 | Select-String -Pattern "Apple" -Context 0,3
