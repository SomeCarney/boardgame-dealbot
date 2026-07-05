# Fires Wed/Fri evening via the "BoardGameSocialReminder" scheduled task.
#
# Deal POSTING is now event-driven -- main.py pushes you the moment a good deal
# is found (whenever it comes up), so it's no longer tied to specific days. This
# reminder handles only the NON-deal weekly habits, each with a tap-to-go link
# so you can act straight from your phone:
#   Wednesday -> answer a few questions in r/boardgames' daily discussion thread
#   Friday    -> Instagram sweep (reply to comments, follow a few niche accounts)
# See marketing/GROWTH_PLAYBOOK.md.

$ErrorActionPreference = "Continue"

$day = (Get-Date).DayOfWeek
switch ($day) {
    "Wednesday" {
        $title = "Wednesday: answer a few questions"
        $msg   = "~10 min in r/boardgames' daily discussion: answer 2-3 questions genuinely. Only link one of our guides/lists when it DIRECTLY answers the question (e.g. someone asks 'best 2-player games?'). Tap below to open the latest thread."
        $url   = "https://www.reddit.com/r/boardgames/search/?q=%22Daily%20Discussion%22&restrict_sr=1&sort=new"
        $label = "Open discussion"
    }
    "Friday" {
        $title = "Friday: Instagram sweep"
        $msg   = "~5 min: reply to every comment on recent posts, then follow 10-15 accounts that recently posted under #boardgamedeals or #boardgamenight. Tap below to open Instagram."
        $url   = "https://www.instagram.com/boardgameblackmarket/"
        $label = "Open Instagram"
    }
    default {
        # Deals are event-driven now; no scheduled task on other days.
        exit 0
    }
}

& "$PSScriptRoot\notify.ps1" -Title $title -Message $msg -Priority "high" -ActionUrl $url -ActionLabel $label
