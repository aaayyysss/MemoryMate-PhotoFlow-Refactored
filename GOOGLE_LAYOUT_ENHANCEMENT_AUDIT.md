# Google Photos Layout Enhancement Audit
**Date**: 2025-12-01
**Focus**: Sidebar UX, Face Management, Tag System
**Goal**: Professional layout matching Google Photos/iPhone/Lightroom/Excire Fotos

---

## 🎯 Current Issues Identified

### 1. **Sidebar Cluttering & Scrollbar Problems**

#### **Current State:**
```
┌───────────────────────┐
│ 📅 Timeline          │
│   2024 (152)          │
│     December (45)     │
│     November (32)     │
│   2023 (89)           │
│                       │
│ 📁 Folders            │
│   Documents/Photos    │ ← Horizontal scrollbar!
│   C:\Users\Long\Path\ │ ← Text truncated
│                       │
│ 👥 People             │
│   ⬤ John Doe (24)     │
│   ⬤ Jane Smith (15)   │
│   ⬤ Unknown #3 (8)    │
│                       │
│ 🎬 Videos             │
│   video001.mp4        │
└───────────────────────┘
```

#### **Problems:**
1. ❌ **Horizontal scrollbar** on long folder paths (unprofessional)
2. ❌ **Limited visible area** - all sections stacked vertically
3. ❌ **No collapsible sections** - can't focus on one area
4. ❌ **Fixed width** (180-250px) - not flexible
5. ❌ **No visual hierarchy** - all items look same
6. ❌ **People section lacks context menu** - can't rename/merge
7. ❌ **No tag section** - missing key feature

#### **Best Practice Analysis:**

**Google Photos Sidebar:**
- Collapsible sections with expand/collapse
- Clean truncation with tooltips (no scrollbars)
- Top sections pinned, rest scrollable
- Clear visual separation
- Context menus everywhere

**iPhone Photos (macOS):**
- Collapsible Albums/People/Places
- Smooth animations
- Hover shows full names
- Clean, minimal scrollbars
- Section counters (e.g., "People (47)")

**Lightroom Classic:**
- Collapsible panels with disclosure triangles
- Resizable sidebar (drag to resize)
- Search within sections
- Right-click context menus
- Badge counters

**Excire Fotos:**
- Tabbed sidebar (Timeline/People/Places/Keywords)
- Each tab full screen
- No clutter
- Smart filters at top

---

### 2. **Face Management Missing Features**

#### **Current Layout Has:**
✅ Face renaming (double-click or context menu)
✅ Face merging (context menu → "Merge with...")
✅ Face deletion (context menu → "Delete")
✅ Face card grid with thumbnails
✅ Search/filter faces

#### **Google Layout Missing:**
❌ No context menu on people tree items
❌ No rename functionality
❌ No merge functionality
❌ No delete functionality
❌ Can only click to filter - no management

#### **Required Implementation:**
```python
# Add context menu to people_tree items
def _show_people_context_menu(self, pos):
    item = self.people_tree.itemAt(pos)
    if not item:
        return

    branch_key = item.data(0, Qt.UserRole).get("branch_key")

    menu = QMenu(self.people_tree)

    # Rename
    rename_action = menu.addAction("✏️ Rename Person...")

    # Merge
    merge_action = menu.addAction("🔗 Merge with Another Person...")

    # View all photos
    menu.addSeparator()
    view_action = menu.addAction("📸 View All Photos")

    # Delete
    menu.addSeparator()
    delete_action = menu.addAction("🗑️ Delete Person")

    chosen = menu.exec(self.people_tree.viewport().mapToGlobal(pos))

    if chosen == rename_action:
        self._rename_person(branch_key)
    elif chosen == merge_action:
        self._merge_person(branch_key)
    elif chosen == delete_action:
        self._delete_person(branch_key)
```

---

### 3. **Tag System Missing**

