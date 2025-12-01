# Pre-Build Verification Script
# Checks all requirements before running PyInstaller build
# =============================================================================

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Pre-Build Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allGood = $true

# Check 1: Python version
Write-Host "[1/8] Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($pythonVersion -match "Python 3\.10") {
    Write-Host "  ✓ $pythonVersion" -ForegroundColor Green
} elseif ($pythonVersion -match "Python 3\.(9|11|12)") {
    Write-Host "  ⚠ $pythonVersion (recommended: 3.10)" -ForegroundColor Yellow
} else {
    Write-Host "  ✗ $pythonVersion (required: Python 3.9+)" -ForegroundColor Red
    $allGood = $false
}

# Check 2: PyInstaller
Write-Host "[2/8] Checking PyInstaller..." -ForegroundColor Yellow
try {
    $pyiVersion = pyinstaller --version 2>&1
    $versionNum = [version]($pyiVersion -replace '[^0-9.]', '')
    
    if ($versionNum.Major -ge 6) {
        Write-Host "  ✓ PyInstaller $pyiVersion" -ForegroundColor Green
        Write-Host "    ⚠️ Note: v6.0+ removed AES bytecode encryption" -ForegroundColor Yellow
        Write-Host "    Still protected: UPX compression, one-file mode, bytecode-only" -ForegroundColor Gray
    } else {
        Write-Host "  ✓ PyInstaller $pyiVersion (older version)" -ForegroundColor Green
    }
} catch {
    Write-Host "  ✗ PyInstaller not found" -ForegroundColor Red
    Write-Host "    Install: pip install pyinstaller" -ForegroundColor Gray
    $allGood = $false
}

# Check 3: Critical packages
Write-Host "[3/8] Checking required packages..." -ForegroundColor Yellow
$requiredPackages = @(
    "PySide6",
    "Pillow",
    "pillow-heif",
    "opencv-python",
    "insightface",
    "onnxruntime",
    "scikit-learn",
    "numpy",
    "matplotlib",
    "rawpy"
)

foreach ($pkg in $requiredPackages) {
    $installed = pip show $pkg 2>&1
    if ($installed -match "Version:") {
        $version = ($installed | Select-String "Version:").ToString().Split(":")[1].Trim()
        Write-Host "  ✓ $pkg $version" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $pkg NOT INSTALLED" -ForegroundColor Red
        $allGood = $false
    }
}

# Check 4: FFmpeg
Write-Host "[4/8] Checking FFmpeg..." -ForegroundColor Yellow
try {
    $ffmpegVersion = ffmpeg -version 2>&1 | Select-Object -First 1
    if ($ffmpegVersion -match "ffmpeg version") {
        Write-Host "  ✓ FFmpeg found" -ForegroundColor Green
        Write-Host "    $($ffmpegVersion.Substring(0, [Math]::Min(60, $ffmpegVersion.Length)))" -ForegroundColor Gray
    } else {
        throw "FFmpeg not responding"
    }
} catch {
    Write-Host "  ✗ FFmpeg NOT on PATH" -ForegroundColor Red
    Write-Host "    Download: https://ffmpeg.org/download.html" -ForegroundColor Gray
    Write-Host "    Add to PATH before building" -ForegroundColor Gray
    $allGood = $false
}

# Check 5: InsightFace models
Write-Host "[5/8] Checking InsightFace models..." -ForegroundColor Yellow
$modelPath = "$env:USERPROFILE\.insightface\models\buffalo_l"
if (Test-Path $modelPath) {
    $modelFiles = Get-ChildItem $modelPath -Filter "*.onnx"
    if ($modelFiles.Count -ge 3) {
        Write-Host "  ✓ InsightFace models found ($($modelFiles.Count) files)" -ForegroundColor Green
        Write-Host "    Location: $modelPath" -ForegroundColor Gray
    } else {
        Write-Host "  ⚠ Incomplete models ($($modelFiles.Count) ONNX files)" -ForegroundColor Yellow
        Write-Host "    Expected: 3+ model files" -ForegroundColor Gray
    }
} else {
    Write-Host "  ✗ InsightFace models NOT found" -ForegroundColor Red
    Write-Host "    Run app once to download models automatically" -ForegroundColor Gray
    Write-Host "    Or use: python utils/download_face_models.py" -ForegroundColor Gray
    $allGood = $false
}

# Check 6: Spec file
Write-Host "[6/8] Checking spec file..." -ForegroundColor Yellow
if (Test-Path "memorymate_pyinstaller.spec") {
    Write-Host "  ✓ memorymate_pyinstaller.spec found" -ForegroundColor Green
    
    # Check for critical settings
    $specContent = Get-Content "memorymate_pyinstaller.spec" -Raw
    if ($specContent -match "console=False") {
        Write-Host "    ✓ Console disabled (production mode)" -ForegroundColor Green
    } else {
        Write-Host "    ⚠ Console enabled (debug mode)" -ForegroundColor Yellow
    }
    
    # Check if spec still has old cipher parameter (PyInstaller 6.0+ incompatible)
    if ($specContent -match "cipher\s*=\s*block_cipher") {
        Write-Host "    ✗ Old 'cipher' parameter found (PyInstaller 6.0+ incompatible)" -ForegroundColor Red
        Write-Host "    Fix: Remove cipher parameters from spec file" -ForegroundColor Gray
        $allGood = $false
    } else {
        Write-Host "    ✓ Spec compatible with PyInstaller 6.0+" -ForegroundColor Green
    }
} else {
    Write-Host "  ✗ memorymate_pyinstaller.spec NOT found" -ForegroundColor Red
    $allGood = $false
}

# Check 7: App icon
Write-Host "[7/8] Checking app icon..." -ForegroundColor Yellow
if (Test-Path "app_icon.ico") {
    $iconSize = (Get-Item "app_icon.ico").Length
    Write-Host "  ✓ app_icon.ico found ($([math]::Round($iconSize/1KB, 1)) KB)" -ForegroundColor Green
} else {
    Write-Host "  ⚠ app_icon.ico NOT found (will use default icon)" -ForegroundColor Yellow
}

# Check 8: Disk space
Write-Host "[8/8] Checking disk space..." -ForegroundColor Yellow
$drive = (Get-Location).Drive
$freeSpace = (Get-PSDrive $drive.Name).Free
$freeSpaceGB = [math]::Round($freeSpace / 1GB, 2)

if ($freeSpaceGB -gt 5) {
    Write-Host "  ✓ Free space: $freeSpaceGB GB" -ForegroundColor Green
} elseif ($freeSpaceGB -gt 2) {
    Write-Host "  ⚠ Free space: $freeSpaceGB GB (recommended: 5+ GB)" -ForegroundColor Yellow
} else {
    Write-Host "  ✗ Free space: $freeSpaceGB GB (need at least 2 GB)" -ForegroundColor Red
    $allGood = $false
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan

if ($allGood) {
    Write-Host "✅ ALL CHECKS PASSED!" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Ready to build! Run:" -ForegroundColor White
    Write-Host "  .\build_and_split.ps1" -ForegroundColor Cyan
    Write-Host ""
} else {
    Write-Host "❌ SOME CHECKS FAILED" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix the issues above before building." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Quick fixes:" -ForegroundColor White
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Gray
    Write-Host "  pip install rawpy" -ForegroundColor Gray
    Write-Host ""
}

Write-Host "Estimated build time: 5-10 minutes" -ForegroundColor Gray
Write-Host "Output size: ~900 MB (split into 5 x 180 MB parts)" -ForegroundColor Gray
Write-Host ""
