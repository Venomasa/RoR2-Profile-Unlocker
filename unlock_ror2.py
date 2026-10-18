import os
import sys
import glob
import json
import uuid
import shutil
import xml.etree.ElementTree as ET
import winreg

# Load embedded unlock data
DATA_PATH = os.path.join(os.path.dirname(__file__), "unlock_data.json")
if os.path.exists(DATA_PATH):
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        UNLOCK_DATA = json.load(f)
else:
    UNLOCK_DATA = {"characters": [], "skills": [], "skins": [], "items": [], "artifacts": []}

def discover_all_profile_dirs():
    """
    Find all Risk of Rain 2 profile directories across:
    1. OnlineFix saves (C:\Users\Public\Documents\OnlineFix\*\Saves\UserProfiles)
    2. Steam userdata (Registry + drive roots)
    3. Other emulators
    """
    dirs = []

    # 1. OnlineFix
    for of_root in [r"C:\Users\Public\Documents\OnlineFix", r"C:\Users\Public\Documents\Steam"]:
        if os.path.isdir(of_root):
            for appid in ["632360", "480"]:
                pdir = os.path.join(of_root, appid, "Saves", "UserProfiles")
                if os.path.isdir(pdir):
                    dirs.append(pdir)

    # 2. Steam userdata
    steam_roots = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            val, _ = winreg.QueryValueEx(key, "SteamPath")
            if val: steam_roots.append(os.path.join(val.replace("/", "\\"), "userdata"))
    except Exception:
        pass

    for drive in ["C", "D", "E", "F"]:
        for sub in [r"Program Files (x86)\Steam\userdata", r"Steam\userdata"]:
            cand = rf"{drive}:\{sub}"
            if os.path.isdir(cand): steam_roots.append(cand)

    for s_root in steam_roots:
        if os.path.isdir(s_root):
            try:
                user_folders = [f for f in os.listdir(s_root) if os.path.isdir(os.path.join(s_root, f)) and f.isdigit()]
                for u in user_folders:
                    for appid in ["632360", "480"]:
                        pdir = os.path.join(s_root, u, appid, "remote", "UserProfiles")
                        dirs.append(pdir)
            except Exception:
                pass

    return list(dict.fromkeys(dirs))

def unlock_xml(xml_path, mode="chars_skills", coins=2000000):
    """Modify existing profile XML or create new unlocked XML."""
    backup_path = xml_path + ".bak"
    if os.path.exists(xml_path) and not os.path.exists(backup_path):
        shutil.copy2(xml_path, backup_path)
        print(f"  [+] Backup created: {backup_path}")

    entries = []
    entries.extend(UNLOCK_DATA["characters"])
    entries.extend(UNLOCK_DATA["skills"])
    if mode == "all":
        entries.extend(UNLOCK_DATA["skins"])
        entries.extend(UNLOCK_DATA["items"])
        entries.extend(UNLOCK_DATA["artifacts"])

    unlock_tokens = set(e["unlock"] for e in entries)
    achieve_tokens = set(e["id"] for e in entries)

    if os.path.exists(xml_path):
        tree = ET.parse(xml_path)
        root = tree.getroot()
    else:
        root = ET.Element("UserProfile")
        ET.SubElement(root, "version").text = "3"
        ET.SubElement(root, "name").text = "UnlockedPlayer"
        ET.SubElement(root, "coins").text = str(coins)
        ET.SubElement(root, "totalCollectedCoins").text = str(coins)
        tree = ET.ElementTree(root)

    # Coins
    coins_elem = root.find("coins")
    if coins_elem is None:
        coins_elem = ET.SubElement(root, "coins")
    if mode == "all" or int(coins_elem.text or "0") < coins:
        coins_elem.text = str(coins)

    tot_coins = root.find("totalCollectedCoins")
    if tot_coins is None:
        tot_coins = ET.SubElement(root, "totalCollectedCoins")
    try:
        cur_tot = int(tot_coins.text or "0")
    except ValueError:
        cur_tot = 0
    if mode == "all" or cur_tot < coins:
        tot_coins.text = str(coins)

    # Stats -> unlock
    stats_elem = root.find("stats")
    if stats_elem is None:
        stats_elem = ET.SubElement(root, "stats")

    existing_unlocks = set()
    for u in stats_elem.findall("unlock"):
        if u.text: existing_unlocks.add(u.text.strip())

    added = 0
    for tok in sorted(unlock_tokens):
        if tok not in existing_unlocks:
            el = ET.SubElement(stats_elem, "unlock")
            el.text = tok
            added += 1

    # achievementsList
    ach_elem = root.find("achievementsList")
    if ach_elem is None:
        ach_elem = ET.SubElement(root, "achievementsList")
    current_achs = set((ach_elem.text or "").split())
    merged_achs = current_achs.union(achieve_tokens)
    ach_elem.text = " ".join(sorted(merged_achs))

    # viewedUnlockablesList
    viewed_elem = root.find("viewedUnlockablesList")
    if viewed_elem is None:
        viewed_elem = ET.SubElement(root, "viewedUnlockablesList")
    current_viewed = set((viewed_elem.text or "").split())
    merged_viewed = current_viewed.union(unlock_tokens)
    viewed_elem.text = " ".join(sorted(merged_viewed))

    # Clear unviewedAchievementsList
    unviewed = root.find("unviewedAchievementsList")
    if unviewed is not None:
        unviewed.text = ""

    ET.indent(tree, space="  ", level=0)
    tree.write(xml_path, encoding="utf-8", xml_declaration=True)
    return added, len(existing_unlocks) + added

def main():
    mode = "chars_skills"
    coins = 2000000

    if len(sys.argv) > 1 and sys.argv[1] in ["all", "100"]:
        mode = "all"

    print("=" * 60)
    print("  Risk of Rain 2 - Profile Unlocker (OFME & Steam)")
    print(f"  Mode: {'Unlock Everything (100%)' if mode == 'all' else 'Characters & Skills Only'}")
    print("=" * 60)

    target_dirs = discover_all_profile_dirs()
    if not target_dirs:
        print("[-] No save directories found.")
        sys.exit(1)

    print(f"[*] Found {len(target_dirs)} profile folder candidates.")

    total_files_modified = 0
    for pdir in target_dirs:
        if not os.path.isdir(pdir):
            continue
        xmls = [x for x in glob.glob(os.path.join(pdir, "*.xml")) if not x.endswith(".bak")]
        if not xmls:
            # Create a profile if directory exists but empty
            new_file = os.path.join(pdir, f"{uuid.uuid4()}.xml")
            added, total = unlock_xml(new_file, mode, coins)
            print(f"[+] Created and unlocked: {new_file} (+{added} unlocks)")
            total_files_modified += 1
        else:
            for x in xmls:
                added, total = unlock_xml(x, mode, coins)
                print(f"[+] Updated: {x} (+{added} added, {total} total unlocks)")
                total_files_modified += 1

    print("\n" + "=" * 60)
    print(f"  Done! Successfully processed {total_files_modified} profile file(s).")
    print("  Backups were saved with extension .bak")
    print("=" * 60)

if __name__ == "__main__":
    main()
