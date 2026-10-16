# Lock Windows down for the unmanned stand. Run as ADMINISTRATOR, logged in as
# the account the stand runs under. Undo with windows\unlock.ps1.
#
# The autopilot already swallows every key except name typing (Alt+Tab, Win,
# Alt+F4, Esc, Ctrl+Shift+Esc...). What NO program can intercept is the
# Ctrl+Alt+Del screen and Win+L — this script empties what they offer.

$ErrorActionPreference = "Stop"
$sys  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\System"
$exp  = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer"
$hklm = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
$notif = "HKCU:\Software\Policies\Microsoft\Windows\Explorer"
foreach ($k in $sys, $exp, $notif) { if (-not (Test-Path $k)) { New-Item -Path $k -Force | Out-Null } }

Set-ItemProperty $sys  DisableTaskMgr          1 -Type DWord   # no Task Manager
Set-ItemProperty $sys  DisableLockWorkstation  1 -Type DWord   # no "Lock" / Win+L
Set-ItemProperty $sys  DisableChangePassword   1 -Type DWord
Set-ItemProperty $exp  NoLogoff                1 -Type DWord   # no "Sign out"
Set-ItemProperty $exp  NoClose                 1 -Type DWord   # no shut down / restart
Set-ItemProperty $hklm HideFastUserSwitching   1 -Type DWord   # no "Switch user"
Set-ItemProperty $notif DisableNotificationCenter 1 -Type DWord

# Never sleep, never blank the screens.
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Write-Host "Locked down. Sign out and in again (or reboot) for everything to apply." -ForegroundColor Green
Write-Host "Undo: windows\unlock.ps1 (as administrator)."
