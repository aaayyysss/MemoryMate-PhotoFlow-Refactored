# MemoryMate-PhotoFlow Patch Creator
# Creates a lightweight patch package with only modified files

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "MemoryMate-PhotoFlow Patch Creator v3.0.2" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Patch information
$patchVersion = "v3.0.2-hotfix"
$patchDate = Get-Date -Format "yyyy-MM-dd"
$patchName = "MemoryMate-PhotoFlow-Patch-$patchVersion"

# Files to include in patch
$patchFiles = @(
    "services\face_detection_service.py",
    "BUGFIX_FACE_DETECTION_NONETYPE.md"
)

# Create patch directory
$patchDir = "patch_output\$patchName"
if (Test-Path "patch_output") {
    Remove-Item "patch_output" -Recurse -Force
}
New-Item -ItemType Directory -Path $patchDir | Out-Null

Write-Host "[1/4] Copying patch files..." -ForegroundColor Yellow

# Copy files maintaining directory structure
foreach ($file in $patchFiles) {
    $sourcePath = Join-Path $PSScriptRoot $file
    $destPath = Join-Path $patchDir $file
    
    # Create parent directory if needed
    $destDir = Split-Path $destPath -Parent
    if (-not (Test-Path $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    
    if (Test-Path $sourcePath) {
        Copy-Item $sourcePath $destPath -Force
        Write-Host "  ✓ $file" -ForegroundColor Green
    } else {
        Write-Host "  ✗ $file (not found)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "[2/4] Creating patch installer..." -ForegroundColor Yellow

# Copy batch installer template
Copy-Item "install_patch_template.bat" (Join-Path $patchDir "install_patch.bat") -Force
Write-Host "  ✓ install_patch.bat" -ForegroundColor Green

Write-Host ""
Write-Host "[3/4] Creating README..." -ForegroundColor Yellow

# Copy README template
Copy-Item "README_template.md" (Join-Path $patchDir "README.md") -Force
Write-Host "  ✓ README.md" -ForegroundColor Green

Write-Host ""
Write-Host "[4/4] Creating patch archive..." -ForegroundColor Yellow

# Compress to ZIP
$zipPath = "patch_output\$patchName.zip"
Compress-Archive -Path "$patchDir\*" -DestinationPath $zipPath -Force

# Get file size
$zipSize = (Get-Item $zipPath).Length
$zipSizeKB = [math]::Round($zipSize / 1KB, 2)
$zipSizeMB = [math]::Round($zipSize / 1MB, 2)

Write-Host "  ✓ $patchName.zip" -ForegroundColor Green

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "Patch package created successfully!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Package Details:" -ForegroundColor Cyan
Write-Host "  Location: $zipPath" -ForegroundColor White
Write-Host "  Size: $zipSizeKB KB ($zipSizeMB MB)" -ForegroundColor White
Write-Host "  Files: $($patchFiles.Count) patched files" -ForegroundColor White
Write-Host ""
Write-Host "Distribution:" -ForegroundColor Cyan
Write-Host "  - Send $patchName.zip to users (email, USB, cloud)" -ForegroundColor White
Write-Host "  - Users extract and run install_patch.bat" -ForegroundColor White
Write-Host "  - No need to transfer full 1.2GB package!" -ForegroundColor White
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Yellow
Write-Host "  1. Test the patch on a clean installation" -ForegroundColor White
Write-Host "  2. Verify face detection works after patching" -ForegroundColor White
Write-Host "  3. Distribute to users who need the fix" -ForegroundColor White
Write-Host ""
