Get-Service | Where-Object { $_.DisplayName -like '*Apple*' } | Select-Object Name, DisplayName, Status | Format-Table -AutoSize
