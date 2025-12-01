# MemoryMate-PhotoFlow Build & Split Script
# Builds the application with PyInstaller and splits into manageable parts
# =============================================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MemoryMate-PhotoFlow Build & Split" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Build with PyInstaller
Write-Host "[1/3] Building with PyInstaller..." -ForegroundColor Yellow
Write-Host "Command: pyinstaller memorymate_pyinstaller.spec --clean --noconfirm" -ForegroundColor Gray
Write-Host ""

pyinstaller memorymate_pyinstaller.spec --clean --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "❌ PyInstaller build FAILED!" -ForegroundColor Red
    Write-Host "Check errors above and fix before continuing." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "✓ Build completed successfully!" -ForegroundColor Green
Write-Host ""

# Step 2: Verify output file exists
$exePath = "dist\MemoryMate-PhotoFlow-v3.0.1.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "❌ ERROR: Output file not found: $exePath" -ForegroundColor Red
    Write-Host "Expected one-file build, but exe is missing." -ForegroundColor Red
    exit 1
}

# Get file size
$fileSize = (Get-Item $exePath).Length
$fileSizeMB = [math]::Round($fileSize / 1MB, 2)

Write-Host "[2/3] Splitting executable into parts..." -ForegroundColor Yellow
Write-Host "File: $exePath" -ForegroundColor Gray
Write-Host "Size: $fileSizeMB MB ($fileSize bytes)" -ForegroundColor Gray
Write-Host ""

# Calculate part size (split into 5 parts, ~180MB each for 900MB file)
$numParts = 5
$partSize = [math]::Ceiling($fileSize / $numParts)
$partSizeMB = [math]::Round($partSize / 1MB, 2)

Write-Host "Splitting into $numParts parts (~$partSizeMB MB each)..." -ForegroundColor Cyan

# Create output directory for parts
$outputDir = "dist\MemoryMate-Parts"
if (Test-Path $outputDir) {
    Remove-Item $outputDir -Recurse -Force
}
New-Item -ItemType Directory -Path $outputDir | Out-Null

# Read file as bytes
$fileBytes = [System.IO.File]::ReadAllBytes($exePath)
$totalBytes = $fileBytes.Length

# Split into parts
for ($i = 0; $i -lt $numParts; $i++) {
    $partNum = $i + 1
    $startIndex = $i * $partSize
    $endIndex = [math]::Min(($i + 1) * $partSize, $totalBytes)
    $length = $endIndex - $startIndex
    
    $partFileName = "MemoryMate-PhotoFlow-v3.0.1.exe.part$partNum"
    $partPath = Join-Path $outputDir $partFileName
    
    # Extract bytes for this part
    $partBytes = New-Object byte[] $length
    [Array]::Copy($fileBytes, $startIndex, $partBytes, 0, $length)
    
    # Write to file
    [System.IO.File]::WriteAllBytes($partPath, $partBytes)
    
    $partSizeActual = [math]::Round($length / 1MB, 2)
    Write-Host "  ✓ Part $partNum/$numParts : $partFileName ($partSizeActual MB)" -ForegroundColor Green
}

Write-Host ""
Write-Host "✓ Split completed successfully!" -ForegroundColor Green
Write-Host ""

# Step 3: Create merge script for target PC
Write-Host "[3/3] Creating merge script for target PC..." -ForegroundColor Yellow

$mergeScriptContent = @"
# MemoryMate-PhotoFlow Merge Script
# Merges split parts back into single executable
# =============================================================================
# INSTRUCTIONS:
# 1. Copy all .part1, .part2, .part3, .part4, .part5 files to the same folder
# 2. Copy this merge.ps1 script to the same folder
# 3. Right-click merge.ps1 → Run with PowerShell
# 4. Wait for merge to complete
# 5. Run MemoryMate-PhotoFlow-v3.0.1.exe
# =============================================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MemoryMate-PhotoFlow Merge Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Get all part files
`$partFiles = Get-ChildItem -Filter "MemoryMate-PhotoFlow-v3.0.1.exe.part*" | Sort-Object Name

if (`$partFiles.Count -eq 0) {
    Write-Host "❌ ERROR: No part files found!" -ForegroundColor Red
    Write-Host "Make sure all .part1, .part2, etc. files are in this folder." -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Found `$(`$partFiles.Count) part files:" -ForegroundColor Cyan
foreach (`$part in `$partFiles) {
    `$sizeMB = [math]::Round(`$part.Length / 1MB, 2)
    Write-Host "  - `$(`$part.Name) (`$sizeMB MB)" -ForegroundColor Gray
}
Write-Host ""

