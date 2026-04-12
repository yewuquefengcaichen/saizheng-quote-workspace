Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "D:\A赛正\完整导出的商品信息\claudecode-报价系统"
WshShell.Run "python run_server.py", 1, False