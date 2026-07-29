# 创建桌面快捷方式
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$shortcutPath = [System.IO.Path]::Combine([Environment]::GetFolderPath("Desktop"), "股票分析助手.lnk")
$targetPath = Join-Path $projectRoot "start.bat"
$iconLocation = "shell32.dll,13"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = "股票分析助手 - 一键启动"
$shortcut.IconLocation = $iconLocation
$shortcut.Save()

Write-Host "桌面快捷方式已创建: $shortcutPath" -ForegroundColor Green