# Verify we have all parts (1 to 5)
`$expectedParts = 5
if (`$partFiles.Count -ne `$expectedParts) {
    Write-Host "⚠️  WARNING: Expected `$expectedParts parts, but found `$(`$partFiles.Count)" -ForegroundColor Yellow
    Write-Host "Some parts may be missing. Continuing anyway..." -ForegroundColor Yellow
    Write-Host ""
}

# Output file
`$outputFile = "MemoryMate-PhotoFlow-v3.0.1.exe"

# Check if output already exists
if (Test-Path `$outputFile) {
    Write-Host "⚠️  Output file already exists: `$outputFile" -ForegroundColor Yellow
    `$overwrite = Read-Host "Overwrite? (y/n)"
    if (`$overwrite -ne "y") {
        Write-Host "Cancelled." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 0
    }
    Remove-Item `$outputFile -Force
}

Write-Host "Merging parts into `$outputFile..." -ForegroundColor Cyan
Write-Host ""

# Create output stream
`$outputStream = [System.IO.File]::Create(`$outputFile)

try {
    `$partNum = 0
    foreach (`$partFile in `$partFiles) {
        `$partNum++
        Write-Host "  [``$partNum/`$(`$partFiles.Count)] Merging `$(`$partFile.Name)..." -ForegroundColor Yellow -NoNewline
        
        # Read part bytes
        `$partBytes = [System.IO.File]::ReadAllBytes(`$partFile.FullName)
        
        # Write to output
        `$outputStream.Write(`$partBytes, 0, `$partBytes.Length)
        
        Write-Host " ✓" -ForegroundColor Green
    }
}
finally {
    `$outputStream.Close()
}

Write-Host ""

