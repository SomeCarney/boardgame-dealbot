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

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n==== $timestamp ===="

try {
    $output = & ".\.venv\Scripts\python.exe" "src\main.py" 2>&1
    $exitCode = $LASTEXITCODE
    Add-Content -Path $logFile -Value $output

    if ($exitCode -ne 0) {
        Add-Content -Path $logFile -Value "Pipeline failed with exit code $exitCode -- not committing."
        exit $exitCode
    }

    git add docs/ posted_log.json config/category_cache.json
    $hasChanges = git diff --cached --quiet; $hasChangesExit = $LASTEXITCODE
    if ($hasChangesExit -ne 0) {
        git -c user.name="boardgame-dealbot" -c user.email="actions@users.noreply.github.com" commit -q -m "Update deals $timestamp"
        git push
        Add-Content -Path $logFile -Value "Committed and pushed updated deals."
    } else {
        Add-Content -Path $logFile -Value "No new deals this run -- nothing to commit."
    }
} catch {
    Add-Content -Path $logFile -Value "ERROR: $_"
    exit 1
}
