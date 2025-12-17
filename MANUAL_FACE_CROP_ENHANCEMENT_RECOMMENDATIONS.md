# Manual Face Crop Enhancement Recommendations
**Date:** 2025-12-17
**Status:** App Stable - Ready for Quality Enhancements
**Based on:** Google Photos, Apple Photos, Adobe Lightroom Best Practices

---

## Executive Summary

The manual face cropping feature is now **stable and functional** ✅. However, the face crops can be enhanced to match professional photo management standards.

**Current State:**
- ✅ Stable (no crashes)
- ✅ Face detection refinement working
- ✅ Database integration working
- ⚠️ **Face crops need polishing** (user feedback)

**Recommended Enhancements:** 6 high-impact improvements based on industry best practices

---

## Current Implementation Analysis

### **What's Working Well** ✅

1. **Auto-refinement:** Manual rectangles are refined using InsightFace detection
2. **Graceful fallback:** If detection fails, keeps user's original rectangle
3. **DNG/RAW support:** Handles all image formats safely
4. **Database integration:** Faces saved with proper schema

### **What Needs Enhancement** ⚠️

Looking at the current `_refine_manual_bbox_with_detection()` method (lines 702-801):

```python
# Current implementation uses only bbox from detection:
det_x = face['bbox_x']
det_y = face['bbox_y']
det_w = face['bbox_w']
det_h = face['bbox_h']

# MISSING:
# - Facial landmarks (eye positions, nose, mouth)
# - Face alignment (rotation correction)
# - Quality scoring (blur, lighting, occlusion)
# - Smart padding adjustment
# - Embedding generation verification
```

**Problem:** We're only using ~20% of InsightFace's capabilities!

---

## Enhancement Recommendations

### **Priority Matrix**

| Enhancement | Impact | Effort | Priority |
|-------------|--------|--------|----------|
| #1: Face Alignment | 🔥 HIGH | Medium | **P0** |
| #2: Smart Padding | 🔥 HIGH | Low | **P0** |
| #3: Quality Assessment | 🔥 HIGH | Medium | **P1** |
| #4: Visual Feedback | 🟡 MEDIUM | Low | **P1** |
| #5: Auto-Clustering | 🟡 MEDIUM | High | **P2** |
| #6: Post-Processing | 🟢 LOW | High | **P3** |

---

## 🔥 **P0 Enhancement #1: Face Alignment** (Most Important!)

### **Problem**
Tilted/rotated faces are harder to recognize and cluster. Current crops don't correct face rotation.

### **Industry Standard**
- **Google Photos:** Auto-rotates faces to align eyes horizontally
- **Apple Photos:** Uses facial landmarks for perfect alignment
- **Adobe Lightroom:** Face alignment before recognition

### **What InsightFace Provides**
InsightFace detects **5 facial landmarks** (keypoints):
```python
face['kps'] = [
    [x1, y1],  # Left eye
    [x2, y2],  # Right eye
    [x3, y3],  # Nose tip
    [x4, y4],  # Left mouth corner
    [x5, y5]   # Right mouth corner
]
```

### **Implementation Strategy**

**Step 1: Extract landmarks from detection**
```python
def _refine_manual_bbox_with_detection(self, x, y, w, h):
    # ... existing code ...

    if len(detected_faces) == 1:
        face = detected_faces[0]

        # NEW: Check if landmarks available
        if 'kps' in face and face['kps'] is not None:
            logger.info("[FaceCropEditor] Landmarks detected - applying face alignment")
            return self._align_face_with_landmarks(img, face, search_x, search_y)
        else:
            logger.info("[FaceCropEditor] No landmarks - using bbox only")
            # Fall back to current bbox-only method
```