# Verify output file
if (Test-Path `$outputFile) {
    `$finalSize = (Get-Item `$outputFile).Length
    `$finalSizeMB = [math]::Round(`$finalSize / 1MB, 2)
    
    Write-Host "✓ Merge completed successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Output file: `$outputFile" -ForegroundColor Cyan
    Write-Host "Final size: `$finalSizeMB MB (`$finalSize bytes)" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "========================================" -ForegroundColor Green
    Write-Host "You can now run: .\`$outputFile" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
} else {
    Write-Host "❌ ERROR: Merge failed - output file not created" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"
"@

$mergeScriptPath = Join-Path $outputDir "merge.ps1"
Set-Content -Path $mergeScriptPath -Value $mergeScriptContent -Encoding UTF8

Write-Host "✓ Merge script created: $mergeScriptPath" -ForegroundColor Green

# Also copy the batch file merge script for compatibility
$mergeBatSource = "merge.bat"
if (Test-Path $mergeBatSource) {
    $mergeBatDest = Join-Path $outputDir "merge.bat"
    Copy-Item $mergeBatSource $mergeBatDest
    Write-Host "✓ Batch merge script copied: $mergeBatDest" -ForegroundColor Green
}

Write-Host ""

# Step 4: Create README
$readmePath = Join-Path $outputDir "README.txt"
$readmeContent = @"
MemoryMate-PhotoFlow v3.0.1 - Split Installation Package
========================================================

CONTENTS:
---------
✓ MemoryMate-PhotoFlow-v3.0.1.exe.part1 (~$partSizeMB MB)
✓ MemoryMate-PhotoFlow-v3.0.1.exe.part2 (~$partSizeMB MB)
✓ MemoryMate-PhotoFlow-v3.0.1.exe.part3 (~$partSizeMB MB)
✓ MemoryMate-PhotoFlow-v3.0.1.exe.part4 (~$partSizeMB MB)
✓ MemoryMate-PhotoFlow-v3.0.1.exe.part5 (~$partSizeMB MB)
✓ merge.bat (Batch merge script - EASIEST, works everywhere)
✓ merge.ps1 (PowerShell merge script - advanced)
✓ README.txt (This file)

INSTALLATION INSTRUCTIONS (EASY METHOD):
-----------------------------------------
1. Copy ALL files from this folder to your target PC
   (You can transfer via USB drive, email, cloud storage, etc.)

2. On the target PC, place all files in the same folder

3. Double-click "merge.bat" 
   (This is the simplest method - no PowerShell needed!)

4. Wait for the merge to complete (~10-30 seconds)

5. After merge completes, you'll have: MemoryMate-PhotoFlow-v3.0.1.exe

6. Double-click the .exe to run the application

ALTERNATIVE METHOD (PowerShell):
--------------------------------
If you prefer PowerShell:

1. Right-click "merge.ps1" → Run with PowerShell
   (If blocked, see troubleshooting below)

2. Wait for merge to complete

3. Run MemoryMate-PhotoFlow-v3.0.1.exe

TROUBLESHOOTING:
----------------
If PowerShell says "Execution policy" error:

  Option A (Temporary bypass):
    Right-click merge.ps1 → Open with → PowerShell
    Then run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    Then run: .\merge.ps1

  Option B (One-time run):
    Open PowerShell in the folder
    Run: powershell -ExecutionPolicy Bypass -File merge.ps1

MANUAL MERGE (Alternative):
----------------------------
If PowerShell script doesn't work, you can merge manually:

  Windows Command Prompt:
    copy /b MemoryMate-PhotoFlow-v3.0.1.exe.part1 + MemoryMate-PhotoFlow-v3.0.1.exe.part2 + MemoryMate-PhotoFlow-v3.0.1.exe.part3 + MemoryMate-PhotoFlow-v3.0.1.exe.part4 + MemoryMate-PhotoFlow-v3.0.1.exe.part5 MemoryMate-PhotoFlow-v3.0.1.exe

  Linux/Mac:
    cat MemoryMate-PhotoFlow-v3.0.1.exe.part* > MemoryMate-PhotoFlow-v3.0.1.exe

TECHNICAL DETAILS:
------------------
Original size: $fileSizeMB MB
Split into: $numParts parts
Part size: ~$partSizeMB MB each
Build date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Python version: $(python --version 2>&1)
PyInstaller mode: One-file (encrypted bytecode)

SYSTEM REQUIREMENTS:
--------------------
- Windows 10/11 (64-bit)
- No Python installation required
- ~2 GB free disk space (for temp extraction)
- ~4 GB RAM recommended

FEATURES:
---------
✓ Photo organization and management
✓ Face detection and recognition (InsightFace AI)
✓ Video support (MP4, MOV, AVI, etc.)
✓ RAW photo support (CR2, NEF, ARW, DNG)
✓ HEIC/HEIF support (iPhone photos)
✓ Google Photos-style lightbox viewer
✓ Smart photo enhancement presets
✓ Metadata extraction (EXIF, GPS)
✓ Device import (MTP, USB, SD cards)

CONTACT:
--------
For issues or questions, check the application logs:
  - Console output (if any errors on startup)
  - app_log.txt (created in application folder)

Built with: Python 3.10, PySide6, InsightFace, OpenCV
License: See application about dialog

========================================================
"@

Set-Content -Path $readmePath -Value $readmeContent -Encoding UTF8

Write-Host "✓ README created: $readmePath" -ForegroundColor Green
Write-Host ""

# Step 5: Summary
Write-Host "========================================" -ForegroundColor Green
Write-Host "BUILD & SPLIT COMPLETED!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Output location: $outputDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "Files created:" -ForegroundColor White
Write-Host "  ✓ MemoryMate-PhotoFlow-v3.0.1.exe.part1" -ForegroundColor Gray
Write-Host "  ✓ MemoryMate-PhotoFlow-v3.0.1.exe.part2" -ForegroundColor Gray
Write-Host "  ✓ MemoryMate-PhotoFlow-v3.0.1.exe.part3" -ForegroundColor Gray
Write-Host "  ✓ MemoryMate-PhotoFlow-v3.0.1.exe.part4" -ForegroundColor Gray
Write-Host "  ✓ MemoryMate-PhotoFlow-v3.0.1.exe.part5" -ForegroundColor Gray
Write-Host "  ✓ merge.ps1 (PowerShell merge script)" -ForegroundColor Gray
Write-Host "  ✓ merge.bat (Batch merge script - works anywhere)" -ForegroundColor Gray
Write-Host "  ✓ README.txt (Instructions)" -ForegroundColor Gray
Write-Host ""
Write-Host "NEXT STEPS:" -ForegroundColor Yellow
Write-Host "1. Copy entire '$outputDir' folder to target PC" -ForegroundColor White
Write-Host "2. On target PC, run: merge.ps1" -ForegroundColor White
Write-Host "3. After merge, run: MemoryMate-PhotoFlow-v3.0.1.exe" -ForegroundColor White
Write-Host ""
Write-Host "========================================" -ForegroundColor Green

# Optional: Open output folder
$openFolder = Read-Host "Open output folder now? (y/n)"
if ($openFolder -eq "y") {
    Start-Process explorer.exe -ArgumentList $outputDir
}
