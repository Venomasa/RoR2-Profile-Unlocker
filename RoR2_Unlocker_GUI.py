import os
import sys
import glob
import json
import time
import uuid
import shutil
import ctypes
from ctypes import wintypes
import winreg
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# -------------------------------------------------------------
# Data Loader (Supports Standalone Portable .exe & External JSON)
# -------------------------------------------------------------
DATA_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unlock_data.json")

def load_unlock_data():
    candidates = []
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            candidates.append(os.path.join(sys._MEIPASS, "unlock_data.json"))
        candidates.append(os.path.join(os.path.dirname(sys.executable), "unlock_data.json"))
    candidates.append(DATA_JSON_PATH)
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "unlock_data.json"))

    for c in candidates:
        if os.path.exists(c):
            try:
                with open(c, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {"characters": [], "skills": [], "skins": [], "items": [], "artifacts": []}

UNLOCK_DATA = load_unlock_data()

# -------------------------------------------------------------
# Process Detection & Management via Windows API (ctypes)
# -------------------------------------------------------------
TH32CS_SNAPPROCESS = 0x00000002

class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('cntUsage', wintypes.DWORD),
        ('th32ProcessID', wintypes.DWORD),
        ('th32DefaultHeapID', ctypes.c_void_p),
        ('th32ModuleID', wintypes.DWORD),
        ('cntThreads', wintypes.DWORD),
        ('th32ParentProcessID', wintypes.DWORD),
        ('pcPriClassBase', wintypes.LONG),
        ('dwFlags', wintypes.DWORD),
        ('szExeFile', ctypes.c_char * 260)
    ]

def detect_running_game():
    """
    Scans running Windows processes using CreateToolhelp32Snapshot.
    Returns (pid, exe_name, exe_path) if Risk of Rain 2 is running, else None.
    """
    hSnapshot = ctypes.windll.kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if hSnapshot == -1 or not hSnapshot:
        return None

    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    success = ctypes.windll.kernel32.Process32First(hSnapshot, ctypes.byref(pe))

    found = None
    target_names = ["risk of rain 2.exe", "risk of rain 2", "riskofrain2.exe"]

    while success:
        exe_str = pe.szExeFile.decode('latin1', errors='ignore').lower()
        if any(t in exe_str for t in target_names):
            pid = pe.th32ProcessID
            full_path = get_process_full_path(pid)
            found = (pid, pe.szExeFile.decode('latin1', errors='ignore'), full_path)
            break
        success = ctypes.windll.kernel32.Process32Next(hSnapshot, ctypes.byref(pe))

    ctypes.windll.kernel32.CloseHandle(hSnapshot)
    return found