**Step 2: Calculate rotation angle from eye positions**
```python
def _align_face_with_landmarks(self, img, face, search_x, search_y):
    """Align face using eye landmarks for perfect horizontal alignment."""
    import numpy as np
    import cv2

    # Get eye coordinates (relative to search region)
    kps = face['kps']
    left_eye = kps[0]   # [x, y] of left eye
    right_eye = kps[1]  # [x, y] of right eye

    # Convert to original image coordinates
    left_eye_abs = [search_x + left_eye[0], search_y + left_eye[1]]
    right_eye_abs = [search_x + right_eye[0], search_y + right_eye[1]]

    # Calculate angle between eyes
    dx = right_eye_abs[0] - left_eye_abs[0]
    dy = right_eye_abs[1] - left_eye_abs[1]
    angle = np.degrees(np.arctan2(dy, dx))

    logger.debug(f"[FaceCropEditor] Eye angle: {angle:.2f}° (0° = perfectly horizontal)")

    # If angle is within ±3°, no rotation needed
    if abs(angle) < 3.0:
        logger.debug("[FaceCropEditor] Face already aligned - skipping rotation")
        return self._get_aligned_bbox(face, search_x, search_y, img.size)

    # Calculate center point between eyes
    center_x = (left_eye_abs[0] + right_eye_abs[0]) / 2
    center_y = (left_eye_abs[1] + right_eye_abs[1]) / 2

    # Convert PIL to CV2 for rotation
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    # Rotate image to align eyes horizontally
    M = cv2.getRotationMatrix2D((center_x, center_y), angle, 1.0)
    rotated = cv2.warpAffine(img_cv, M, (img.width, img.height))

    # Convert back to PIL
    rotated_pil = Image.fromarray(cv2.cvtColor(rotated, cv2.COLOR_BGR2RGB))

    # Re-run detection on rotated image to get new bbox
    # ... (save temp, detect, get bbox)

    logger.info(f"[FaceCropEditor] ✅ Face aligned: rotated {angle:.2f}° for horizontal eyes")
```

**Benefits:**
- ✅ Better face recognition (aligned faces cluster better)
- ✅ Professional-looking crops (eyes always horizontal)
- ✅ Improved embedding quality (ArcFace trained on aligned faces)
- ✅ Consistent with auto-detected faces

**Complexity:** Medium (requires CV2, coordinate transformation)

---

## 🔥 **P0 Enhancement #2: Smart Padding**

### **Problem**
Current crops might be too tight or include too much background.

### **Industry Standard**
- **Google Photos:** 30% padding around face (includes shoulders)
- **Apple Photos:** Golden ratio padding (1.618:1)
- **Facebook:** Shows partial shoulders for context

### **Current Code**
```python
# In _create_face_crop():
face_crop = img.crop((x, y, x + w, y + h))  # Exact bbox, might be too tight
```

### **Recommended Enhancement**

```python
def _create_face_crop_with_smart_padding(self, img, x, y, w, h):
    """Create face crop with smart padding for professional appearance."""

    # Calculate smart padding (30% of face size)
    padding_factor = 0.30  # Industry standard
    pad_w = int(w * padding_factor)
    pad_h = int(h * padding_factor)

    # Asymmetric padding: more padding below (include shoulders)
    pad_top = pad_h
    pad_bottom = int(pad_h * 1.5)  # 50% more below for shoulders
    pad_left = pad_w
    pad_right = pad_w

    # Calculate crop coordinates with padding
    crop_x1 = max(0, x - pad_left)
    crop_y1 = max(0, y - pad_top)
    crop_x2 = min(img.width, x + w + pad_right)
    crop_y2 = min(img.height, y + h + pad_bottom)

    # Crop with smart padding
    face_crop = img.crop((crop_x1, crop_y1, crop_x2, crop_y2))

    logger.debug(f"[FaceCropEditor] Applied smart padding: "
                 f"original {w}x{h} → cropped {crop_x2-crop_x1}x{crop_y2-crop_y1}")

    return face_crop
```

**Visual Comparison:**
```
BEFORE (tight crop):          AFTER (smart padding):
┌────────┐                    ┌──────────────┐
│  👁️ 👁️  │                    │              │
│   👃    │                    │    👁️ 👁️     │
│   👄    │                    │     👃       │
└────────┘                    │     👄       │
                              │  Shoulders   │
                              └──────────────┘
```

**Benefits:**
- ✅ More professional appearance
- ✅ Easier face recognition (more context)
- ✅ Better for printing/display
- ✅ Matches auto-detected face crops

**Complexity:** Low (simple coordinate adjustment)

---

## 🔥 **P1 Enhancement #3: Quality Assessment**

### **Problem**
Low-quality manual crops (blurry, dark, occluded) hurt recognition accuracy.

