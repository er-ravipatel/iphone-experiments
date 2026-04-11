$toolsDir = "$env:USERPROFILE\libimobiledevice"
$currentPath = [System.Environment]::GetEnvironmentVariable('PATH', 'User')

if ($currentPath -like "*$toolsDir*") {
    Write-Host "Already in PATH - no changes needed."
} else {
    $newPath = $currentPath + ";" + $toolsDir
    [System.Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
    Write-Host "SUCCESS: Added to user PATH."
    Write-Host "Path added: $toolsDir"
}

Write-Host ""
Write-Host "Verifying tools..."
$tools = @("idevice_id.exe","ideviceinfo.exe","idevicebackup2.exe","ideviceinstaller.exe","idevicescreenshot.exe","idevicename.exe","idevicediagnostics.exe")
foreach ($t in $tools) {
    $found = Join-Path $toolsDir $t
    if (Test-Path $found) {
        Write-Host "  [OK] $t"
    } else {
        Write-Host "  [MISSING] $t"
    }
}
Write-Host ""
Write-Host "NOTE: Open a NEW terminal window for PATH changes to take effect."