def get_process_full_path(pid):
    """Retrieves full image path of process using QueryFullProcessImageNameW."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    hProc = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not hProc:
        return None
    buf = ctypes.create_unicode_buffer(1024)
    size = wintypes.DWORD(1024)
    path = None
    if ctypes.windll.kernel32.QueryFullProcessImageNameW(hProc, 0, buf, ctypes.byref(size)):
        path = buf.value
    ctypes.windll.kernel32.CloseHandle(hProc)
    return path

def terminate_game_process(pid):
    """Terminates process cleanly by PID."""
    PROCESS_TERMINATE = 0x0001
    hProc = ctypes.windll.kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if hProc:
        ctypes.windll.kernel32.TerminateProcess(hProc, 0)
        ctypes.windll.kernel32.CloseHandle(hProc)
        return True
    return False

# -------------------------------------------------------------
# Smart Profile Discovery Engine (OnlineFix + Steam + Player.log)
# -------------------------------------------------------------
def get_active_profile_from_log():
    """
    Reads Risk of Rain 2 Player.log from AppData LocalLow
    to determine which profile XML the game actually loaded.
    """
    local_low = os.path.expandvars(r"%LOCALAPPDATA%Low")
    log_path = os.path.join(local_low, "Hopoo Games, LLC", "Risk of Rain 2", "Player.log")
    if not os.path.exists(log_path):
        # Alternative casing
        alt_path = os.path.join(local_low, "Hopoo Games", "Risk of Rain 2", "Player.log")
        if os.path.exists(alt_path):
            log_path = alt_path

    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "Attempting to load user profile /UserProfiles/" in line:
                        parts = line.split("/UserProfiles/")
                        if len(parts) > 1:
                            return parts[1].strip()
        except Exception:
            pass
    return None

def discover_all_profiles():
    """
    Exhaustively and dynamically searches for Risk of Rain 2 save profiles:
    1. OnlineFix saves in C:\\Users\\Public\\Documents\\OnlineFix\\
    2. Steam userdata (Registry + common drive roots)
    3. Other emulator paths (CODEX, Goldberg, Rune)
    4. Active profile logged in Player.log
    """
    seen_paths = set()
    active_filename = get_active_profile_from_log()

    # 1. OnlineFix paths (AppID 632360, 480, etc.)
    of_roots = [
        r"C:\Users\Public\Documents\OnlineFix",
        r"C:\Users\Public\Documents\Steam",
        os.path.expandvars(r"%PUBLIC%\Documents\OnlineFix"),
        os.path.expandvars(r"%PUBLIC%\Documents\Steam"),
    ]
    for root in of_roots:
        if os.path.isdir(root):
            for xml in glob.glob(os.path.join(root, "**", "*.xml"), recursive=True):
                if xml.endswith(".bak") or "UserProfiles" not in xml:
                    continue
                seen_paths.add(os.path.normcase(os.path.abspath(xml)))

    # 2. Steam userdata candidates
    steam_roots = []
    # Registry Current User
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            val, _ = winreg.QueryValueEx(key, "SteamPath")
            if val:
                steam_roots.append(os.path.join(val.replace("/", "\\"), "userdata"))
    except Exception:
        pass

    # Registry Local Machine
    for reg_path in [r"Software\Valve\Steam", r"Software\Wow6432Node\Valve\Steam"]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                if val:
                    steam_roots.append(os.path.join(val, "userdata"))
        except Exception:
            pass

    # Drive scans
    for drive in ["C", "D", "E", "F", "G"]:
        steam_roots.extend([
            rf"{drive}:\Program Files (x86)\Steam\userdata",
            rf"{drive}:\Program Files\Steam\userdata",
            rf"{drive}:\Steam\userdata",
            rf"{drive}:\Games\Steam\userdata",
        ])

    for s_root in steam_roots:
        if os.path.isdir(s_root):
            for xml in glob.glob(os.path.join(s_root, "**", "*.xml"), recursive=True):
                if xml.endswith(".bak") or "UserProfiles" not in xml:
                    continue
                seen_paths.add(os.path.normcase(os.path.abspath(xml)))

    # 3. Goldberg / AppData saves
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        goldberg_path = os.path.join(appdata, "Goldberg SteamEmu Saves")
        if os.path.isdir(goldberg_path):
            for xml in glob.glob(os.path.join(goldberg_path, "**", "*.xml"), recursive=True):
                if xml.endswith(".bak") or "UserProfiles" not in xml:
                    continue
                seen_paths.add(os.path.normcase(os.path.abspath(xml)))

    # Parse and enrich detected profiles
    profiles = []
    for path in seen_paths:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            name_el = root.find("name")
            p_name = name_el.text if name_el is not None and name_el.text else "Unnamed"
            stats_el = root.find("stats")
            unlocks_count = len(stats_el.findall("unlock")) if stats_el is not None else 0
            coins_el = root.find("coins")
            coins_val = coins_el.text if coins_el is not None and coins_el.text else "0"
            fname = os.path.basename(path)

            is_active = bool(active_filename and fname.lower() == active_filename.lower())

            path_low = path.lower()
            if "onlinefix" in path_low:
                ptype = "OnlineFix"
            elif "steam" in path_low or "userdata" in path_low:
                ptype = "Steam"
            else:
                ptype = "Emulator/Custom"

            label = f"{p_name} [{ptype}]"
            if is_active:
                label += " (Active Profile)"
            label += f" - {fname}"

            profiles.append({
                "label": label,
                "path": path,
                "name": p_name,
                "type": ptype,
                "filename": fname,
                "is_active": is_active,
                "unlocks": unlocks_count,
                "coins": coins_val
            })
        except Exception:
            pass

    # Sort: Active first, then OnlineFix, then Steam, then alphabetical
    profiles.sort(key=lambda x: (not x["is_active"], x["type"] != "OnlineFix", x["name"].lower()))
    return profiles

# -------------------------------------------------------------
# XML Modifier Logic
# -------------------------------------------------------------
def apply_unlocks(xml_path, unlock_cats, set_coins=True, coins_val=2000000):
    """
    Applies selected unlock categories to the target XML profile.
    Safely creates .bak backup immediately before writing.
    """
    parent_dir = os.path.dirname(xml_path)
    if not os.path.isdir(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    # If file doesn't exist, initialize a clean valid profile structure first
    if not os.path.exists(xml_path):
        root = ET.Element("UserProfile")
        ET.SubElement(root, "version").text = "3"
        ET.SubElement(root, "name").text = "UnlockedPlayer"
        ET.SubElement(root, "coins").text = str(coins_val)
        ET.SubElement(root, "totalCollectedCoins").text = str(coins_val)
        ET.SubElement(root, "stats")
        ET.SubElement(root, "achievementsList").text = ""
        ET.SubElement(root, "unviewedAchievementsList").text = ""
        ET.SubElement(root, "viewedUnlockablesList").text = ""
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)

    bak_path = xml_path + ".bak"
    # Create permanent backup of original file if not already present
    if not os.path.exists(bak_path):
        shutil.copy2(xml_path, bak_path)

    tree = ET.parse(xml_path)
    root = tree.getroot()

    entries = []
    for cat in unlock_cats:
        if cat in UNLOCK_DATA:
            entries.extend(UNLOCK_DATA[cat])

    unlock_tokens = set(e["unlock"] for e in entries)
    achieve_tokens = set(e["id"] for e in entries)

    # 1. Update Coins
    if set_coins:
        coins_elem = root.find("coins")
        if coins_elem is None:
            coins_elem = ET.SubElement(root, "coins")
        coins_elem.text = str(coins_val)

        tot_coins = root.find("totalCollectedCoins")
        if tot_coins is None:
            tot_coins = ET.SubElement(root, "totalCollectedCoins")
        try:
            cur_tot = int(tot_coins.text or "0")
        except ValueError:
            cur_tot = 0
        if cur_tot < coins_val:
            tot_coins.text = str(coins_val)

    # 2. Update <stats> with <unlock>TOKEN</unlock>
    stats_elem = root.find("stats")
    if stats_elem is None:
        stats_elem = ET.SubElement(root, "stats")

    existing_unlocks = set()
    for u in stats_elem.findall("unlock"):
        if u.text:
            existing_unlocks.add(u.text.strip())

    added_count = 0
    for tok in sorted(unlock_tokens):
        if tok not in existing_unlocks:
            el = ET.SubElement(stats_elem, "unlock")
            el.text = tok
            added_count += 1

    # 3. Update <achievementsList>
    ach_elem = root.find("achievementsList")
    if ach_elem is None:
        ach_elem = ET.SubElement(root, "achievementsList")
    current_achs = set((ach_elem.text or "").split())
    merged_achs = current_achs.union(achieve_tokens)
    ach_elem.text = " ".join(sorted(merged_achs))

    # 4. Update <viewedUnlockablesList>
    viewed_elem = root.find("viewedUnlockablesList")
    if viewed_elem is None:
        viewed_elem = ET.SubElement(root, "viewedUnlockablesList")
    current_viewed = set((viewed_elem.text or "").split())
    merged_viewed = current_viewed.union(unlock_tokens)
    viewed_elem.text = " ".join(sorted(merged_viewed))

    # 5. Clear unviewedAchievementsList
    unviewed = root.find("unviewedAchievementsList")
    if unviewed is not None:
        unviewed.text = ""

    ET.indent(tree, space="  ", level=0)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return added_count, len(existing_unlocks) + added_count, bak_path

def restore_backup(xml_path):
    """Restore profile from its .bak backup file."""
    bak_path = xml_path + ".bak"
    if os.path.exists(bak_path):
        shutil.copy2(bak_path, xml_path)
        return True, bak_path
    return False, None

# -------------------------------------------------------------
# GUI Implementation (Clean Dark Theme - English)
# -------------------------------------------------------------
class RoR2UnlockerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Risk of Rain 2 - Profile Unlocker")
        self.geometry("680x820")
        self.minsize(620, 740)

        # Set Official Risk of Rain 2 Window Icon
        icon_candidates = [
            os.path.join(getattr(sys, '_MEIPASS', ''), "ror2_icon.ico"),
            os.path.join(os.path.dirname(sys.executable), "ror2_icon.ico"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "ror2_icon.ico"),
        ]
        for ic in icon_candidates:
            if os.path.exists(ic):
                try:
                    self.iconbitmap(ic)
                    break
                except Exception:
                    pass

        # High-Contrast Modern Dark Palette
        self.bg_color = "#16161e"
        self.card_color = "#1f2335"
        self.card_inner = "#1a1b26"
        self.accent_color = "#7aa2f7"
        self.btn_color = "#2e3440"
        self.btn_hover = "#434c5e"
        self.text_color = "#ffffff"       # Pure Bright White
        self.text_secondary = "#c0caf5"   # Light Blue/White
        self.text_muted = "#9aa5ce"
        self.success_color = "#9ece6a"
        self.warn_color = "#e0af68"
        self.danger_color = "#f7768e"
        self.primary_btn = "#7aa2f7"
        self.primary_txt = "#15161e"

        self.configure(bg=self.bg_color)

        # State Variables
        self.game_proc = None  # None or (pid, name, path)
        self.profile_list = discover_all_profiles()
        self.selected_profile_label = tk.StringVar()
        self.selected_profile_path = tk.StringVar()

        self.var_chars = tk.BooleanVar(value=True)
        self.var_skills = tk.BooleanVar(value=True)
        self.var_skins = tk.BooleanVar(value=False)
        self.var_items = tk.BooleanVar(value=False)
        self.var_artifacts = tk.BooleanVar(value=False)
        self.var_coins = tk.BooleanVar(value=True)
        self.entry_coins = tk.StringVar(value="2000000")

        # Configure Styles
        self.setup_styles()
        self.create_widgets()

        # Set default profile
        if self.profile_list:
            self.on_profile_selected(self.profile_list[0]["label"])

        # Start live game process monitoring loop
        self.poll_game_process()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=self.bg_color, foreground=self.text_color, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_color, relief="flat")
        style.configure("TLabel", background=self.card_color, foreground=self.text_color, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=self.bg_color, foreground=self.accent_color, font=("Segoe UI", 16, "bold"))
        style.configure("SubHeader.TLabel", background=self.bg_color, foreground="#9aa5ce", font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.card_color, foreground=self.accent_color, font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background=self.card_color, foreground=self.text_color, font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", self.card_color)], foreground=[("active", "#ffffff")])

        # High-Contrast Combobox Style
        style.configure("TCombobox",
            fieldbackground="#0f1017",
            background="#2e3440",
            foreground="#ffffff",
            darkcolor="#0f1017",
            lightcolor="#414868",
            arrowcolor="#7aa2f7"
        )
        style.map("TCombobox",
            fieldbackground=[("readonly", "#0f1017"), ("active", "#1a1b26"), ("focus", "#0f1017")],
            foreground=[("readonly", "#ffffff"), ("active", "#ffffff"), ("focus", "#ffffff")],
            selectbackground=[("readonly", "#3d4561")],
            selectforeground=[("readonly", "#ffffff")]
        )
        self.option_add("*TCombobox*Listbox.background", "#0f1017")
        self.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.option_add("*TCombobox*Listbox.selectBackground", "#3d4561")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def create_widgets(self):
        main_container = ttk.Frame(self, padding="20 16 20 16")
        main_container.pack(fill=tk.BOTH, expand=True)

        # Header Title
        title_lbl = ttk.Label(main_container, text="Risk of Rain 2 - Profile Unlocker", style="Header.TLabel")
        title_lbl.pack(anchor="w", pady=(0, 2))

        sub_lbl = ttk.Label(main_container, text="Compatible with v1.5.0, Survivors of the Void, Seekers of the Storm & OnlineFix", style="SubHeader.TLabel")
        sub_lbl.pack(anchor="w", pady=(0, 10))

        # ----------------- Game Process Status Card (Live) -----------------
        self.game_card = ttk.Frame(main_container, style="Card.TFrame", padding="10 12 10 12")
        self.game_card.pack(fill=tk.X, pady=(0, 10))

        game_row = ttk.Frame(self.game_card, style="Card.TFrame")
        game_row.pack(fill=tk.X)

        self.lbl_game_badge = tk.Label(game_row, text="GAME STATUS:", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_secondary)
        self.lbl_game_badge.pack(side=tk.LEFT, padx=(0, 6))

        self.lbl_game_text = tk.Label(game_row, text="Scanning for Risk of Rain 2...", font=("Segoe UI", 9, "bold"), bg=self.card_color, fg=self.text_muted)
        self.lbl_game_text.pack(side=tk.LEFT)

        self.btn_close_game = tk.Button(game_row, text="Close Game Safely", font=("Segoe UI", 8, "bold"),
                                        bg="#f7768e", fg="#15161e", activebackground="#ff7a93", activeforeground="#15161e",
                                        relief="flat", padx=8, pady=2, cursor="hand2", command=self.close_game_action)

        # ----------------- Profile Selection Card -----------------
        prof_card = ttk.Frame(main_container, style="Card.TFrame", padding="14")
        prof_card.pack(fill=tk.X, pady=(0, 10))

        prof_title = ttk.Label(prof_card, text="TARGET SAVE PROFILE (AUTO-DETECTED)", style="Section.TLabel")
        prof_title.pack(anchor="w", pady=(0, 8))

        # Dropdown selection of detected profiles
        row_dropdown = ttk.Frame(prof_card, style="Card.TFrame")
        row_dropdown.pack(fill=tk.X, pady=(0, 6))

        labels = [p["label"] for p in self.profile_list] if self.profile_list else ["No profile files detected automatically"]
        self.cb_profile = ttk.Combobox(row_dropdown, textvariable=self.selected_profile_label, values=labels, state="readonly", font=("Segoe UI", 9, "bold"))
        self.cb_profile.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        self.cb_profile.bind("<<ComboboxSelected>>", lambda e: self.on_profile_selected(self.selected_profile_label.get()))

        btn_rescan = tk.Button(row_dropdown, text="Rescan", font=("Segoe UI", 9), bg=self.btn_color, fg="#c0caf5",
                               activebackground=self.btn_hover, activeforeground="#ffffff", relief="flat", padx=10, pady=3,
                               cursor="hand2", command=self.refresh_profiles)
        btn_rescan.pack(side=tk.LEFT)

        # Dedicated High-Contrast Full Path Entry
        row_path = ttk.Frame(prof_card, style="Card.TFrame")
        row_path.pack(fill=tk.X, pady=(2, 6))

        self.entry_path = tk.Entry(row_path, textvariable=self.selected_profile_path, font=("Consolas", 9, "bold"),
                                   bg="#0f1017", fg="#ffffff", insertbackground="#ffffff", relief="flat", state="readonly", readonlybackground="#0f1017")
        self.entry_path.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8), ipady=3)

        btn_browse = tk.Button(row_path, text="Browse...", font=("Segoe UI", 9, "bold"), bg=self.btn_color, fg="#ffffff",
                               activebackground=self.btn_hover, activeforeground="#ffffff", relief="flat", padx=12, pady=3,
                               cursor="hand2", command=self.browse_file)
        btn_browse.pack(side=tk.LEFT, padx=(0, 4))

        btn_open_folder = tk.Button(row_path, text="Open Folder", font=("Segoe UI", 9), bg=self.btn_color, fg="#c0caf5",
                                    activebackground=self.btn_hover, activeforeground="#ffffff", relief="flat", padx=10, pady=3,
                                    cursor="hand2", command=self.open_profile_folder)
        btn_open_folder.pack(side=tk.LEFT)

        # Profile Details Info
        self.lbl_prof_info = tk.Label(prof_card, text="", font=("Segoe UI", 8), bg=self.card_color, fg=self.accent_color, anchor="w")
        self.lbl_prof_info.pack(fill=tk.X, pady=(2, 0))

        # ----------------- Quick Presets -----------------
        preset_frame = ttk.Frame(main_container)
        preset_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(preset_frame, text="Quick Presets:", font=("Segoe UI", 9, "bold"), background=self.bg_color, foreground="#9aa5ce").pack(side=tk.LEFT, padx=(0, 8))

        btn_preset_chars = tk.Button(preset_frame, text="Characters & Skills", font=("Segoe UI", 9), bg=self.btn_color, fg="#ffffff",
                                     relief="flat", padx=10, pady=3, cursor="hand2", command=self.preset_chars_skills)
        btn_preset_chars.pack(side=tk.LEFT, padx=3)

        btn_preset_all = tk.Button(preset_frame, text="Unlock All (100%)", font=("Segoe UI", 9), bg=self.btn_color, fg=self.accent_color,
                                   relief="flat", padx=10, pady=3, cursor="hand2", command=self.preset_all)
        btn_preset_all.pack(side=tk.LEFT, padx=3)

        btn_preset_clear = tk.Button(preset_frame, text="Deselect All", font=("Segoe UI", 9), bg=self.btn_color, fg="#787c99",
                                     relief="flat", padx=10, pady=3, cursor="hand2", command=self.preset_none)
        btn_preset_clear.pack(side=tk.LEFT, padx=3)

        # ----------------- Content Options Card -----------------
        opts_card = ttk.Frame(main_container, style="Card.TFrame", padding="14")
        opts_card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        opts_title = ttk.Label(opts_card, text="CONTENT TO UNLOCK", style="Section.TLabel")
        opts_title.pack(anchor="w", pady=(0, 8))

        # Checkboxes
        c1 = ttk.Checkbutton(opts_card, text=f"Unlock All Characters ({len(UNLOCK_DATA['characters'])} locked survivors + defaults)", variable=self.var_chars)
        c1.pack(anchor="w", pady=4)

        c2 = ttk.Checkbutton(opts_card, text=f"Unlock All Alternate Skills ({len(UNLOCK_DATA['skills'])} loadout skill variants)", variable=self.var_skills)
        c2.pack(anchor="w", pady=4)

        c3 = ttk.Checkbutton(opts_card, text=f"Unlock All Mastery & Monsoon Skins ({len(UNLOCK_DATA['skins'])} survivor skins)", variable=self.var_skins)
        c3.pack(anchor="w", pady=4)

        c4 = ttk.Checkbutton(opts_card, text=f"Unlock All Challenge Items & Equipment ({len(UNLOCK_DATA['items'])} items)", variable=self.var_items)
        c4.pack(anchor="w", pady=4)

        c5 = ttk.Checkbutton(opts_card, text=f"Unlock All Artifacts ({len(UNLOCK_DATA['artifacts'])} gameplay modifiers)", variable=self.var_artifacts)
        c5.pack(anchor="w", pady=4)

        # Divider line
        div = tk.Frame(opts_card, height=1, bg="#313244")
        div.pack(fill=tk.X, pady=8)

        # Coins Section
        coins_row = ttk.Frame(opts_card, style="Card.TFrame")
        coins_row.pack(fill=tk.X, pady=2)

        c_coins = ttk.Checkbutton(coins_row, text="Add Lunar Coins:", variable=self.var_coins)
        c_coins.pack(side=tk.LEFT)

        entry_coins = tk.Entry(coins_row, textvariable=self.entry_coins, font=("Consolas", 10, "bold"), width=12, bg="#0f1017", fg="#ffffff",
                               insertbackground="#ffffff", relief="flat", justify="center")
        entry_coins.pack(side=tk.LEFT, padx=10)

        ttk.Label(coins_row, text="coins", foreground="#9aa5ce").pack(side=tk.LEFT)

        # ----------------- Status Log Area -----------------
        self.status_lbl = tk.Label(main_container, text="Ready. Select options and click Apply.", font=("Segoe UI", 9), bg=self.bg_color, fg="#9aa5ce", wraplength=620, justify="left")
        self.status_lbl.pack(fill=tk.X, pady=(0, 8))

        # ----------------- Action Buttons -----------------
        btn_box = ttk.Frame(main_container)
        btn_box.pack(fill=tk.X)

        self.btn_apply = tk.Button(btn_box, text="Apply Unlocks", font=("Segoe UI", 11, "bold"),
                                   bg=self.primary_btn, fg=self.primary_txt, activebackground="#9abdf9", activeforeground="#15161e",
                                   relief="flat", pady=9, cursor="hand2", command=self.apply_action)
        self.btn_apply.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        btn_restore = tk.Button(btn_box, text="Restore Backup (.bak)", font=("Segoe UI", 10),
                                bg=self.btn_color, fg="#ffffff", activebackground=self.btn_hover, activeforeground="#ffffff",
                                relief="flat", pady=9, cursor="hand2", command=self.restore_action)
        btn_restore.pack(side=tk.RIGHT, padx=(6, 0))

    # -------------------------------------------------------------
    # Process Monitoring Loop
    # -------------------------------------------------------------
    def poll_game_process(self):
        """Polls process list periodically to update game running status."""
        proc = detect_running_game()
        self.game_proc = proc

        if proc:
            pid, name, path = proc
            path_str = f" ({os.path.basename(path)})" if path else ""
            self.lbl_game_text.config(
                text=f"ACTIVE / RUNNING - {name} (PID: {pid}){path_str}",
                fg=self.warn_color
            )
            self.btn_close_game.pack(side=tk.RIGHT)
            self.btn_apply.config(text="Close Game & Apply Unlocks")
        else:
            self.lbl_game_text.config(
                text="NOT RUNNING (Safe to modify save file)",
                fg=self.success_color
            )
            self.btn_close_game.pack_forget()
            self.btn_apply.config(text="Apply Unlocks")

        # Poll again in 1500ms
        self.after(1500, self.poll_game_process)

    def close_game_action(self):
        """Action handler for manual Close Game button."""
        if not self.game_proc:
            messagebox.showinfo("Game Status", "Risk of Rain 2 is not currently running.")
            return

        pid, name, _ = self.game_proc
        if messagebox.askyesno("Close Game", f"Do you want to close {name} (PID: {pid}) now to prevent save conflicts?"):
            if terminate_game_process(pid):
                time.sleep(0.5)
                self.poll_game_process()
                self.status_lbl.config(text="Game closed safely. Safe to apply unlocks.", fg=self.success_color)
                messagebox.showinfo("Success", f"{name} closed successfully.")
            else:
                messagebox.showerror("Error", f"Failed to terminate process {name}.")

    # -------------------------------------------------------------
    # Profile Selection Handlers
    # -------------------------------------------------------------
    def on_profile_selected(self, label):
        match = next((p for p in self.profile_list if p["label"] == label), None)
        if match:
            self.selected_profile_label.set(match["label"])
            self.selected_profile_path.set(match["path"])
            info_text = f"Profile: {match['name']} | Type: {match['type']} | Unlocks: {match['unlocks']}/205 | Lunar Coins: {match['coins']}"
            if match["is_active"]:
                info_text += " [ACTIVE SAVE]"
            self.lbl_prof_info.config(text=info_text, fg=self.accent_color)
        else:
            self.selected_profile_path.set(label)
            self.lbl_prof_info.config(text="Custom Profile File", fg=self.text_secondary)

    def refresh_profiles(self):
        self.profile_list = discover_all_profiles()
        labels = [p["label"] for p in self.profile_list] if self.profile_list else ["No profile files detected automatically"]
        self.cb_profile["values"] = labels
        if self.profile_list:
            self.on_profile_selected(self.profile_list[0]["label"])
        self.status_lbl.config(text=f"Refreshed: found {len(self.profile_list)} profile file(s).", fg="#c0caf5")

    def get_current_profile_dir(self):
        path = self.selected_profile_path.get().strip()
        if path and os.path.exists(os.path.dirname(path)):
            return os.path.dirname(path)
        if self.profile_list and os.path.exists(os.path.dirname(self.profile_list[0]["path"])):
            return os.path.dirname(self.profile_list[0]["path"])
        return None

    def browse_file(self):
        initial_dir = self.get_current_profile_dir()
        kwargs = {
            "title": "Select Risk of Rain 2 Profile XML",
            "filetypes": [("XML Profile", "*.xml"), ("All Files", "*.*")]
        }
        if initial_dir and os.path.isdir(initial_dir):
            kwargs["initialdir"] = initial_dir

        path = filedialog.askopenfilename(**kwargs)
        if path:
            fname = os.path.basename(path)
            custom_entry = {
                "label": f"Custom: {fname} ({path})",
                "path": os.path.abspath(path),
                "name": fname,
                "type": "Custom",
                "filename": fname,
                "is_active": False,
                "unlocks": 0,
                "coins": "0"
            }
            self.profile_list.insert(0, custom_entry)
            labels = [p["label"] for p in self.profile_list]
            self.cb_profile["values"] = labels
            self.on_profile_selected(custom_entry["label"])
            self.status_lbl.config(text=f"Selected: {fname}", fg="#c0caf5")

    def open_profile_folder(self):
        folder = self.get_current_profile_dir()
        if folder and os.path.isdir(folder):
            try:
                os.startfile(folder)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to open folder:\n{e}")
        else:
            messagebox.showwarning("Notice", "Profile directory could not be determined.")

    # -------------------------------------------------------------
    # Presets
    # -------------------------------------------------------------
    def preset_chars_skills(self):
        self.var_chars.set(True)
        self.var_skills.set(True)
        self.var_skins.set(False)
        self.var_items.set(False)
        self.var_artifacts.set(False)
        self.var_coins.set(True)
        self.status_lbl.config(text="Preset selected: Characters & Skills only", fg="#c0caf5")

    def preset_all(self):
        self.var_chars.set(True)
        self.var_skills.set(True)
        self.var_skins.set(True)
        self.var_items.set(True)
        self.var_artifacts.set(True)
        self.var_coins.set(True)
        self.status_lbl.config(text="Preset selected: Unlock Everything (100%)", fg=self.accent_color)

    def preset_none(self):
        self.var_chars.set(False)
        self.var_skills.set(False)
        self.var_skins.set(False)
        self.var_items.set(False)
        self.var_artifacts.set(False)
        self.var_coins.set(False)
        self.status_lbl.config(text="All options deselected", fg="#9aa5ce")

    # -------------------------------------------------------------
    # Action Handlers
    # -------------------------------------------------------------
    def apply_action(self):
        # 1. Conflict Prevention Check
        if self.game_proc:
            pid, name, _ = self.game_proc
            prompt = (
                f"CONFLICT WARNING:\n\n"
                f"{name} (PID: {pid}) is currently RUNNING!\n\n"
                f"Risk of Rain 2 keeps its save profile in RAM while running.\n"
                f"If you modify the file now, the game will overwrite it when closing,\n"
                f"causing your unlocks to be lost.\n\n"
                f"Would you like to close the game automatically before applying unlocks?\n\n"
                f"- Click [Yes] to Close Game & Apply (Recommended)\n"
                f"- Click [No] to Apply Anyway (Risk of overwrite)\n"
                f"- Click [Cancel] to abort"
            )
            res = messagebox.askyesnocancel("Game Running - Conflict Warning", prompt)
            if res is None:
                return
            elif res is True:
                terminate_game_process(pid)
                time.sleep(1.0)
                self.poll_game_process()

        selected = self.selected_profile_path.get().strip()
        targets = set()

        if selected and os.path.isfile(selected):
            targets.add(selected)

        # Partner syncing: if OnlineFix 632360 or 480 is selected, also sync the other
        if selected and os.path.isfile(selected):
            if "\\632360\\" in selected:
                alt = selected.replace("\\632360\\", "\\480\\")
                if os.path.isdir(os.path.dirname(alt)):
                    targets.add(alt)
            elif "\\480\\" in selected:
                alt = selected.replace("\\480\\", "\\632360\\")
                if os.path.isdir(os.path.dirname(alt)):
                    targets.add(alt)

        if not targets:
            messagebox.showerror("Error", "No valid profile file selected. Please click Browse to select an XML file.")
            return

        cats = []
        if self.var_chars.get(): cats.append("characters")
        if self.var_skills.get(): cats.append("skills")
        if self.var_skins.get(): cats.append("skins")
        if self.var_items.get(): cats.append("items")
        if self.var_artifacts.get(): cats.append("artifacts")

        coins_val = 2000000
        if self.var_coins.get():
            try:
                coins_val = int(self.entry_coins.get().strip())
            except ValueError:
                messagebox.showerror("Invalid Input", "Lunar coins must be a valid integer number.")
                return

        if not cats and not self.var_coins.get():
            messagebox.showwarning("Notice", "Please select at least one unlock category or enable Lunar Coins.")
            return

        try:
            total_added = 0
            backup_files = []
            for t in sorted(targets):
                added, total_active, bak_file = apply_unlocks(t, cats, set_coins=self.var_coins.get(), coins_val=coins_val)
                total_added += added
                if bak_file and bak_file not in backup_files:
                    backup_files.append(bak_file)

            self.refresh_profiles()

            msg = f"Successfully updated {len(targets)} profile(s)!\n\n"
            msg += f"- Unlocks added: {total_added}\n"
            msg += f"- Backup saved (.bak):\n  {backup_files[0] if backup_files else 'Existing .bak preserved'}\n\n"
            msg += "You can launch Risk of Rain 2 now."

            self.status_lbl.config(text=f"Success! Updated {len(targets)} profile(s). Backup saved (.bak).", fg=self.success_color)
            messagebox.showinfo("Unlocks Applied", msg)
        except Exception as e:
            self.status_lbl.config(text=f"Error: {e}", fg="#f7768e")
            messagebox.showerror("Error Applying Unlocks", f"Failed to modify profile:\n{e}")

    def restore_action(self):
        selected = self.selected_profile_path.get().strip()
        targets = [selected] if selected and os.path.isfile(selected) else [p["path"] for p in self.profile_list]

        restored = []
        for t in targets:
            success, bak = restore_backup(t)
            if success:
                restored.append(bak)

        if restored:
            self.refresh_profiles()
            self.status_lbl.config(text=f"Successfully restored {len(restored)} backup file(s).", fg=self.success_color)
            messagebox.showinfo("Backup Restored", f"Successfully restored {len(restored)} profile(s) from:\n{restored[0]}")
        else:
            self.status_lbl.config(text="No .bak backup files found for this profile.", fg="#e0af68")
            messagebox.showwarning("Notice", "No .bak backup file was found in the folder.")

if __name__ == "__main__":
    app = RoR2UnlockerApp()
    app.mainloop()
