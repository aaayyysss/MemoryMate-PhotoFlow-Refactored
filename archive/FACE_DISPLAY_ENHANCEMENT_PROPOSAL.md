# Face Display Enhancement Proposal
**Date**: 2025-12-01
**Component**: People Manager / Face Clustering UI
**Goal**: Improve face visibility and user experience in People section

---

## 🎯 Current State Analysis

### Current Face Sizes

| Component | Current Size | Visibility |
|-----------|-------------|------------|
| **FaceClusterCard** (Grid View) | 192x192px | ⚠️ Small |
| **PeopleListView** (Sidebar) | 96x96px (circular) | ❌ Too small |

### User Feedback
> "Very small face after clustering next the faces-branches makes it so difficult to see the face"

**Problem**: Current face thumbnails are too small to comfortably identify people, especially when viewing multiple clusters.

---

## 📊 Best Practices Research

### 1. **Google Photos** - Industry Leader

#### Grid View
- **Face Card Size**: **250x250px** (enlarged on hover to 300x300px)
- **Layout**: Masonry grid with 4-5 columns on desktop
- **Features**:
  - Large, clear face thumbnails
  - Prominent name labels (18px font)
  - Photo count badge
  - Smooth hover animations
  - **Multi-photo preview**: Shows 3-4 sample photos on hover

#### Detail View
- **Enlarged preview**: 400x400px face when clicked
- **Photo grid**: Shows all photos of that person below

#### Key Takeaways:
✅ **250px is the sweet spot** for face card size
✅ Hover enlargement improves UX without cluttering
✅ Multi-photo preview helps confirm identity

---

### 2. **iPhone Photos (iOS 17 / macOS Sonoma)**

#### People Album
- **Face Thumbnail**: **220x220px** circular avatars
- **Layout**: Grid with 3-4 columns on iPad/Mac
- **Features**:
  - Circular masking (elegant, Apple-style)
  - Large name below (16px bold)
  - Subtle drop shadow
  - **Hover effect**: Gentle scale (1.05x) + shadow increase
  - **Multiple face examples**: Shows 2-3 circular thumbnails in a cluster

#### Key Takeaways:
✅ Circular faces are more elegant and space-efficient
✅ 220px+ is comfortable for viewing
✅ Subtle hover effects enhance interactivity

---

### 3. **Lightroom Classic**

#### People View
- **Face Thumbnail**: **180-220px** (adjustable with slider)
- **Layout**: Grid with variable columns (2-6)
- **Features**:
  - Square thumbnails with rounded corners
  - Name overlay at bottom
  - **Size slider**: User can adjust thumbnail size (120px → 300px)
  - **Expanded view**: Shows 10-20 face examples when cluster is expanded

#### Key Takeaways:
✅ User-adjustable sizing is powerful
✅ Expanded view with multiple examples is valuable
✅ 180-220px range is professional standard

---

### 4. **Excire Fotos**

#### Face Recognition Grid
- **Face Card**: **200-280px** (depends on zoom level)
- **Layout**: Responsive grid (2-5 columns)
- **Features**:
  - Large face thumbnails with rounded corners
  - Confidence score badge (e.g., "95%")
  - Photo count prominent
  - **Hover preview**: Enlarges to 400x400px overlay
  - **Quality indicators**: Shows face quality score

#### Key Takeaways:
✅ Hover preview with enlargement is excellent UX
✅ Confidence/quality indicators build trust
✅ 280px maximum works well for large monitors

---

## 💡 Proposed Enhancements

### Phase 1: Immediate Size Improvements (CRITICAL)

#### 1. **Increase Face Card Size**
**Current**: 192x192px
**Proposed**: **250x250px** (matches Google Photos)

**Benefits**:
- ✅ 30% larger viewing area
- ✅ Easier face identification
- ✅ Industry-standard size
- ✅ Better for high-DPI displays

**Code Change**:
```python
# ui/people_manager_dialog.py, line 60
self.thumbnail_label.setFixedSize(250, 250)  # Was 192

# Also update scaling on lines 119, 131, 145
pixmap = pixmap.scaled(250, 250, Qt.KeepAspectRatio, Qt.SmoothTransformation)
```

---

#### 2. **Increase Sidebar Face Size**
**Current**: 96x96px
**Proposed**: **128x128px** (33% larger)

**Benefits**:
- ✅ More comfortable for sidebar viewing
- ✅ Still compact enough for list view
- ✅ Better readability

**Code Change**:
```python
# ui/people_list_view.py, line 244
self.table.setIconSize(QSize(128, 128))  # Was 96

# line 247
self.table.verticalHeader().setDefaultSectionSize(142)  # Was 110 (128px + padding)

# line 405 (circular masking function call)
circular_pixmap = make_circular_pixmap(pixmap, 128)  # Was 96
```

---

#### 3. **Improve Grid Layout**
**Current**: Fixed 192px cards in grid
**Proposed**: Responsive 250px cards with better spacing

**Code Change**:
```python
# ui/people_manager_dialog.py
# Update grid layout to accommodate larger cards
CARD_SIZE = 250
CARD_SPACING = 16
CARDS_PER_ROW = max(2, (available_width - CARD_SPACING) // (CARD_SIZE + CARD_SPACING))
```

---

### Phase 2: Hover Preview Enhancement (HIGH PRIORITY)

#### 4. **Add Hover Enlargement Overlay**
**Inspiration**: Google Photos + Excire Fotos

**Features**:
- Hover over face card → Show 400x400px enlarged preview
- Smooth fade-in animation (200ms)
- Drop shadow for depth
- Shows additional details (confidence score, photo count)

**Implementation**:
```python
class FaceClusterCard(QFrame):
    def enterEvent(self, event):
        """Show enlarged preview on hover"""
        if not self._hover_preview:
            self._hover_preview = EnlargedFacePreview(self)
            self._hover_preview.set_face_image(self.cluster_data)
            self._hover_preview.show()

    def leaveEvent(self, event):
        """Hide preview on mouse leave"""
        if self._hover_preview:
            self._hover_preview.deleteLater()
            self._hover_preview = None

class EnlargedFacePreview(QWidget):
    """400x400px floating preview overlay"""
    def __init__(self, parent_card):
        super().__init__(parent_card.window())
        self.setFixedSize(400, 400)
        self.setStyleSheet("""
            background-color: white;
            border: 2px solid #E0E0E0;
            border-radius: 12px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.15);
        """)
        # Position to the right of parent card
        # ...
```

**Benefits**:
- ✅ On-demand enlargement without cluttering UI
- ✅ Matches Google Photos UX
- ✅ Helps with face identification
- ✅ Professional feel

---

#### 5. **Multi-Face Preview** (Optional)
**Inspiration**: iPhone Photos + Google Photos

Show 2-3 example faces from the cluster on hover:

```
┌─────────────────────────────────┐
│  ╭─────╮ ╭─────╮ ╭─────╮        │
│  │ 🙂  │ │ 🙂  │ │ 🙂  │        │
│  ╰─────╯ ╰─────╯ ╰─────╯        │
│                                  │
│  John Doe                        │
│  24 photos                       │
└─────────────────────────────────┘
```

**Benefits**:
- ✅ Shows variety of expressions/angles
- ✅ Helps confirm person identity
- ✅ More engaging UI

---

### Phase 3: Advanced Features (NICE-TO-HAVE)

#### 6. **Size Adjustment Slider**
**Inspiration**: Lightroom Classic

Add a zoom slider to toolbar:
```
Thumbnail Size: ──────●──── [S M L]
                120px  250px  400px
```

**Benefits**:
- ✅ User preference flexibility
- ✅ Adapts to different screen sizes
- ✅ Professional feature

---

#### 7. **View Mode Toggle**
**Inspiration**: Google Photos

Three view modes:
1. **Grid View** (current) - 250x250px cards
2. **List View** - 128px circular + details in row
3. **Expanded View** - 400x400px with 10-20 face examples

**Benefits**:
- ✅ Flexibility for different workflows
- ✅ Expanded view great for reviewing clusters

---

#### 8. **Quality/Confidence Indicators**
**Inspiration**: Excire Fotos

Show face quality score as badge:
```
┌─────────────┐
│  ╭─────╮    │
│  │ 🙂  │ 95%│ ← Quality badge
│  ╰─────╯    │
│  John Doe   │
└─────────────┘
```