#### **Current Layout Has:**
✅ Tag sidebar tab
✅ Tag filtering
✅ Tag creation/editing
✅ Tag assignment to photos
✅ Tag tree view with counts

#### **Google Layout Missing:**
❌ No tag section in sidebar
❌ No tag filtering
❌ No tag assignment
❌ No tag management

#### **Tag System Architecture (from Current Layout):**

**Database Schema:**
```sql
-- tags table
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    color TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- image_tags junction table
CREATE TABLE image_tags (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    tagged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (tag_id) REFERENCES tags(id)
);
```

**Tag Operations:**
1. Create tag
2. Assign tag to photos
3. Remove tag from photos
4. Rename tag
5. Delete tag
6. Filter photos by tag
7. Bulk tag operations

---

## 💡 Proposed Enhancements

### **Phase 1: Redesign Sidebar (CRITICAL)**

#### **1.1 Add Collapsible Sections**

```python
class CollapsibleSection(QWidget):
    """
    Collapsible section widget (Google Photos / macOS style).

    Features:
    - Disclosure triangle (▶ / ▼)
    - Section title with count badge
    - Smooth expand/collapse animation
    - Remembers collapsed state
    """
    def __init__(self, title: str, count: int = 0):
        super().__init__()
        self.is_collapsed = False
        self.title = title
        self.count = count

        # Header with triangle
        self.header = QPushButton(f"▼ {title} ({count})")
        self.header.clicked.connect(self.toggle_collapsed)

        # Content widget (tree/list)
        self.content_widget = QWidget()

        # Animation
        self.animation = QPropertyAnimation(self.content_widget, b"maximumHeight")
        self.animation.setDuration(200)

    def toggle_collapsed(self):
        if self.is_collapsed:
            self.expand()
        else:
            self.collapse()

    def collapse(self):
        self.is_collapsed = True
        self.header.setText(f"▶ {self.title} ({self.count})")
        self.animation.setStartValue(self.content_widget.height())
        self.animation.setEndValue(0)
        self.animation.start()

    def expand(self):
        self.is_collapsed = False
        self.header.setText(f"▼ {self.title} ({self.count})")
        self.animation.setStartValue(0)
        self.animation.setEndValue(self.content_widget.sizeHint().height())
        self.animation.start()
```

**Benefits:**
✅ Users can collapse unused sections
✅ More screen space for active section
✅ Professional appearance
✅ Smooth animations

---

#### **1.2 Fix Horizontal Scrollbar**

**Problem:** Long folder paths cause horizontal scrollbar

**Solution: Text Elision with Tooltip**

```python
# Current (BAD):
item = QTreeWidgetItem(["C:\Users\John\Documents\Photos\Vacation\2024\Summer\Italy"])
# → Shows horizontal scrollbar 🤮

# Fixed (GOOD):
full_path = "C:\Users\John\Documents\Photos\Vacation\2024\Summer\Italy"
display_name = self._elide_path(full_path, max_width=200)
# → "...Vacation\2024\Summer\Italy"

item = QTreeWidgetItem([display_name])
item.setToolTip(0, full_path)  # Full path on hover
```

**Elision Helper:**
```python
def _elide_path(self, path: str, max_width: int = 200) -> str:
    """
    Elide path intelligently (keep important parts visible).

    Examples:
    "C:\Users\...\Photos\Vacation" (start)
    "...\Vacation\2024\Summer" (middle)
    "Documents\Photos\..." (end)
    """
    from pathlib import Path

    # Use QFontMetrics for accurate text width
    fm = self.people_tree.fontMetrics()

    if fm.horizontalAdvance(path) <= max_width:
        return path  # Fits, no elision needed

    # Elide from beginning (keep end visible)
    parts = Path(path).parts
    if len(parts) > 3:
        elided = "..." + str(Path(*parts[-3:]))
        if fm.horizontalAdvance(elided) <= max_width:
            return elided

    # Fallback: Qt elision
    return fm.elidedText(path, Qt.ElideMiddle, max_width)
```

**Benefits:**
✅ No horizontal scrollbar
✅ Clean appearance
✅ Tooltip shows full path
✅ Intelligent truncation

---

#### **1.3 Add Visual Hierarchy**

**Current:** All items look the same
**Proposed:** Different styles for different levels

```python
# Timeline - Year (bold, larger)
year_item.setFont(0, QFont("Segoe UI", 11, QFont.Bold))
year_item.setForeground(0, QColor("#202124"))

# Timeline - Month (normal)
month_item.setFont(0, QFont("Segoe UI", 10))
month_item.setForeground(0, QColor("#5f6368"))

# People - Named (bold)
named_person.setFont(0, QFont("Segoe UI", 10, QFont.Bold))

# People - Unnamed (italic, lighter)
unnamed_person.setFont(0, QFont("Segoe UI", 10, QFont.Normal, True))
unnamed_person.setForeground(0, QColor("#80868b"))
```

**Benefits:**
✅ Clear hierarchy
✅ Easy scanning
✅ Professional appearance

---

### **Phase 2: Add Face Management (HIGH PRIORITY)**

#### **2.1 Context Menu for People Tree**

```python
# Enable context menu
self.people_tree.setContextMenuPolicy(Qt.CustomContextMenu)
self.people_tree.customContextMenuRequested.connect(self._show_people_context_menu)

def _show_people_context_menu(self, pos):
    """Show context menu for people tree items."""
    item = self.people_tree.itemAt(pos)
    if not item:
        return

    data = item.data(0, Qt.UserRole)
    if not data or data.get("type") != "person":
        return

    branch_key = data.get("branch_key")
    current_name = data.get("label") or "Unnamed Person"

    menu = QMenu(self.people_tree)

    # Rename
    rename_action = QAction("✏️ Rename Person...", self)
    rename_action.triggered.connect(lambda: self._rename_person(item, branch_key, current_name))
    menu.addAction(rename_action)

    # Merge
    merge_action = QAction("🔗 Merge with Another Person...", self)
    merge_action.triggered.connect(lambda: self._merge_person(branch_key))
    menu.addAction(merge_action)

    menu.addSeparator()

    # View all photos
    view_action = QAction("📸 View All Photos", self)
    view_action.setEnabled(True)  # Already filtering on click
    menu.addAction(view_action)

    menu.addSeparator()

    # Delete
    delete_action = QAction("🗑️ Delete This Person", self)
    delete_action.triggered.connect(lambda: self._delete_person(branch_key, current_name))
    menu.addAction(delete_action)

    menu.exec(self.people_tree.viewport().mapToGlobal(pos))
```

#### **2.2 Rename Person**

```python
def _rename_person(self, item: QTreeWidgetItem, branch_key: str, current_name: str):
    """Rename a person/face cluster."""
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    new_name, ok = QInputDialog.getText(
        self,
        "Rename Person",
        f"Rename '{current_name}' to:",
        text=current_name if not current_name.startswith("Unnamed") else ""
    )

    if not ok or not new_name.strip():
        return

    new_name = new_name.strip()

    if new_name == current_name:
        return

    try:
        from reference_db import ReferenceDB
        db = ReferenceDB()

        # Update database
        with db._connect() as conn:
            conn.execute("""
                UPDATE branches
                SET display_name = ?
                WHERE project_id = ? AND branch_key = ?
            """, (new_name, self.project_id, branch_key))

            conn.execute("""
                UPDATE face_branch_reps
                SET label = ?
                WHERE project_id = ? AND branch_key = ?
            """, (new_name, self.project_id, branch_key))

            conn.commit()

        # Update UI
        item.setText(0, f"{new_name} ({item.text(0).split('(')[-1]}")  # Keep count
        item.data(0, Qt.UserRole)["label"] = new_name

        QMessageBox.information(self, "Renamed", f"Person renamed to '{new_name}'")

    except Exception as e:
        QMessageBox.critical(self, "Rename Failed", f"Error: {e}")
```

