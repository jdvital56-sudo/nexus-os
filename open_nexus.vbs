' Запускает open_nexus.ps1 скрыто — без мелькающего чёрного окна консоли.
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\Users\Вадим\projects\nexus-os\open_nexus.ps1""", 0, False
