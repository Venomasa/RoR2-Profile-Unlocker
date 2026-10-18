# Risk of Rain 2 Profile Unlocker (PowerShell)
# Compatible with v1.5.0 and OnlineFix / Steam

param (
    [string]$Mode = "chars_skills", # 'chars_skills' or 'all'
    [int]$Coins = 2000000,
    [string]$CustomPath = ""
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$jsonPath = Join-Path $scriptDir "unlock_data.json"

if (-not (Test-Path $jsonPath)) {
    Write-Host "[-] unlock_data.json not found in $scriptDir" -ForegroundColor Red
    exit 1
}

$unlockData = Get-Content -Raw -Path $jsonPath -Encoding UTF8 | ConvertFrom-Json

$targetDirs = @()

# 1. OnlineFix directories
foreach ($ofRoot in @("C:\Users\Public\Documents\OnlineFix", "C:\Users\Public\Documents\Steam")) {
    if (Test-Path $ofRoot) {
        foreach ($appId in @("632360", "480")) {
            $pdir = Join-Path $ofRoot "$appId\Saves\UserProfiles"
            if (Test-Path $pdir) { $targetDirs += $pdir }
        }
    }
}

# 2. Steam userdata
$userdataCandidates = @()
try {
    $steamPath = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
    if ($steamPath) { $userdataCandidates += (Join-Path $steamPath.Replace('/', '\') "userdata") }
} catch {}

$userdataCandidates += @(
    "C:\Program Files (x86)\Steam\userdata",
    "C:\Program Files\Steam\userdata",
    "D:\Steam\userdata",
    "E:\Steam\userdata"
)

if ($CustomPath -and (Test-Path $CustomPath)) {
    if ((Test-Path $CustomPath -PathType Container) -and (Get-ChildItem -Path $CustomPath -Filter "*.xml")) {
        $targetDirs += $CustomPath
    } else {
        $userdataCandidates = @($CustomPath)
    }
}

foreach ($cand in $userdataCandidates) {
    if (Test-Path $cand) {
        Get-ChildItem -Path $cand -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^\d+$' } | ForEach-Object {
            $userFolder = $_.FullName
            foreach ($appId in @("632360", "480")) {
                $pdir = Join-Path $userFolder "$appId\remote\UserProfiles"
                $targetDirs += $pdir
            }
        }
    }
}

$targetDirs = $targetDirs | Sort-Object -Unique

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Risk of Rain 2 - Profile Unlocker (v1.5.0 Compatible)" -ForegroundColor Yellow
Write-Host "  Mode: $(if ($Mode -eq 'all') { 'Unlock Everything (100%)' } else { 'Characters & Skills Only' })" -ForegroundColor Cyan
Write-Host "  Found $( $targetDirs.Count ) profile directory candidate(s)." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

$allEntries = @()
$allEntries += $unlockData.characters
$allEntries += $unlockData.skills
if ($Mode -eq "all") {
    $allEntries += $unlockData.skins
    $allEntries += $unlockData.items
    $allEntries += $unlockData.artifacts
}

$unlockTokens = ($allEntries | ForEach-Object { $_.unlock }) | Sort-Object -Unique
$achieveTokens = ($allEntries | ForEach-Object { $_.id }) | Sort-Object -Unique

$processed = 0

foreach ($pdir in $targetDirs) {
    if (-not (Test-Path $pdir)) {
        continue
    }

    $xmls = Get-ChildItem -Path $pdir -Filter "*.xml" -ErrorAction SilentlyContinue | Where-Object { -not $_.Name.EndsWith(".bak") }
    if (-not $xmls) {
        continue
    }

    foreach ($xmlFile in $xmls) {
        $path = $xmlFile.FullName
        $bak = $path + ".bak"
        if (-not (Test-Path $bak)) {
            Copy-Item -Path $path -Destination $bak -Force
            Write-Host "  [+] Backup created: $bak" -ForegroundColor DarkGray
        }

        [xml]$xmlDoc = Get-Content -Path $path -Raw -Encoding UTF8

        # 1. Update Coins
        $coinsNode = $xmlDoc.SelectSingleNode("//coins")
        if (-not $coinsNode) {
            $coinsNode = $xmlDoc.CreateElement("coins")
            $xmlDoc.UserProfile.AppendChild($coinsNode) | Out-Null
        }
        $coinsNode.InnerText = [string]$Coins

        $totCoinsNode = $xmlDoc.SelectSingleNode("//totalCollectedCoins")
        if (-not $totCoinsNode) {
            $totCoinsNode = $xmlDoc.CreateElement("totalCollectedCoins")
            $xmlDoc.UserProfile.AppendChild($totCoinsNode) | Out-Null
        }
        $curTot = 0
        [int]::TryParse($totCoinsNode.InnerText, [ref]$curTot) | Out-Null
        if ($curTot -lt $Coins) {
            $totCoinsNode.InnerText = [string]$Coins
        }

        # 2. Stats unlocks
        $statsNode = $xmlDoc.SelectSingleNode("//stats")
        if (-not $statsNode) {
            $statsNode = $xmlDoc.CreateElement("stats")
            $xmlDoc.UserProfile.AppendChild($statsNode) | Out-Null
        }

        $existing = @{}
        $statsNode.SelectNodes("unlock") | ForEach-Object {
            if ($_.InnerText) { $existing[$_.InnerText.Trim()] = $true }
        }

        $added = 0
        foreach ($tok in $unlockTokens) {
            if (-not $existing.ContainsKey($tok)) {
                $el = $xmlDoc.CreateElement("unlock")
                $el.InnerText = $tok
                $statsNode.AppendChild($el) | Out-Null
                $added++
            }
        }

        # 3. achievementsList
        $achNode = $xmlDoc.SelectSingleNode("//achievementsList")
        if (-not $achNode) {
            $achNode = $xmlDoc.CreateElement("achievementsList")
            $xmlDoc.UserProfile.AppendChild($achNode) | Out-Null
        }
        $currentAchs = @()
        if ($achNode.InnerText) {
            $currentAchs = $achNode.InnerText.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
        }
        $mergedAchs = ($currentAchs + $achieveTokens) | Sort-Object -Unique
        $achNode.InnerText = ($mergedAchs -join " ")

        # 4. viewedUnlockablesList
        $viewedNode = $xmlDoc.SelectSingleNode("//viewedUnlockablesList")
        if (-not $viewedNode) {
            $viewedNode = $xmlDoc.CreateElement("viewedUnlockablesList")
            $xmlDoc.UserProfile.AppendChild($viewedNode) | Out-Null
        }
        $currentViewed = @()
        if ($viewedNode.InnerText) {
            $currentViewed = $viewedNode.InnerText.Split(' ', [System.StringSplitOptions]::RemoveEmptyEntries)
        }
        $mergedViewed = ($currentViewed + $unlockTokens) | Sort-Object -Unique
        $viewedNode.InnerText = ($mergedViewed -join " ")

        # 5. Clear unviewedAchievementsList
        $unviewed = $xmlDoc.SelectSingleNode("//unviewedAchievementsList")
        if ($unviewed) {
            $unviewed.InnerText = ""
        }

        $xmlDoc.Save($path)
        Write-Host "[+] Successfully unlocked: $path (+ $added unlocks added)" -ForegroundColor Green
        $processed++
    }
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Finished! Updated $processed profile file(s)." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan
