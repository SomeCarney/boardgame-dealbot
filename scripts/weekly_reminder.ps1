# Fires Mon/Wed/Fri at 6:30 PM via the "BoardGameSocialReminder" scheduled
# task. Regenerates social_drafts.md so the drafts are current, then sends
# a toast + phone push telling Devon exactly which 5-minute task is due.
# See marketing/GROWTH_PLAYBOOK.md for the full routine.

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Fresh drafts so the reminder always points at current deals
try {
    Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "src\make_social_drafts.py" `
        -WorkingDirectory $repoRoot -NoNewWindow -Wait | Out-Null
} catch {}

$day = (Get-Date).DayOfWeek
switch ($day) {
    "Monday" {
        $msg = "5-min task: open social_drafts.md in C:\Claude\boardgame-dealbot and post the best deal to r/boardgamedeals (clean link, title format is pre-written)."
    }
    "Wednesday" {
        $msg = "5-min task: post a deal from social_drafts.md to r/boardgamedeals. Bonus 10 min: answer 2-3 questions in the r/boardgames daily discussion thread."
    }
    "Friday" {
        $msg = "5-min task: post a deal from social_drafts.md to r/boardgamedeals. Then Instagram sweep: reply to every comment, follow 10-15 accounts under #boardgamedeals."
    }
    default {
        $msg = "5-min task: open social_drafts.md and post the best deal to r/boardgamedeals."
    }
}

& "$PSScriptRoot\notify.ps1" -Title "Board Game Black Market - weekly routine" -Message $msg -Priority "high"
