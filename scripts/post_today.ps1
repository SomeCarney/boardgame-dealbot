# One-click Mon/Wed/Fri posting helper. Double-click the "Post Today's Deal"
# desktop shortcut (created by scripts/install_tasks-style setup) and this:
#   1. picks the best un-shared deal (src/daily_action.py)
#   2. copies the ready-to-paste price-history comment to your clipboard
#   3. opens r/boardgamedeals' submit page with the title + link PRE-FILLED
#   4. records the deal as offered so it isn't suggested again
# Your job shrinks to: click "Post", press Ctrl+V in the comment box, hit reply.
#
# See marketing/GROWTH_PLAYBOOK.md. Posting stays human-driven on purpose --
# automated link posting on a young account gets filtered/banned.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"

$py = Join-Path $repoRoot ".venv\Scripts\python.exe"

# Refresh drafts so any parallel look at social_drafts.md is current, then pick today's action.
try { & $py "src\make_social_drafts.py" | Out-Null } catch {}

$raw = & $py "src\daily_action.py" "--json"
try {
    $action = $raw | ConvertFrom-Json
} catch {
    & "$PSScriptRoot\notify.ps1" -Title "Board Game Black Market" -Message "Could not work out today's deal to post. Open the repo and run daily_action.py to see why." -Priority "high"
    exit 1
}

if (-not $action.has_deal) {
    & "$PSScriptRoot\notify.ps1" -Title "Nothing new to post today" -Message "No fresh, un-shared deal is live right now. Skipping is fine -- consistency beats forcing a post. Try again after the next bot run." -Priority "default"
    exit 0
}

# 2. comment onto the clipboard so posting it is a single Ctrl+V
try { Set-Clipboard -Value $action.comment } catch {}

# 3. open the pre-filled Reddit submit page in the default browser
Start-Process $action.submit_url

# 4. mark it offered so the next run picks something else
try { & $py "src\daily_action.py" "--mark" $action.asin | Out-Null } catch {}

# 5. tell Devon what to do in the two windows that just opened
$msg = "Reddit submit page opened with the title + link filled in. Click Post, then paste (Ctrl+V) the comment that's already on your clipboard as the top comment. $($action.bonus)"
& "$PSScriptRoot\notify.ps1" -Title "Posting: $($action.title)" -Message $msg -Priority "default"