#### **2.3 Merge Persons**

```python
def _merge_person(self, source_branch_key: str):
    """Merge this person with another person."""
    from PySide6.QtWidgets import QDialog, QListWidget, QDialogButtonBox

    # Get all other persons
    from reference_db import ReferenceDB
    db = ReferenceDB()

    with db._connect() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT branch_key, label, count
            FROM face_branch_reps
            WHERE project_id = ? AND branch_key != ?
            ORDER BY count DESC
        """, (self.project_id, source_branch_key))

        other_persons = cur.fetchall()

    if not other_persons:
        QMessageBox.information(self, "No Persons", "No other persons to merge with")
        return

    # Show selection dialog
    dialog = QDialog(self)
    dialog.setWindowTitle("Merge With Person")
    dialog.resize(400, 500)

    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel("Select person to merge into:"))

    list_widget = QListWidget()
    for branch_key, label, count in other_persons:
        display = f"{label or 'Unnamed Person'} ({count} photos)"
        item = QListWidgetItem(display)
        item.setData(Qt.UserRole, branch_key)
        list_widget.addItem(item)

    layout.addWidget(list_widget)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec() == QDialog.Accepted:
        selected_item = list_widget.currentItem()
        if selected_item:
            target_branch_key = selected_item.data(Qt.UserRole)
            self._perform_merge(source_branch_key, target_branch_key)

def _perform_merge(self, source_key: str, target_key: str):
    """Perform the actual merge operation."""
    try:
        from reference_db import ReferenceDB
        db = ReferenceDB()

        with db._connect() as conn:
            # Move all faces from source to target
            conn.execute("""
                UPDATE face_crops
                SET branch_key = ?
                WHERE project_id = ? AND branch_key = ?
            """, (target_key, self.project_id, source_key))

            # Delete source branch
            conn.execute("""
                DELETE FROM face_branch_reps
                WHERE project_id = ? AND branch_key = ?
            """, (self.project_id, source_key))

            conn.execute("""
                DELETE FROM branches
                WHERE project_id = ? AND branch_key = ?
            """, (self.project_id, source_key))

            conn.commit()

        # Rebuild people tree
        self._build_people_tree()

        QMessageBox.information(self, "Merged", "Persons merged successfully")

    except Exception as e:
        QMessageBox.critical(self, "Merge Failed", f"Error: {e}")
```

---

### **Phase 3: Add Tag System (MEDIUM PRIORITY)**

#### **3.1 Add Tags Section to Sidebar**

```python
# Add after people section
tags_header = QPushButton("🏷️ Tags")
tags_header.setFlat(True)
tags_header.setCursor(Qt.PointingHandCursor)
tags_header.setStyleSheet("""...""")
layout.addWidget(tags_header)

# Tags tree
self.tags_tree = QTreeWidget()
self.tags_tree.setHeaderHidden(True)
self.tags_tree.setIconSize(QSize(16, 16))  # Small color squares
self.tags_tree.itemClicked.connect(self._on_tag_item_clicked)
self.tags_tree.setContextMenuPolicy(Qt.CustomContextMenu)
self.tags_tree.customContextMenuRequested.connect(self._show_tag_context_menu)
layout.addWidget(self.tags_tree)
```

#### **3.2 Build Tags Tree**

