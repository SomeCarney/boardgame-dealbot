# Sends a notification Devon is guaranteed to see:
#   1. Windows toast (scenario=reminder -> stays on screen until dismissed,
#      and persists in the Action Center). Requires an interactive session.
#   2. ntfy.sh push to Devon's phone (free; needs the ntfy app subscribed to
#      the topic below -- see marketing/GROWTH_PLAYBOOK.md "Notifications").
# Both are best-effort and independent; failure of one never blocks the other.
#
# Usage: powershell -File notify.ps1 -Title "..." -Message "..." [-Priority high]
#        [-ActionUrl <url> -ActionLabel "..."] [-Action2Url <url> -Action2Label "..."]

param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Message,
    [string]$Priority = "default",  # ntfy priority: min|low|default|high|urgent
    [string]$ActionUrl = "",        # optional: URL the phone push opens (tap + button)
    [string]$ActionLabel = "Open",  # label for that action button
    [string]$Action2Url = "",       # optional: a SECOND action button (e.g. Post to X)
    [string]$Action2Label = "Open"
)

$NTFY_TOPIC = "bgbm-devon-alerts-7q4xk2m9"

# HTTP headers must be ASCII. ntfy sends the Title via a header, so a non-ASCII
# character there (em dash, curly quote) makes the whole request fail -- which is
# why a deal alert could show on the PC (toast = XML/UTF-8) but never reach the
# phone. Transliterate common punctuation to ASCII and drop anything else. Uses
# only hex code points so this script itself stays pure ASCII.
function ConvertTo-AsciiHeader([string]$s) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $s.ToCharArray()) {
        $c = [int][char]$ch
        if ($c -ge 32 -and $c -le 126) { [void]$sb.Append($ch) }
        elseif ($c -ge 0x2010 -and $c -le 0x2015) { [void]$sb.Append('-') }      # hyphens/dashes
        elseif ($c -eq 0x2018 -or $c -eq 0x2019) { [void]$sb.Append("'") }        # curly single quotes
        elseif ($c -eq 0x201C -or $c -eq 0x201D) { [void]$sb.Append('"') }        # curly double quotes
        elseif ($c -eq 0x2026) { [void]$sb.Append('...') }                        # ellipsis
        elseif ($c -eq 0x00B7 -or $c -eq 0x2022) { [void]$sb.Append('-') }        # middot / bullet
        # else: drop (emoji, etc.)
    }
    return $sb.ToString()
}

# -- Windows toast --------------------------------------------------
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null

    $safeTitle = [System.Security.SecurityElement]::Escape($Title)
    $safeMessage = [System.Security.SecurityElement]::Escape($Message)
    $toastXml = @"
<toast scenario="reminder">
  <visual>
    <binding template="ToastGeneric">
      <text>$safeTitle</text>
      <text>$safeMessage</text>
    </binding>
  </visual>
  <actions>
    <action content="Got it" arguments="dismiss" activationType="system"/>
  </actions>
  <audio src="ms-winsoundevent:Notification.Default"/>
</toast>
"@
    $xml = New-Object Windows.Data.Xml.Dom.XmlDocument
    $xml.LoadXml($toastXml)
    $toast = New-Object Windows.UI.Notifications.ToastNotification $xml
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
    Write-Output "toast: shown"
} catch {
    Write-Output "toast: failed ($_)"
}

# -- ntfy phone push ------------------------------------------------
try {
    $headers = @{ Title = (ConvertTo-AsciiHeader $Title); Priority = $Priority; Tags = "game_die" }

    $actions = @()
    if ($ActionUrl)  { $actions += "view, $(($ActionLabel  -replace ',', ' ')), $ActionUrl, clear=true" }
    if ($Action2Url) { $actions += "view, $(($Action2Label -replace ',', ' ')), $Action2Url, clear=true" }
    if ($actions.Count -gt 0) {
        if ($ActionUrl) { $headers["Click"] = $ActionUrl } else { $headers["Click"] = $Action2Url }
        $headers["Actions"] = ($actions -join "; ")
    }

    # Send the body as explicit UTF-8 bytes so em dashes / curly quotes render on
    # the phone (only the ASCII-only HEADER above is the constraint).
    $bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($Message)
    Invoke-RestMethod -Uri "https://ntfy.sh/$NTFY_TOPIC" -Method Post -Body $bodyBytes `
        -ContentType "text/plain; charset=utf-8" -Headers $headers -TimeoutSec 15 | Out-Null
    Write-Output "ntfy: sent"
} catch {
    Write-Output "ntfy: failed ($_)"
}
