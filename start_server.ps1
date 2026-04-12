$p = Start-Process -FilePath 'python' -ArgumentList 'run_server.py' -WorkingDirectory 'D:\A赛正\完整导出的商品信息\claudecode-报价系统' -WindowStyle Normal -PassThru
Write-Host "Process ID: $($p.Id)"
Start-Sleep -Seconds 10
netstat -ano | findstr ':5000'