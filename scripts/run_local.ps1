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
#
# Retries: this task can fire right as the PC wakes from sleep (WakeToRun),
# and the network/DNS resolver isn't always ready that instant -- seen in
# practice as Keepa connection failures that clear up on their own a minute
# later. Retry a couple of times with a delay rather than losing the whole
# run to a transient post-wake hiccup.
$maxAttempts = 3
for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
    $proc = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\main.py" `
        -WorkingDirectory $repoRoot -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $stdoutTmp -RedirectStandardError $stderrTmp

    Get-Content $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue | Add-Content -Path $logFile
    Remove-Item $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue

    if ($proc.ExitCode -eq 0) {
        break
    }

    if ($attempt -lt $maxAttempts) {
        Add-Content -Path $logFile -Value "Attempt $attempt failed with exit code $($proc.ExitCode) -- retrying in 60s."
        Start-Sleep -Seconds 60
    }
}

if ($proc.ExitCode -ne 0) {
    Add-Content -Path $logFile -Value "Pipeline failed with exit code $($proc.ExitCode) after $maxAttempts attempts -- not committing."
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
