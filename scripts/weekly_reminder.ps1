# Fires Mon/Wed/Fri at 6:30 PM via the "BoardGameSocialReminder" scheduled
# task. Picks today's best un-shared deal and sends a reminder that is already
# the whole task: the phone push has an "Open Reddit" button that opens the
# submit page pre-filled, and includes the exact comment to paste. On the PC,
# the "Post Today's Deal" desktop shortcut does it in one click (opens Reddit
# pre-filled + copies the comment to the clipboard). See marketing/GROWTH_PLAYBOOK.md.

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot
$env:PYTHONIOENCODING = "utf-8"

$py = Join-Path $repoRoot ".venv\Scripts\python.exe"

# Fresh drafts so social_drafts.md is current, then compute today's one action.
try { & $py "src\make_social_drafts.py" | Out-Null } catch {}

$action = $null
try {
    $raw = & $py "src\daily_action.py" "--json"
    $action = $raw | ConvertFrom-Json
} catch {
    $action = $null
}

if (-not $action -or -not $action.has_deal) {
    & "$PSScriptRoot\notify.ps1" -Title "Board Game Black Market - no post needed today" `
        -Message "No fresh, un-shared deal is live right now, so there's nothing to post to r/boardgamedeals today. Skipping is fine -- consistency beats forcing it." `
        -Priority "default"
    exit 0
}

# Phone push: tapping it (or the "Open Reddit" button) opens the pre-filled
# submit page; the body carries the comment so it can be copied on mobile too.
$msg = @"
Post to r/boardgamedeals (tap "Open Reddit" -> the title + link are pre-filled -> Post):

$($action.title)

Then paste this as the top comment:
$($action.comment)

$($action.bonus)

On your PC: just double-click "Post Today's Deal" on the desktop -- it opens Reddit pre-filled and copies the comment for you.
"@

& "$PSScriptRoot\notify.ps1" -Title "5-min task: today's board game deal" `
    -Message $msg -Priority "high" `
    -ActionUrl $action.submit_url -ActionLabel "Open Reddit"
