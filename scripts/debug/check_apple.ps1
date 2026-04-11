Write-Host "=== All Apple-related services ===" -ForegroundColor Cyan
Get-Service | Where-Object { $_.DisplayName -like '*Apple*' -or $_.Name -like '*Apple*' -or $_.Name -like '*usbmux*' } | Format-Table Name, DisplayName, Status -AutoSize

Write-Host ""
Write-Host "=== usbmuxd port check (27015) ===" -ForegroundColor Cyan
$conn = Test-NetConnection -ComputerName 127.0.0.1 -Port 27015 -WarningAction SilentlyContinue
Write-Host "Port 27015 open: $($conn.TcpTestSucceeded)"

Write-Host ""
Write-Host "=== Apple Devices process check ===" -ForegroundColor Cyan
Get-Process | Where-Object { $_.Name -like '*Apple*' -or $_.Name -like '*usbmux*' } | Format-Table Name, Id, CPU -AutoSize
