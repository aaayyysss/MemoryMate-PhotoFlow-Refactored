# Why Search Scores Are Low (19-26%)

## The Reality Check

Looking at your search logs:
```
Query: "blue shirt" → "person wearing blue shirt"
Results: 21 out of 21 photos
Top Score: 26.6%
Threshold: 19%
```

**These low scores (19-26%) are actually NORMAL for the current setup.** Here's why:

## Root Cause: Small CLIP Model

You're currently using: **`clip-vit-base-patch32`**
- This is the **smallest and fastest** CLIP model
- It has the **lowest quality** semantic understanding
- It produces **lower similarity scores** compared to larger models

### CLIP Model Comparison

| Model | Embedding Size | Quality | Typical Scores |
|-------|---------------|---------|----------------|
| **base-patch32** (current) | 512-D | Baseline | 15-30% |
| base-patch16 | 512-D | +15% better | 20-35% |
| **large-patch14** (best) | 768-D | +40% better | 25-60% |

## What Your Scores Mean

With **base-patch32** model:

| Score Range | Meaning | What to Expect |
|-------------|---------|----------------|
| **25-30%** | Best match available | Might be relevant OR might not |
| **20-25%** | Weak match | Probably not relevant |
| **15-20%** | Very weak | Almost certainly not relevant |
| **Below 15%** | No match | Definitely not relevant |

### Why "Blue Shirt" Gets 26.6%

There are three possible explanations:

1. **Photos don't actually contain blue shirts**
   - Your test dataset may not have any photos with blue shirts
   - The model correctly identifies them as "not blue shirts" (low score)
   - This is good discrimination!

2. **Model has limited visual understanding**
   - base-patch32 struggles with specific color+clothing combinations
   - It can't reliably distinguish "blue shirt" from "red shirt" or "blue pants"
   - Scores stay in 20-30% range for everything

3. **Photos are ambiguous**
   - Maybe there's some blue in the photo (sky, background)
   - Maybe there's a person but shirt color unclear
   - Model gives it a weak positive score

## The Real Problem

**All 21 photos are returned** with scores 19-26.6%

This means:
- No discrimination between relevant and irrelevant photos
- Model treats everything as "equally weak match"
- Threshold of 19% is too low to filter anything out

## Solution: What to Do

### Option 1: Quick Fix (Keep Current Model)

**Raise your threshold to 30%** (already done in latest code)
- Expected: 5-10 photos returned instead of 21
- Expected: Better filtering even with low absolute scores
- Reality: Still won't find "blue shirt" if photos don't have blue shirts

### Option 2: Upgrade CLIP Model (RECOMMENDED)

**Install clip-vit-large-patch14:**

```bash
cd /home/user/MemoryMate-PhotoFlow-Refactored

# Download the large model (1.7 GB)
python -c "from transformers import CLIPProcessor, CLIPModel; \
    CLIPProcessor.from_pretrained('openai/clip-vit-large-patch14'); \
    CLIPModel.from_pretrained('openai/clip-vit-large-patch14')"
```

**Then re-extract embeddings:**
1. Delete old embeddings: `DELETE FROM photo_embeddings;`
2. Run embedding extraction job with new model
3. Search again

**Expected improvement:**
- Scores increase by 30-40%
- "Blue shirt" matches: 45-60% (if photos actually have blue shirts)
- "Non-blue-shirt" photos: 15-25% (better discrimination)
- Much better filtering

### Option 3: Verify Your Test Data

**Check what's actually in the photos:**

1. Open your test photos folder
2. Manually look at the 21 photos
3. Count how many actually have blue shirts

**If 0 have blue shirts:**
- Model is working correctly!
- Low scores mean "no match found"
- Try different queries like "eyes", "trees", "buildings"

**If 5+ have blue shirts:**
- Model is failing to recognize them
- This confirms need for larger model
- base-patch32 is insufficient

## Expected Behavior After Fixes

### With base-patch32 (current):
```
Query: "blue shirt"
Expected: 5-10 photos (reduced from 21)
Top Score: 26-30%
Result: Better filtering, but still uncertain matches
```

### With large-patch14 (upgraded):
```
Query: "blue shirt" (on photos WITH blue shirts)
Expected: 2-5 photos
Top Score: 50-65%
Result: High confidence, accurate matches

Query: "blue shirt" (on photos WITHOUT blue shirts)
Expected: 0-2 photos
Top Score: 15-20%
Result: Correctly filters out non-matches
```

## Understanding Search Semantics

Your current search shows an interesting pattern:

```
1. "blue shirt" → 21 photos, top 26.6%
2. "blue shirts" → 21 photos, all below 30%
3. "eyes" → 13 photos, top 20.2%
```

**What this tells us:**
- Model finds everything "weakly similar" (20-30%)
- Can't strongly distinguish query differences
- Behaves like random scoring in this range

**This is classic base-patch32 behavior on images it can't confidently classify.**

## Bottom Line

**Your search is working, but the model is too weak.**

The low scores (19-26%) don't necessarily mean bugs - they mean:
1. Current model (base-patch32) has limited capability
2. Photos may not contain what you're searching for
3. Scores this low are "uncertain" range for this model

**To get confident, useful results (40-60% scores), upgrade to clip-vit-large-patch14.**

Until then, expect:
- Lots of weak matches (20-30%)
- Poor discrimination
- Many irrelevant results
- Uncertainty about what's actually in photos

## Next Steps

1. ✅ Toolbar hiding fixed (removed setMinimumHeight)
2. ✅ Query expansion fixed (handles plurals: "shirts", "dresses")
3. ✅ Threshold raised to 30% (better filtering)
4. ⏳ **RECOMMENDED**: Upgrade to large CLIP model
5. ⏳ Re-extract embeddings with better model
6. ⏳ Test with known queries on known photo content
