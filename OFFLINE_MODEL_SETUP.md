# Offline CLIP Model Setup Guide

## Problem

If you're using portable Python on Windows without admin rights, you may encounter SSL certificate verification errors when trying to download the CLIP model:

```
[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate
```

## Solution: Offline Model Download

Use the provided script to download the model with SSL verification disabled.

---

## Quick Start (Recommended)

### Step 1: Run the Download Script

Open a command prompt in the application directory and run:

```bash
python download_clip_model_offline.py
```

The script will:
- ✅ Disable SSL verification
- ✅ Download all required model files (~600MB total)
- ✅ Place files in **app root directory** (next to face detection models)
- ✅ Show download progress
- ✅ Skip already downloaded files

**Model Location:** `./models/clip-vit-base-patch32/` (same directory as buffalo_l face detection models)

### Step 2: Restart the Application

After download completes, restart your photo application and try the embedding extraction feature again.

---

## Alternative: Manual Download

If the script doesn't work, you can download manually:

### 1. Download Files from HuggingFace

Visit: https://huggingface.co/openai/clip-vit-base-patch32/tree/main

Download these files:
- ✅ `config.json`
- ✅ `preprocessor_config.json`
- ✅ `tokenizer_config.json`
- ✅ `vocab.json`
- ✅ `merges.txt`
- ✅ `tokenizer.json`
- ✅ `special_tokens_map.json`
- ✅ `pytorch_model.bin` (⚠️ Large file: ~600MB)

### 2. Create Directory in App Root

Create this directory structure **in the application directory** (next to the face detection models):

```
./models/clip-vit-base-patch32/snapshots/e6a30b603a447e251fdaca1c3056b2a16cdfebeb/
./models/clip-vit-base-patch32/refs/
```

The commit hash `e6a30b603a447e251fdaca1c3056b2a16cdfebeb` is the stable version of CLIP ViT-B/32.

### 3. Copy Files

Copy all downloaded files to the `snapshots/e6a30b603a447e251fdaca1c3056b2a16cdfebeb/` directory.

Create a file `refs/main` containing just the commit hash:
```
e6a30b603a447e251fdaca1c3056b2a16cdfebeb
```

### 4. Verify

The directory structure should look like:

```
./models/
├── buffalo_l/                    (face detection models)
│   └── ...
└── clip-vit-base-patch32/        (CLIP embedding models)
    ├── refs/
    │   └── main                  (contains commit hash)
    └── snapshots/
        └── e6a30b603a447e251fdaca1c3056b2a16cdfebeb/
            ├── config.json
            ├── preprocessor_config.json
            ├── tokenizer_config.json
            ├── vocab.json
            ├── merges.txt
            ├── tokenizer.json
            ├── special_tokens_map.json
            └── pytorch_model.bin (~600MB)
```

---

## Verification

After setup, you should see this log message when running embedding extraction:

```
[EmbeddingService] Loading CLIP model: openai/clip-vit-base-patch32
[EmbeddingService] ✓ CLIP loaded: openai/clip-vit-base-patch32 (512-D, device=cpu)
```

If you see SSL errors, the model is still trying to download from the internet. Check that:
1. Files are in the correct directory
2. File names match exactly (case-sensitive)
3. All 8 files are present

---

## Troubleshooting

### Issue: "Still getting SSL errors"

**Solution:** Ensure files are in the exact path shown above. The `transformers` library is very specific about cache directory structure.

### Issue: "Model loads but is very slow"

**Solution:** This is normal on CPU. The first time loading will take 30-60 seconds. Subsequent loads will be faster.

### Issue: "Script can't find cache directory"

**Solution:** The script auto-detects the cache directory. If it fails, manually specify:

```python
# Edit download_clip_model_offline.py
cache_dir = Path("C:/Users/YourUsername/.cache/huggingface/hub/models--openai--clip-vit-base-patch32/snapshots/main")
```

### Issue: "Download interrupted"

**Solution:** Run the script again. It will skip already downloaded files and resume from where it stopped.

---

## Technical Details

### Why This Happens

Portable Python installations often lack:
- Updated root SSL certificates
- Proper certificate chain validation
- System-level certificate store access

### Security Note

⚠️ **Important:** Disabling SSL verification is only safe for:
- Downloading from trusted sources (HuggingFace is trusted)
- Local development environments
- Portable/offline environments

For production deployments, properly configure SSL certificates.

---

## Support

If you continue to have issues:

1. Check that all 8 files downloaded successfully
2. Verify file sizes (pytorch_model.bin should be ~600MB)
3. Try deleting the cache directory and re-downloading
4. Check Windows username doesn't contain special characters

For additional help, see the main README.md
