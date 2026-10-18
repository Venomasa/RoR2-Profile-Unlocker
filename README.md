# Risk of Rain 2 Profile Unlocker

<p align="center">
  <a href="https://github.com/Venomasa/RoR2-Profile-Unlocker/releases/latest/download/RoR2_Profile_Unlocker.exe">
    <img src="assets/download-button.svg" width="360" alt="Download for Windows">
  </a>
</p>

<p align="center">
  <a href="https://github.com/Venomasa/RoR2-Profile-Unlocker/releases/latest">
    <img src="https://img.shields.io/github/v/release/Venomasa/RoR2-Profile-Unlocker?style=flat-square&label=Latest%20Version&color=blue" alt="Latest Version">
  </a>
  <a href="https://github.com/Venomasa/RoR2-Profile-Unlocker/releases">
    <img src="https://img.shields.io/github/downloads/Venomasa/RoR2-Profile-Unlocker/total?style=flat-square&color=333333" alt="Total Downloads">
  </a>
</p>

---

A lightweight profile modification tool for Risk of Rain 2 (v1.5.0+, Survivors of the Void, Seekers of the Storm). Supports both Steam and OnlineFix save formats.

## Features

- Auto-discovery for Steam `userdata` and OnlineFix save directories (`C:\Users\Public\Documents\OnlineFix\`).
- Live process detection to warn or close the game before editing, preventing memory overwrites.
- Selective unlock options:
  - Characters (14 unlockable survivors)
  - Alternate loadout skills (65 skills)
  - Mastery and Monsoon skins (62 skins)
  - Challenge items and equipment (44 items)
  - Artifacts (20 artifacts)
  - Lunar Coins adjustment
- Automatic `.bak` backup creation before any file modification, with one-click restore.

## Download

- Click the green **Download** button above, or go to the [Releases](https://github.com/Venomasa/RoR2-Profile-Unlocker/releases) page.
- Direct download: [`RoR2_Profile_Unlocker.exe`](https://github.com/Venomasa/RoR2-Profile-Unlocker/releases/latest/download/RoR2_Profile_Unlocker.exe) (Portable single-file executable, no Python required).

## Running from Source

Requirements: Python 3.8+ on Windows (Tkinter included by default).

1. Clone the repository:
   ```bash
   git clone https://github.com/Venomasa/RoR2-Profile-Unlocker.git
   cd RoR2-Profile-Unlocker
   ```

2. Run the GUI:
   ```bash
   python RoR2_Unlocker_GUI.py
   ```

   Or use the CLI script:
   ```bash
   python unlock_ror2.py
   ```

   Or run via PowerShell:
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\unlock_ror2.ps1
   ```

## Building the Portable Executable

To compile the standalone single-file `.exe`:

```bash
pip install -r requirements.txt
pyinstaller --noconsole --onefile --icon "ror2_icon.ico" --add-data "unlock_data.json;." --add-data "ror2_icon.ico;." --name "RoR2_Profile_Unlocker" --clean RoR2_Unlocker_GUI.py
```

## Save File Locations

- OnlineFix: `C:\Users\Public\Documents\OnlineFix\632360\Saves\UserProfiles\`
- Steam: `<Steam_Install_Directory>\userdata\<UserID>\632360\remote\UserProfiles\`

## License

For personal, non-commercial offline use.
