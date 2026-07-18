# Runs once a month (1st of month, 6 AM) via Windows Scheduled Task.
# Re-fetches Keepa data for all ranked game lists, recomputes order,
# regenerates the Best Board Games pages, then commits and pushes.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"

$logDir  = Join-Path $repoRoot "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir "rankings_update.log"
$stdoutTmp = Join-Path $logDir "_rankings_stdout.tmp"
$stderrTmp = Join-Path $logDir "_rankings_stderr.tmp"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "`n==== RANKINGS UPDATE $timestamp ===="

# 1. Re-fetch Keepa data and recompute rankings
$proc = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\update_rankings.py" `
    -WorkingDirectory $repoRoot -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $stdoutTmp -RedirectStandardError $stderrTmp
Get-Content $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue | Add-Content -Path $logFile
Remove-Item $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue

if ($proc.ExitCode -ne 0) {
    Add-Content -Path $logFile -Value "Rankings update failed (exit $($proc.ExitCode)) -- not committing."
    exit $proc.ExitCode
}

# 2. Re-render the site so the new rankings show up on the Best Board Games pages.
# Calls render_site.py's __main__ directly -- an inline `python -c "..."` here
# gets truncated at the first space by Start-Process on Windows (Python only saw
# "import" -> SyntaxError), which is what silently failed this task every run.
$proc2 = Start-Process -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "src\render_site.py" `
    -WorkingDirectory $repoRoot -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput $stdoutTmp -RedirectStandardError $stderrTmp
Get-Content $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue | Add-Content -Path $logFile
Remove-Item $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue

if ($proc2.ExitCode -ne 0) {
    Add-Content -Path $logFile -Value "Site render failed (exit $($proc2.ExitCode)) -- not committing."
    exit $proc2.ExitCode
}

# 3. Commit and push
git add docs/ config/rankings_cache.json config/page_lastmod.json
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $month = Get-Date -Format "yyyy-MM"
    git -c user.name="boardgame-dealbot" -c user.email="actions@users.noreply.github.com" `
        commit -q -m "Monthly rankings update $month"
    git push
    Add-Content -Path $logFile -Value "Rankings committed and pushed for $month."

    # Resubmit every page to IndexNow after the monthly refresh (best-effort).
    try {
        $pingProc = Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\ping_search_engines.py", "--all" `
            -WorkingDirectory $repoRoot -NoNewWindow -Wait -PassThru `
            -RedirectStandardOutput $stdoutTmp -RedirectStandardError $stderrTmp
        Get-Content $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue | Add-Content -Path $logFile
        Remove-Item $stdoutTmp, $stderrTmp -ErrorAction SilentlyContinue
    } catch {
        Add-Content -Path $logFile -Value "IndexNow ping errored -- non-fatal: $_"
    }
} else {
    Add-Content -Path $logFile -Value "No changes in rankings this month."
}
