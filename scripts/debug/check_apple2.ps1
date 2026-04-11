Write-Host "=== Apple Devices MS Store package ===" -ForegroundColor Cyan
Get-AppxPackage | Where-Object { $_.Name -like '*Apple*' } | Format-Table Name, Version, Status -AutoSize

Write-Host ""
Write-Host "=== Apple USB drivers in Device Manager ===" -ForegroundColor Cyan
Get-PnpDevice | Where-Object { $_.FriendlyName -like '*Apple*' } | Format-Table FriendlyName, Status, Class -AutoSize

Write-Host ""
Write-Host "=== All services with Apple or mux in name ===" -ForegroundColor Cyan
sc.exe query type= all state= all | Select-String -Pattern "Apple|usbmux|AMDS" -Context 0,1