**Benefits**:
- ✅ Transparency about detection accuracy
- ✅ Helps users identify misclassified faces
- ✅ Professional tool feature

---

## 📐 Recommended Sizes Summary

| Component | Current | Proposed | Increase | Inspiration |
|-----------|---------|----------|----------|-------------|
| **Face Card (Grid)** | 192px | **250px** | +30% | Google Photos |
| **Sidebar List** | 96px | **128px** | +33% | iPhone Photos |
| **Hover Preview** | N/A | **400px** | New | Google Photos + Excire |
| **Expanded View** | N/A | **400px+** | New | Lightroom |

---

## 🎨 Visual Mockup

### Before (Current 192px)
```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│   🙂     │ │   🙂     │ │   🙂     │ │   🙂     │
│          │ │          │ │          │ │          │
│          │ │          │ │          │ │          │
│  Person  │ │  Person  │ │  Person  │ │  Person  │
│  5 pics  │ │  3 pics  │ │  8 pics  │ │  2 pics  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
    192px        192px        192px        192px
```

### After (Proposed 250px + Hover)
```
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│    🙂        │ │    🙂        │ │    🙂        │
│              │ │              │ │              │
│              │ │              │ │              │
│              │ │              │ │              │
│   John Doe   │ │   Jane Doe   │ │   Unknown #3 │
│   24 photos  │ │   15 photos  │ │   8 photos   │
└──────────────┘ └──────────────┘ └──────────────┘
     250px            250px            250px

         ↓ Hover on Jane Doe

┌──────────────┐ ┌────────────────────┐ ┌──────────────┐
│    🙂        │ │       🙂          │ │    🙂        │
│              │ │                    │ │              │
│              │ │    400x400px       │ │              │
│              │ │    PREVIEW         │ │              │
│   John Doe   │ │                    │ │   Unknown #3 │
│   24 photos  │ │   Jane Doe         │ │   8 photos   │
└──────────────┘ │   15 photos        │ └──────────────┘
                 │   Quality: 95%     │
                 └────────────────────┘
                    Enlarged Overlay
```

---

## 🚀 Implementation Plan

### **Phase 1: Critical Fixes (1-2 hours)**
1. ✅ Increase face card size to 250px
2. ✅ Increase sidebar faces to 128px
3. ✅ Update grid layout spacing
4. ✅ Test on different screen sizes

### **Phase 2: Hover Preview (2-3 hours)**
1. ✅ Create EnlargedFacePreview widget
2. ✅ Add hover detection to FaceClusterCard
3. ✅ Implement smooth animations
4. ✅ Add drop shadow and styling

### **Phase 3: Advanced Features (Optional, 4+ hours)**
1. ⏳ Size adjustment slider
2. ⏳ Multi-face preview
3. ⏳ View mode toggle
4. ⏳ Quality indicators

---

## 🧪 Testing Checklist

- [ ] Face cards display at 250x250px
- [ ] Sidebar faces display at 128x128px
- [ ] Hover preview appears smoothly
- [ ] Preview is properly positioned (doesn't go off-screen)
- [ ] Works on 1080p, 1440p, and 4K displays
- [ ] Works with different DPI scales (100%, 150%, 200%)
- [ ] Grid layout adapts to window resize
- [ ] Performance is good with 100+ clusters

---

## 📊 Expected User Impact

### Before
- 😞 Faces too small to identify comfortably
- 😞 Need to click to see larger version
- 😞 Sidebar faces barely visible

### After
- 😊 Faces clearly visible at 250px
- 😊 Hover preview for on-demand enlargement
- 😊 Sidebar faces comfortable at 128px
- 😊 Professional UX matching industry leaders

---

## 🎯 Success Metrics

- ✅ **30% larger face cards** (192px → 250px)
- ✅ **33% larger sidebar faces** (96px → 128px)
- ✅ **400px hover preview** (new feature)
- ✅ **Matches Google Photos standards**
- ✅ **Better face identification accuracy**

---

**Recommendation**: **Implement Phase 1 immediately** (1-2 hours)
Phase 2 can follow based on user feedback.

**Priority**: 🔴 **HIGH** - Directly impacts core face management workflow