```python
def _build_tags_tree(self):
    """Build tags tree with counts."""
    try:
        from reference_db import ReferenceDB
        db = ReferenceDB()

        with db._connect() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    t.id,
                    t.name,
                    t.color,
                    COUNT(DISTINCT it.image_path) as count
                FROM tags t
                LEFT JOIN image_tags it ON it.tag_id = t.id AND it.project_id = t.project_id
                WHERE t.project_id = ?
                GROUP BY t.id
                ORDER BY t.name
            """, (self.project_id,))

            tags = cur.fetchall()

        self.tags_tree.clear()

        if not tags:
            no_tags = QTreeWidgetItem(["  (No tags yet)"])
            no_tags.setDisabled(True)
            self.tags_tree.addTopLevelItem(no_tags)
            return

        for tag_id, name, color, count in tags:
            item = QTreeWidgetItem([f"{name} ({count})"])
            item.setData(0, Qt.UserRole, {"type": "tag", "tag_id": tag_id, "name": name, "color": color})

            # Color square icon
            if color:
                icon = self._make_color_square_icon(color)
                item.setIcon(0, icon)

            self.tags_tree.addTopLevelItem(item)

    except Exception as e:
        print(f"[GoogleLayout] Error building tags tree: {e}")

def _make_color_square_icon(self, color: str, size: int = 16) -> QIcon:
    """Create small colored square icon for tags."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))

    # Add border
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor("#dadce0"), 1))
    painter.drawRect(0, 0, size-1, size-1)
    painter.end()

    return QIcon(pixmap)
```

#### **3.3 Tag Context Menu**

```python
def _show_tag_context_menu(self, pos):
    """Show context menu for tags."""
    item = self.tags_tree.itemAt(pos)
    if not item:
        # Context menu on empty area
        menu = QMenu(self.tags_tree)
        create_action = menu.addAction("➕ Create New Tag...")
        chosen = menu.exec(self.tags_tree.viewport().mapToGlobal(pos))
        if chosen == create_action:
            self._create_tag()
        return

    data = item.data(0, Qt.UserRole)
    if not data or data.get("type") != "tag":
        return

    tag_id = data.get("tag_id")
    tag_name = data.get("name")

    menu = QMenu(self.tags_tree)

    # Rename
    rename_action = menu.addAction("✏️ Rename Tag...")
    rename_action.triggered.connect(lambda: self._rename_tag(item, tag_id, tag_name))

    # Change color
    color_action = menu.addAction("🎨 Change Color...")
    color_action.triggered.connect(lambda: self._change_tag_color(item, tag_id))

    menu.addSeparator()

    # Delete
    delete_action = menu.addAction("🗑️ Delete Tag")
    delete_action.triggered.connect(lambda: self._delete_tag(tag_id, tag_name))

    menu.exec(self.tags_tree.viewport().mapToGlobal(pos))
```

---

## 📊 Implementation Priority

### **Phase 1: Sidebar Improvements (2-3 hours)**
1. ✅ Fix horizontal scrollbar (text elision)
2. ✅ Add collapsible sections
3. ✅ Improve visual hierarchy
4. ✅ Add section counters

### **Phase 2: Face Management (2 hours)**
1. ✅ Add context menu to people tree
2. ✅ Implement rename functionality
3. ✅ Implement merge functionality
4. ✅ Implement delete functionality

### **Phase 3: Tag System (3-4 hours)**
1. ✅ Add tags section to sidebar
2. ✅ Build tags tree with counts
3. ✅ Implement tag filtering
4. ✅ Add tag context menu
5. ✅ Implement tag CRUD operations
6. ✅ Add tag assignment to photos

---

## 🎯 Expected Results

### **Before:**
- 😞 Cluttered sidebar with horizontal scrollbars
- 😞 Can't rename/merge people in Google layout
- 😞 No tag support
- 😞 Unprofessional appearance

### **After:**
- 😊 Clean sidebar with collapsible sections
- 😊 Full face management (rename/merge/delete)
- 😊 Complete tag system
- 😊 Professional UX matching Google Photos
- 😊 No horizontal scrollbars
- 😊 Better space utilization

---

**Status**: ✅ **READY FOR IMPLEMENTATION**
**Priority**: 🔥 **HIGH** - Critical UX improvements
