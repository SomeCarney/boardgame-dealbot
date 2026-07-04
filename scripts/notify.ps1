# Sends a notification Devon is guaranteed to see:
#   1. Windows toast (scenario=reminder -> stays on screen until dismissed,
#      and persists in the Action Center). Requires an interactive session.
#   2. ntfy.sh push to Devon's phone (free; needs the ntfy app subscribed to
#      the topic below -- see marketing/GROWTH_PLAYBOOK.md "Notifications").
# Both are best-effort and independent; failure of one never blocks the other.
#
# Usage: powershell -File notify.ps1 -Title "..." -Message "..." [-Priority high]

param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string]$Message,
    [string]$Priority = "default",  # ntfy priority: min|low|default|high|urgent
    [string]$ActionUrl = "",        # optional: URL the phone push opens (tap + button)
    [string]$ActionLabel = "Open"   # label for the phone push action button
)

$NTFY_TOPIC = "bgbm-devon-alerts-7q4xk2m9"

# ── Windows toast ──────────────────────────────────────────────
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

# ── ntfy phone push ────────────────────────────────────────────
try {
    $headers = @{ Title = $Title; Priority = $Priority; Tags = "game_die" }
    if ($ActionUrl) {
        # Tapping the notification opens the URL; the button does too. ntfy's
        # Actions header is comma-delimited, so keep the label comma-free.
        $safeLabel = ($ActionLabel -replace ',', ' ')
        $headers["Click"] = $ActionUrl
        $headers["Actions"] = "view, $safeLabel, $ActionUrl, clear=true"
    }
    Invoke-RestMethod -Uri "https://ntfy.sh/$NTFY_TOPIC" -Method Post -Body $Message `
        -Headers $headers -TimeoutSec 15 | Out-Null
    Write-Output "ntfy: sent"
} catch {
    Write-Output "ntfy: failed ($_)"
}
