# MemoryMate-PhotoFlow v3.0.1 - Build & Deployment Guide

Complete guide for building and deploying the application with automatic file splitting for easy transfer.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Build Process](#build-process)
4. [Transfer Methods](#transfer-methods)
5. [Target PC Installation](#target-pc-installation)
6. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

This guide covers:
- ✅ Building a single-file executable (~900 MB)
- ✅ Automatically splitting into 5 parts (~180 MB each)
- ✅ Easy transfer via USB/email/cloud
- ✅ Simple merge on target PC (NO Python needed)
- ✅ Maximum code protection (AES-256 encryption)

**Key Features:**
- One-file executable (all dependencies embedded)
- Bytecode-only distribution (no .py source files)
- UPX compression (obfuscates structure)
- Automatic HEIC/HEIF support (iPhone photos)
- RAW photo support (Canon CR2, Nikon NEF, etc.)
- Face detection with InsightFace AI
- No console window (professional appearance)

**Note:** PyInstaller 6.0+ removed AES bytecode encryption. Alternative protection methods are still active (see Security section below).

---

## 🔧 Prerequisites

### On Development PC (where you build):

#### 1. Python 3.10
```powershell
python --version
# Should show: Python 3.10.x
```

#### 2. Install Dependencies
```powershell
# Install all requirements
pip install -r requirements.txt

# Install RAW support
pip install rawpy

# Install PyInstaller
pip install pyinstaller
```

#### 3. FFmpeg (for video support)
- Download: https://ffmpeg.org/download.html
- Add to PATH
- Verify: `ffmpeg -version`

#### 4. InsightFace Models (for face detection)
Option A: Run app once to auto-download
```powershell
python main_qt.py
# Open Settings → Enable face detection → Scan a folder
```

Option B: Manual download
```powershell
python utils/download_face_models.py
```

Models location: `C:\Users\<YOU>\.insightface\models\buffalo_l\`

---

## 🏗️ Build Process

### Step 1: Verify Environment

Run the verification script:
```powershell
.\verify_build_ready.ps1
```

This checks:
- ✅ Python version
- ✅ PyInstaller installed
- ✅ Required packages
- ✅ FFmpeg on PATH
- ✅ InsightFace models
- ✅ Spec file configuration
- ✅ App icon
- ✅ Disk space (need 5+ GB free)

**Fix any ❌ errors before proceeding!**

---

### Step 2: Build & Split

Run the automated build script:
```powershell
.\build_and_split.ps1
```

**What it does:**
1. Runs PyInstaller with clean build
2. Creates single .exe (~900 MB)
3. Splits into 5 parts (~180 MB each)
4. Generates merge scripts (PowerShell + Batch)
5. Creates README with instructions

**Output location:**
```
dist\MemoryMate-Parts\
├── MemoryMate-PhotoFlow-v3.0.1.exe.part1  (~180 MB)
├── MemoryMate-PhotoFlow-v3.0.1.exe.part2  (~180 MB)
├── MemoryMate-PhotoFlow-v3.0.1.exe.part3  (~180 MB)
├── MemoryMate-PhotoFlow-v3.0.1.exe.part4  (~180 MB)
├── MemoryMate-PhotoFlow-v3.0.1.exe.part5  (~180 MB)
├── merge.bat                               (Batch merge script)
├── merge.ps1                               (PowerShell merge script)
└── README.txt                              (Instructions)
```

**Build time:** 5-10 minutes (depending on your PC)

---

## 📤 Transfer Methods

Choose the method that works best for you:

### Method 1: USB Drive (Fastest)
```
1. Copy entire MemoryMate-Parts folder to USB
2. Plug USB into target PC
3. Copy folder to target PC
4. Done!
```

### Method 2: Cloud Storage (Most Reliable)
```
Google Drive / OneDrive / Dropbox:
1. Upload MemoryMate-Parts folder
2. Share folder link
3. Download on target PC
4. Done!
```

### Method 3: Email (If Size Allows)
```
Corporate email (if limit allows):
1. Send 5 separate emails (one part per email)
2. Also email merge.bat and README.txt
3. Download all on target PC
4. Put in same folder
```

### Method 4: FTP / Network Share
```
If you have network access:
1. Copy to shared network location
2. Access from target PC
3. Copy locally
```

---

## 💻 Target PC Installation

### Requirements
- Windows 10/11 (64-bit)
- ~2 GB free disk space (for temp extraction)
- NO Python needed!
- NO additional software needed!

### Step 1: Copy Files
Copy all files from `MemoryMate-Parts` to a folder on the target PC:
```
C:\MemoryMate\   (or any location you prefer)
├── MemoryMate-PhotoFlow-v3.0.1.exe.part1
├── MemoryMate-PhotoFlow-v3.0.1.exe.part2
├── MemoryMate-PhotoFlow-v3.0.1.exe.part3
├── MemoryMate-PhotoFlow-v3.0.1.exe.part4
├── MemoryMate-PhotoFlow-v3.0.1.exe.part5
├── merge.bat
├── merge.ps1
└── README.txt
```

### Step 2: Merge (EASIEST METHOD)
**Double-click:** `merge.bat`

That's it! Wait ~30 seconds for merge to complete.

### Step 2: Merge (Alternative - PowerShell)
**Right-click:** `merge.ps1` → **Run with PowerShell**

If blocked by execution policy:
```powershell
powershell -ExecutionPolicy Bypass -File merge.ps1
```

### Step 3: Run Application
**Double-click:** `MemoryMate-PhotoFlow-v3.0.1.exe`

**First launch:**
- Extracts to `C:\Users\<YOU>\AppData\Local\Temp\_MEI*`
- Takes ~10-15 seconds
- Subsequent launches are faster (~3-5 seconds)

### Step 4: Cleanup (Optional)
After verifying the app works:
```
Delete:
- MemoryMate-PhotoFlow-v3.0.1.exe.part1
- MemoryMate-PhotoFlow-v3.0.1.exe.part2
- MemoryMate-PhotoFlow-v3.0.1.exe.part3
- MemoryMate-PhotoFlow-v3.0.1.exe.part4
- MemoryMate-PhotoFlow-v3.0.1.exe.part5
- merge.bat
- merge.ps1
- README.txt

Keep:
- MemoryMate-PhotoFlow-v3.0.1.exe  (this is your application!)
```

**Create desktop shortcut** (optional):
1. Right-click `.exe` → Send to → Desktop (create shortcut)
2. Rename to "MemoryMate PhotoFlow"

---

## 🐛 Troubleshooting

### Build Issues

#### ❌ PyInstaller fails
```powershell
# Reinstall PyInstaller
pip uninstall pyinstaller
pip install pyinstaller

# Try clean build
pyinstaller memorymate_pyinstaller.spec --clean
```

#### ❌ Missing modules
```powershell
# Reinstall all dependencies
pip install -r requirements.txt --upgrade
pip install rawpy
```

#### ❌ FFmpeg not found
```powershell
# Check FFmpeg on PATH
ffmpeg -version

# If not found, download and add to PATH:
# https://ffmpeg.org/download.html
```

#### ❌ Out of disk space
```
Need at least 5 GB free:
- 900 MB for .exe
- 900 MB for split parts
- 2 GB for temp PyInstaller files
- 1 GB buffer
```

---

### Transfer Issues

#### ⚠️ File corruption during transfer
```
Verify file sizes match:
- part1: ~180 MB
- part2: ~180 MB
- part3: ~180 MB
- part4: ~180 MB
- part5: ~180 MB

If sizes differ:
- Re-download corrupted part
- Or rebuild and re-transfer
```

#### ⚠️ Email blocks attachments
```
Gmail/Outlook block large files:
- Use Google Drive/OneDrive instead
- Share download link
- Or compress with 7-Zip (.7z format)
```

---

### Merge Issues

#### ❌ merge.bat fails
```
Check:
1. All 5 .part files in same folder
2. Files not corrupted (verify sizes)
3. Enough disk space (~900 MB)
4. Run as Administrator (if needed)
```

#### ❌ PowerShell execution policy blocked
```powershell
# Temporary bypass (safe):
powershell -ExecutionPolicy Bypass -File merge.ps1

# Or use merge.bat instead (no restrictions)
```

#### ❌ Merged .exe is wrong size
```
Expected: ~900 MB

If different:
- Delete merged .exe
- Re-run merge script
- If still wrong, re-transfer .part files
```

---

### Runtime Issues

#### ❌ App won't start
```
1. Check Windows version: 10/11 64-bit
2. Check disk space: need ~2 GB for temp extraction
3. Check antivirus: may block UPX-compressed exe
4. Run as Administrator (if needed)
```

#### ⚠️ Antivirus flags as malware
```
False positive due to:
- UPX compression
- Encrypted bytecode
- Self-extracting executable

Fix:
1. Add exception in antivirus
2. Or sign exe with code signing certificate
```

#### ❌ "Missing DLL" error
```
Very rare - means PyInstaller didn't bundle dependency

Fix:
1. Rebuild with --clean flag
2. Check hiddenimports in spec file
3. Install Visual C++ Redistributable:
   https://aka.ms/vs/17/release/vc_redist.x64.exe
```

#### ❌ Face detection errors on HEIC photos
```
This should now be FIXED! But if still occurring:

1. Check pillow-heif version: pip show pillow-heif
   - Should be 1.1.0+
2. Check logs for HEIC support message
3. Test with standard JPEG (to isolate issue)
```

---

## 📊 What's Inside the .exe

**Total size:** ~900 MB

**Components:**
- Python 3.10 runtime (~50 MB)
- PySide6 Qt framework (~200 MB)
- InsightFace AI models (~400 MB)
  - buffalo_l face detection
  - ArcFace recognition
- OpenCV (~100 MB)
- NumPy, scikit-learn (~50 MB)
- Application code (encrypted, ~10 MB)
- Other dependencies (~90 MB)

**At runtime:**
- Extracts to temp: `C:\Users\<YOU>\AppData\Local\Temp\_MEI<random>\`
- Uses ~2 GB disk space temporarily
- Cleaned up on exit (automatic)

---

## 🔒 Security & Code Protection

**Protection features enabled:**
- ✅ Bytecode-only distribution (no .py source files)
- ✅ One-file mode (harder to extract)
- ✅ UPX compression (obfuscates structure)
- ✅ Compiled .pyc files (not human-readable)

**PyInstaller 6.0+ Changes:**
- ⚠️ AES bytecode encryption removed (no longer supported)
- ✅ Still provides good protection for most use cases
- ✅ For maximum protection, consider PyArmor or Nuitka (see below)

**What attackers CAN'T easily do:**
- ❌ View your original Python code
- ❌ Extract .py files
- ❌ Read code with text editor
- ❌ Quickly understand algorithms

**What determined attackers CAN do (with significant effort):**
- ⚠️ Decompile .pyc bytecode (80-90% accuracy, loses comments/variable names)
- ⚠️ Extract from temp folder during runtime (brief window)
- ⚠️ Reverse engineer .exe (requires IDA Pro/Ghidra expertise, very time-consuming)

**For maximum protection**, see QUICK_START.txt section on Cython compilation for critical modules.

---

## 📞 Support

**If build fails:**
1. Run `verify_build_ready.ps1` to check environment
2. Check error messages in console
3. Review this guide's troubleshooting section

**If app crashes on target PC:**
1. Check `app_log.txt` in application folder
2. Run with console enabled (set `console=True` in spec, rebuild)
3. Review error messages

**For face detection issues:**
- Now supports HEIC/HEIF (iPhone photos)
- Now supports RAW (CR2, NEF, ARW, DNG)
- Check logs for format-specific errors

---

## ✅ Quick Reference

### Build Commands
```powershell
# Verify environment
.\verify_build_ready.ps1

# Build and split
.\build_and_split.ps1

# Manual build (no split)
pyinstaller memorymate_pyinstaller.spec --clean --noconfirm
```

### Target PC Commands
```batch
REM Easiest method
merge.bat

REM PowerShell method
merge.ps1
```

### File Sizes
- Single .exe: ~900 MB
- Each part: ~180 MB
- Total (parts): ~900 MB
- After merge: ~900 MB

### System Requirements
- **Development PC:** Python 3.10, 5+ GB free space
- **Target PC:** Windows 10/11 64-bit, 2+ GB free space, NO Python needed

---

**Built:** 2025-11-30  
**Version:** v3.0.1  
**License:** See application about dialog

---
