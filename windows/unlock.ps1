# Undo windows\lockdown.ps1. Run as ADMINISTRATOR.
$sys  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
$exp  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
$hklm = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
$notif = "HKCU:\Software\Policies\Microsoft\Windows\Explorer"
foreach ($p in @(@($sys,"DisableTaskMgr"), @($sys,"DisableLockWorkstation"),
                 @($sys,"DisableChangePassword"), @($exp,"NoLogoff"), @($exp,"NoClose"),
                 @($hklm,"HideFastUserSwitching"), @($notif,"DisableNotificationCenter"))) {
    Remove-ItemProperty -Path $p[0] -Name $p[1] -ErrorAction SilentlyContinue
}
Write-Host "Lockdown removed. Sign out and in again to apply." -ForegroundColor Green
