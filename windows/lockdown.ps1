# Lock Windows down for the unmanned stand. Run as ADMINISTRATOR, logged in as
# the account the stand runs under. Undo with windows\unlock.ps1.
#
# The autopilot already swallows every key except name typing (Alt+Tab, Win,
# Alt+F4, Esc, Ctrl+Shift+Esc...). What NO program can intercept is
# Ctrl+Alt+Del and Win+L. This script:
#   - switches the Ctrl and Alt keys OFF at keyboard-driver level (Scancode
#     Map), so Ctrl+Alt+Del can't even be pressed. Names don't need them.
#   - empties what Ctrl+Alt+Del / Win+L would offer anyway (belt and braces,
#     e.g. for a second keyboard plugged in before the reboot).
# Needs a REBOOT to take effect.

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

# Ctrl (left/right) and Alt (left/right, incl. AltGr) -> nothing. Format:
# 8 zero bytes, entry count incl. terminator, then (new, old) scancode pairs.
$kb = "HKLM:\SYSTEM\CurrentControlSet\Control\Keyboard Layout"
$map = [byte[]](0,0,0,0, 0,0,0,0, 5,0,0,0,
                0,0,0x1D,0x00,   # left Ctrl
                0,0,0x1D,0xE0,   # right Ctrl
                0,0,0x38,0x00,   # left Alt
                0,0,0x38,0xE0,   # right Alt / AltGr
                0,0,0,0)
Set-ItemProperty -Path $kb -Name "Scancode Map" -Value $map -Type Binary

# Ctrl+Alt+Del can no longer be pressed, so Windows must never ask for it
# at the sign-in screen (e.g. if auto-logon ever fails).
Set-ItemProperty $hklm DisableCAD 1 -Type DWord

# Never sleep, never blank the screens.
powercfg /change monitor-timeout-ac 0
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0

Write-Host "Locked down. REBOOT now - Ctrl and Alt stop working after the reboot." -ForegroundColor Green
Write-Host "Undo: windows\unlock.ps1 (as administrator)."
