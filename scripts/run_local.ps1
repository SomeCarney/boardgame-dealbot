# Runs the pipeline locally and pushes the result. This exists because
# Keepa rejects requests from GitHub Actions' datacenter IP ranges, so the
# schedule has to run from a real residential connection instead -- see
# README.md. Invoked by a Windows Scheduled Task every few hours.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$logDir = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "run_local.log"
$stdoutTmp = Join-Path $logDir "_stdout.tmp"
$stderrTmp = Join-Path $logDir "_stderr.tmp"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n==== $timestamp ===="

# Native stdout/stderr are redirected to files rather than via PowerShell's
# 2>&1 stream operator -- with $ErrorActionPreference = "Stop", 2>&1 wraps
# every stderr line (including normal Python log output) in a terminating
# NativeCommandError even when the process exits 0.
$proc = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\main.py" `
    -WorkingDirectory $repoRoot -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $stdoutTmp -RedirectStandardError $stderrTmp

Get-Content $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue | Add-Content -Path $logFile
Remove-Item $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue

if ($proc.ExitCode -ne 0) {
    Add-Content -Path $logFile -Value "Pipeline failed with exit code $($proc.ExitCode) -- not committing."
    exit $proc.ExitCode
}

git add docs/ posted_log.json config/category_cache.json
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git -c user.name="boardgame-dealbot" -c user.email="actions@users.noreply.github.com" commit -q -m "Update deals $timestamp"
    git push
    Add-Content -Path $logFile -Value "Committed and pushed updated deals."
} else {
    Add-Content -Path $logFile -Value "No new deals this run -- nothing to commit."
}