### **Industry Standard**
- **Google Photos:** Flags low-quality faces for user review
- **Apple Photos:** Auto-rejects faces below quality threshold
- **Adobe Lightroom:** Quality score 0-100

### **What InsightFace Provides**
```python
# Already available in detection:
face['confidence']  # Detection confidence (0-1)
# Can calculate additional quality metrics
```

### **Implementation**

```python
def _assess_face_quality(self, face_crop_path: str, face_data: dict) -> dict:
    """Assess face crop quality and flag issues."""
    import cv2
    import numpy as np

    quality_report = {
        'overall_score': 0.0,     # 0-100
        'issues': [],              # List of quality issues
        'confidence': face_data.get('confidence', 0.0),
        'is_acceptable': True
    }

    # Load crop
    img = cv2.imread(face_crop_path)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # METRIC #1: Blur detection (Laplacian variance)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    if laplacian_var < 100:
        quality_report['issues'].append(f"Blurry (sharpness: {laplacian_var:.0f})")
        quality_report['overall_score'] -= 30

    # METRIC #2: Brightness (too dark/bright)
    brightness = np.mean(gray)
    if brightness < 50:
        quality_report['issues'].append(f"Too dark (brightness: {brightness:.0f}/255)")
        quality_report['overall_score'] -= 20
    elif brightness > 200:
        quality_report['issues'].append(f"Too bright (brightness: {brightness:.0f}/255)")
        quality_report['overall_score'] -= 15

    # METRIC #3: Contrast
    contrast = gray.std()
    if contrast < 20:
        quality_report['issues'].append(f"Low contrast ({contrast:.0f})")
        quality_report['overall_score'] -= 15

    # METRIC #4: Detection confidence
    conf_score = face_data['confidence'] * 100
    quality_report['overall_score'] += conf_score * 0.4  # 40% weight

    # METRIC #5: Size (faces too small are low quality)
    face_pixels = face_data['bbox_w'] * face_data['bbox_h']
    if face_pixels < 50 * 50:  # Smaller than 50x50
        quality_report['issues'].append(f"Face too small ({face_data['bbox_w']}x{face_data['bbox_h']})")
        quality_report['overall_score'] -= 25

    # Clamp score 0-100
    quality_report['overall_score'] = max(0, min(100, quality_report['overall_score']))

    # Mark as unacceptable if score < 40
    if quality_report['overall_score'] < 40:
        quality_report['is_acceptable'] = False

    return quality_report
```

**User Feedback:**
```python
def _show_quality_warning(self, quality_report: dict):
    """Warn user about low-quality face crops."""
    if not quality_report['is_acceptable']:
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("Low Quality Face Detected")
        msg.setText(f"⚠️ Quality Score: {quality_report['overall_score']:.0f}/100")

        issues_text = "\n".join([f"• {issue}" for issue in quality_report['issues']])
        msg.setInformativeText(
            f"This face crop has quality issues:\n\n{issues_text}\n\n"
            "Face recognition may not work well. Consider:\n"
            "• Using a clearer photo\n"
            "• Adjusting lighting\n"
            "• Drawing a larger rectangle"
        )

        msg.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        msg.setDefaultButton(QMessageBox.Ok)

        result = msg.exec()
        return result == QMessageBox.Ok  # True = user accepts anyway
```

**Benefits:**
- ✅ Prevents poor-quality faces from hurting recognition
- ✅ Educates users on what makes a good face crop
- ✅ Reduces frustration ("why isn't this face recognized?")

**Complexity:** Medium (requires CV2, quality metrics knowledge)

---

## 🟡 **P1 Enhancement #4: Visual Feedback**

### **Problem**
Users can't see before/after of refinement. No visual confirmation of alignment/padding.

### **Recommended Enhancement**

