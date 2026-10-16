# Undo windows\lockdown.ps1. Run as ADMINISTRATOR.
$sys  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
$exp  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
$hklm = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
$notif = "HKCU:\Software\Policies\Microsoft\Windows\Explorer"
foreach ($p in @(@($sys,"DisableTaskMgr"), @($sys,"DisableLockWorkstation"),
                 @($sys,"DisableChangePassword"), @($exp,"NoLogoff"), @($exp,"NoClose"),
                 @($hklm,"HideFastUserSwitching"), @($hklm,"DisableCAD"),
                 @($notif,"DisableNotificationCenter"),
                 @("HKLM:\SYSTEM\CurrentControlSet\Control\Keyboard Layout","Scancode Map"))) {
    Remove-ItemProperty -Path $p[0] -Name $p[1] -ErrorAction SilentlyContinue
}
Write-Host "Lockdown removed. REBOOT to get Ctrl and Alt back." -ForegroundColor Green
