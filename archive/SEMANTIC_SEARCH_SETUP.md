# Semantic Search Setup Guide

This guide will help you set up AI-powered semantic search in MemoryMate PhotoFlow.

## Overview

Semantic search allows you to find photos using natural language descriptions like:
- "sunset beach"
- "dog playing in park"
- "people smiling at camera"

## Requirements

Before using semantic search, you need to install these Python packages:

1. **PyTorch** - Deep learning framework
2. **Transformers** - Hugging Face library for CLIP models
3. **Pillow** - Image processing

## Installation Steps

### Step 1: Install Dependencies

#### Option A: CPU-only (Recommended for most users)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install transformers pillow
```

#### Option B: With CUDA GPU support (for NVIDIA GPUs)

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install transformers pillow
```

### Step 2: Verify Installation

Run the diagnostic script to check if PyTorch is properly installed:

```bash
python test_pytorch_install.py
```

If all tests pass, you're ready to use semantic search!

## Troubleshooting

### Windows DLL Error

If you see an error like:
```
OSError: [WinError 1114] Eine DLL-Initialisierungsroutine ist fehlgeschlagen
Error loading "...\torch\lib\c10.dll" or one of its dependencies
```

**Solution:**

1. **Install Visual C++ Redistributable 2015-2022:**
   - Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
   - Run the installer
   - Restart your computer

2. **Reinstall PyTorch:**
   ```bash
   pip uninstall torch torchvision
   pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
   ```

3. **Run diagnostic again:**
   ```bash
   python test_pytorch_install.py
   ```

### Import Error: No module named 'torch'

**Solution:**
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

### Import Error: No module named 'transformers'

**Solution:**
```bash
pip install transformers
```

### Import Error: No module named 'PIL'

**Solution:**
```bash
pip install pillow
```

## Usage

### 1. Extract Embeddings (One-time setup)

Before you can search, you need to extract embeddings for your photos:

1. Open MemoryMate PhotoFlow
2. Go to **Tools → AI & Semantic Search → Extract Embeddings...**
3. Click **Yes** to confirm
4. Wait for extraction to complete (runs in background)

**Note:** First run will download the CLIP model (~500MB).

### 2. Check Status

To see how many photos have embeddings:

1. Go to **Tools → AI & Semantic Search → Show Embedding Status**
2. View the progress (e.g., "150 / 1000 photos (15%)")

### 3. Search Your Photos

Once embeddings are extracted:

1. Use the **semantic search bar** in the toolbar
2. Type a natural language description (e.g., "beach sunset")
3. Click **Search** or press Enter
4. Results appear instantly in the photo grid

## Performance Tips

- **CPU vs GPU:** GPU is 10-50x faster for extraction
  - CPU: ~2-5 seconds per photo
  - GPU: ~0.1-0.5 seconds per photo

- **First-time model download:** ~500MB, happens once

- **Background processing:** Extraction runs in background, you can continue working

## Architecture

The semantic search system consists of:

- **EmbeddingService** (`services/embedding_service.py`) - CLIP model loader and inference
- **EmbeddingWorker** (`workers/embedding_worker.py`) - Background extraction worker
- **JobService** (`services/job_service.py`) - Job queue with crash recovery
- **SemanticSearchWidget** (`ui/semantic_search_widget.py`) - Search UI
- **Database Schema v6.0.0** - ML tables for embeddings, jobs, etc.

## Technical Details

### Models

Default model: **openai/clip-vit-base-patch32**
- Size: ~500MB
- Input: 224x224 images
- Embedding dimension: 512

### Database Tables

- `ml_model` - Tracks loaded models
- `photo_embedding` - Stores 512-dim vectors per photo
- `ml_job` - Job queue for extraction
- `photo_caption`, `photo_tag_suggestion`, etc. - For future features

### Search Algorithm

1. User types query: "sunset beach"
2. CLIP converts text → 512-dim embedding
3. Database searches for similar photo embeddings using cosine similarity
4. Top K results returned and displayed

## Support

If you encounter issues:

1. Run `python test_pytorch_install.py` to diagnose
2. Check this guide's troubleshooting section
3. Report bugs at: https://github.com/anthropics/memorymate-photoflow/issues
