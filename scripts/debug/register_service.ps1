$exePath = "C:\Program Files\Common Files\Apple\Mobile Device Support\AppleMobileDeviceService.exe"

Write-Host "Registering Apple Mobile Device Service..." -ForegroundColor Cyan
sc.exe create AppleMobileDeviceService binPath= "`"$exePath`"" start= auto DisplayName= "Apple Mobile Device Service"

Write-Host "Starting service..." -ForegroundColor Cyan
sc.exe start AppleMobileDeviceService

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "=== Service status ===" -ForegroundColor Cyan
sc.exe query AppleMobileDeviceService
