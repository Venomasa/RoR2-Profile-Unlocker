@echo off
title Risk of Rain 2 - Profile Unlocker
color 0b

:MENU
cls
echo ======================================================================
echo                 Risk of Rain 2 - Profile Unlocker
echo             Compatible with v1.5.0, DLCs ^& OnlineFix
echo ======================================================================
echo.
echo   Select an option:
echo.
echo   [1] Unlock Characters ^& Alternate Skills Only
echo   [2] Unlock Everything 100%% (Chars, Skills, Skins, Items, Artifacts, Coins)
echo   [3] Restore Backup (.bak)
echo   [G] Open Graphical User Interface (Python GUI)
echo   [4] Exit
echo.
echo ======================================================================
set /p choice="Enter choice (1-4 or G): "

if /i "%choice%"=="G" goto LAUNCH_GUI
if "%choice%"=="1" goto CHARS_SKILLS
if "%choice%"=="2" goto ALL
if "%choice%"=="3" goto RESTORE
if "%choice%"=="4" goto EXIT

echo Invalid choice, please try again.
timeout /t 2 >nul
goto MENU

:LAUNCH_GUI
start "" pythonw "%~dp0RoR2_Unlocker_GUI.py"
exit

:CHARS_SKILLS
cls
echo [Applying Characters and Skills unlocks...]
powershell -ExecutionPolicy Bypass -File "%~dp0unlock_ror2.ps1" -Mode chars_skills
echo.
echo Press any key to return to menu...
pause >nul
goto MENU

:ALL
cls
echo [Applying 100%% complete unlock...]
powershell -ExecutionPolicy Bypass -File "%~dp0unlock_ror2.ps1" -Mode all -Coins 2000000
echo.
echo Press any key to return to menu...
pause >nul
goto MENU

:RESTORE
cls
echo [Searching for and restoring .bak backups...]
powershell -ExecutionPolicy Bypass -Command ^
  "$paths = @('C:\Users\Public\Documents\OnlineFix', 'C:\Users\Public\Documents\Steam', 'C:\Program Files (x86)\Steam\userdata'); ^
   $found = 0; ^
   foreach ($p in $paths) { ^
     if (Test-Path $p) { ^
       Get-ChildItem -Path $p -Filter '*.xml.bak' -Recurse -ErrorAction SilentlyContinue | ForEach-Object { ^
         $orig = $_.FullName.Substring(0, $_.FullName.Length - 4); ^
         Copy-Item -Path $_.FullName -Destination $orig -Force; ^
         Write-Host '  [+] Restored:' $orig -ForegroundColor Green; ^
         $found++; ^
       } ^
     } ^
   }; ^
   if ($found -eq 0) { Write-Host '[-] No .bak backups found.' -ForegroundColor Yellow } else { Write-Host '[OK] Restored' $found 'backup file(s).' -ForegroundColor Green }"
echo.
echo Press any key to return to menu...
pause >nul
goto MENU

:EXIT
exit
