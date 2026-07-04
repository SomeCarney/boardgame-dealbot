# Creates (or refreshes) the "Post Today's Deal" shortcut on the desktop.
# Double-clicking that shortcut runs scripts/post_today.ps1: it opens
# r/boardgamedeals' submit page pre-filled and copies the comment to the
# clipboard, collapsing the Mon/Wed/Fri routine to a click + a paste.
# Run this once (idempotent -- safe to re-run after moving the repo).

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$target = Join-Path $repoRoot "scripts\post_today.ps1"

$desktop = [Environment]::GetFolderPath("Desktop")
$linkPath = Join-Path $desktop "Post Today's Deal.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($linkPath)
$shortcut.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Minimized -File `"$target`""
$shortcut.WorkingDirectory = $repoRoot
$shortcut.Description = "Open r/boardgamedeals pre-filled with today's best deal and copy the comment"
$shortcut.IconLocation = "$env:SystemRoot\System32\imageres.dll,77"  # a coin/target-ish icon
$shortcut.Save()

Write-Output "Created shortcut: $linkPath"