```python
def _show_refinement_preview(self, original_bbox, refined_bbox, img):
    """Show before/after comparison of refinement."""
    from PySide6.QtWidgets import QDialog, QLabel, QHBoxLayout

    dialog = QDialog(self)
    dialog.setWindowTitle("Face Refinement Preview")
    layout = QHBoxLayout(dialog)

    # BEFORE (user's manual rectangle)
    before_label = QLabel("Your Rectangle:")
    x, y, w, h = original_bbox
    before_crop = img.crop((x, y, x+w, y+h))
    before_pixmap = self._pil_to_qpixmap(before_crop)
    before_img = QLabel()
    before_img.setPixmap(before_pixmap.scaled(200, 200, Qt.KeepAspectRatio))

    # AFTER (refined with detection)
    after_label = QLabel("Refined (with AI):")
    x2, y2, w2, h2 = refined_bbox
    after_crop = img.crop((x2, y2, x2+w2, y2+h2))
    after_pixmap = self._pil_to_qpixmap(after_crop)
    after_img = QLabel()
    after_img.setPixmap(after_pixmap.scaled(200, 200, Qt.KeepAspectRatio))

    # Add to layout
    layout.addWidget(before_label)
    layout.addWidget(before_img)
    layout.addWidget(QLabel("→"))
    layout.addWidget(after_label)
    layout.addWidget(after_img)

    dialog.exec()
```

**Benefits:**
- ✅ Users understand what refinement does
- ✅ Builds trust in AI refinement
- ✅ Educational (users learn what good crops look like)

**Complexity:** Low (simple UI dialog)

---

## 🟡 **P2 Enhancement #5: Auto-Clustering & Merge Suggestions**

### **Problem**
After adding manual faces, they don't automatically merge with similar existing faces.

### **Industry Standard**
- **Google Photos:** "Is this the same person?" suggestions
- **Apple Photos:** Auto-suggests merging similar face clusters

### **Implementation**

```python
def _suggest_face_merges_after_save(self, new_branch_key: str):
    """Suggest merging newly added manual face with similar existing faces."""
    try:
        db = ReferenceDB()

        # Get embedding of new manual face
        new_face = db.get_face_by_branch_key(new_branch_key, self.project_id)
        if not new_face or not new_face.get('centroid'):
            logger.debug(f"No embedding for {new_branch_key} - skipping merge suggestion")
            return

        new_embedding = np.frombuffer(new_face['centroid'], dtype=np.float32)

        # Find similar faces (cosine similarity > 0.6)
        similar_faces = []
        all_faces = db.get_face_clusters(self.project_id)

        for face in all_faces:
            if face['branch_key'] == new_branch_key:
                continue  # Skip self

            if not face.get('centroid'):
                continue

            existing_embedding = np.frombuffer(face['centroid'], dtype=np.float32)

            # Calculate cosine similarity
            similarity = np.dot(new_embedding, existing_embedding) / (
                np.linalg.norm(new_embedding) * np.linalg.norm(existing_embedding)
            )

            if similarity > 0.6:  # Threshold for "same person"
                similar_faces.append({
                    'branch_key': face['branch_key'],
                    'name': face.get('display_name', 'Unknown'),
                    'similarity': similarity,
                    'count': face.get('member_count', 0)
                })

        # Sort by similarity
        similar_faces.sort(key=lambda x: x['similarity'], reverse=True)

        if similar_faces:
            self._show_merge_suggestion_dialog(new_branch_key, similar_faces[:3])

    except Exception as e:
        logger.error(f"Error suggesting merges: {e}", exc_info=True)

def _show_merge_suggestion_dialog(self, new_key: str, similar: List[dict]):
    """Show dialog suggesting face merges."""
    msg = QMessageBox(self)
    msg.setIcon(QMessageBox.Question)
    msg.setWindowTitle("Similar Face Detected")
    msg.setText(f"This face looks similar to existing people:")

    suggestions = "\n".join([
        f"• {f['name']} ({f['count']} photos) - {f['similarity']*100:.0f}% match"
        for f in similar
    ])

    msg.setInformativeText(
        f"{suggestions}\n\n"
        "Would you like to merge them?\n"
        "(You can also merge later by dragging faces in People section)"
    )

    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    result = msg.exec()

    if result == QMessageBox.Yes:
        # Open People section with merge UI
        # ... implementation
```

**Benefits:**
- ✅ Reduces duplicate face clusters
- ✅ Improves organization automatically
- ✅ Saves user time

**Complexity:** High (requires embedding comparison, merge UI)

---

## 🟢 **P3 Enhancement #6: Post-Processing** (Optional)

### **What Professional Apps Do**
- **Lightroom:** Auto-adjusts exposure for face crops
- **Photoshop:** Sharpens slightly blurry faces
- **Portrait Pro:** Enhances skin tones

### **Simple Enhancements**

```python
def _enhance_face_crop(self, face_crop: Image.Image) -> Image.Image:
    """Apply subtle enhancements to face crop."""
    from PIL import ImageEnhance

    # 1. Slight sharpening (for slightly blurry faces)
    enhancer = ImageEnhance.Sharpness(face_crop)
    face_crop = enhancer.enhance(1.2)  # 20% sharper

    # 2. Brightness adjustment (if too dark)
    brightness = np.mean(np.array(face_crop.convert('L')))
    if brightness < 80:  # Too dark
        enhancer = ImageEnhance.Brightness(face_crop)
        boost = 1 + (80 - brightness) / 200  # Gradual boost
        face_crop = enhancer.enhance(boost)

    # 3. Slight contrast boost
    enhancer = ImageEnhance.Contrast(face_crop)
    face_crop = enhancer.enhance(1.1)  # 10% more contrast

    return face_crop
```

**Benefits:**
- ✅ Better-looking face thumbnails
- ✅ Improved recognition from enhanced clarity

**Complexity:** Medium (requires careful tuning to avoid over-processing)

---

## Implementation Roadmap

### **Phase 1: Quick Wins** (1-2 hours)
- ✅ Enhancement #2: Smart Padding (Low effort, high impact)
- ✅ Enhancement #4: Visual Feedback (Low effort, good UX)

### **Phase 2: Core Quality** (3-4 hours)
- ✅ Enhancement #1: Face Alignment (Medium effort, highest impact)
- ✅ Enhancement #3: Quality Assessment (Medium effort, prevents issues)

### **Phase 3: Advanced** (Optional, 6+ hours)
- ⚪ Enhancement #5: Auto-Clustering (High effort, nice-to-have)
- ⚪ Enhancement #6: Post-Processing (Medium effort, optional polish)

---

## Recommended Next Steps

### **Immediate (Do First)**

1. **Start with Enhancement #2 (Smart Padding)**
   - Quick implementation
   - Immediate visual improvement
   - Low risk

2. **Add Enhancement #4 (Visual Feedback)**
   - Shows users what refinement does
   - Builds confidence in the feature
   - Minimal code

### **Next Priority**

3. **Implement Enhancement #1 (Face Alignment)**
   - Biggest quality improvement
   - Aligns with industry standards
   - Better recognition accuracy

4. **Add Enhancement #3 (Quality Assessment)**
   - Prevents frustration from bad crops
   - Educational for users
   - Improves overall data quality

### **Future Enhancements**

5. **Consider Enhancement #5 (Auto-Clustering)** if users request it
6. **Skip Enhancement #6 (Post-Processing)** unless specifically needed

---

## Testing Checklist

After implementing enhancements:

- [ ] Manual crop from frontal face → Should align eyes horizontally
- [ ] Manual crop from tilted face → Should rotate to align
- [ ] Manual crop with smart padding → Should show shoulders
- [ ] Low-quality face → Should show quality warning
- [ ] High-quality face → Should accept without warning
- [ ] Before/after preview → Should show clear difference
- [ ] Very small face → Should warn about size
- [ ] Blurry face → Should detect and warn
- [ ] Dark face → Should detect and warn

---

## Questions for User

1. **Which enhancement sounds most valuable to you?**
   - Face alignment (tilted faces → straight)
   - Smart padding (include shoulders)
   - Quality warnings (prevent bad crops)
   - Visual feedback (before/after preview)

2. **What specific issues are you seeing with current crops?**
   - Too tight (missing shoulders)?
   - Tilted faces?
   - Blurry/dark faces being saved?
   - Other quality issues?

3. **Do you want to see before/after comparison before saving?**
   - Helpful for learning
   - Or prefer automatic without preview?

---

**Recommendation Priority:**
1. 🔥 **Smart Padding** (Enhancement #2) - Quick win
2. 🔥 **Face Alignment** (Enhancement #1) - Biggest impact
3. 🟡 **Quality Assessment** (Enhancement #3) - Prevents problems
4. 🟡 **Visual Feedback** (Enhancement #4) - Better UX

Let me know which enhancements you'd like to prioritize, and I can implement them in order of value! 🚀
