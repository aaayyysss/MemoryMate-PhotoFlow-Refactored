"""
Material Design 3 Integration Adapter
Bridge between Material Design 3/Stitch UI and existing MemoryMate app

This file demonstrates how to:
1. Load photos from existing database (ReferenceDB)
2. Populate Material Design 3 gallery with real data
3. Connect signals to existing app services
4. Handle photo operations (favorite, delete, etc.)

Author: MemoryMate Integration
Version: 1.0
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, QThread, Signal, QObject, QRunnable, QThreadPool

# Existing MemoryMate imports (adapt as needed)
try:
    from reference_db import ReferenceDB
except ImportError:
    ReferenceDB = None

try:
    from services.tag_service import get_tag_service
except ImportError:
    get_tag_service = None

# Material Design 3 imports
from ui.material_gallery_view import MaterialGalleryMainWindow, PhotoGalleryView
from ui.material_photo_card import PhotoCard


class PhotoDataAdapter:
    """Adapter to fetch and format photo data for Material Design gallery"""
    
    def __init__(self):
        self.db = ReferenceDB() if ReferenceDB else None
    
    def get_photos_grouped_by_date(self) -> Dict[str, List[Dict]]:
        """
        Get all photos grouped by date for gallery sections
        
        Returns:
            Dict mapping date labels (e.g., "Today", "Yesterday") to photo lists
            
        Example:
            {
                'Today': [
                    {'id': 1, 'path': '/path/to/photo1.jpg', 'exif': '1/500s f/2.8 ISO 100'},
                    {'id': 2, 'path': '/path/to/photo2.jpg', 'exif': '1/1000s f/4.0 ISO 200'},
                ],
                'Yesterday': [...],
                'October 2026': [...]
            }
        """
        if not self.db:
            return self._get_sample_data()
        
        photo_groups = {}
        now = datetime.now()
        today = now.date()
        
        # Query photos from database
        try:
            all_photos = self.db.get_all_photos()  # Adapt to your DB method
        except Exception as e:
            print(f"Error querying photos: {e}")
            return self._get_sample_data()
        
        # Group by date
        for photo in all_photos:
            # Get photo date (from EXIF or file date)
            photo_date = self._extract_photo_date(photo)
            
            # Calculate date label
            date_label = self._get_date_label(photo_date, today)
            
            # Create photo data dict
            photo_data = {
                'id': photo.id if hasattr(photo, 'id') else None,
                'path': photo.path if hasattr(photo, 'path') else str(photo),
                'exif': self._format_exif_data(photo),
                'thumbnail': photo.thumbnail_path if hasattr(photo, 'thumbnail_path') else None,
            }
            
            # Add to group
            if date_label not in photo_groups:
                photo_groups[date_label] = []
            photo_groups[date_label].append(photo_data)
        
        # Sort groups by date (most recent first)
        date_order = ['Today', 'Yesterday', 'This Week', 'This Month', 'Older']
        ordered_groups = {}
        
        for label in date_order:
            if label in photo_groups:
                ordered_groups[label] = photo_groups.pop(label)
        
        # Add any remaining groups
        for label in sorted(photo_groups.keys(), reverse=True):
            ordered_groups[label] = photo_groups[label]
        
        return ordered_groups
    
    def _extract_photo_date(self, photo) -> datetime:
        """Extract date from photo object"""
        # Try EXIF date first
        if hasattr(photo, 'date_taken') and photo.date_taken:
            return photo.date_taken
        
        # Try file modification date
        if hasattr(photo, 'modified_date') and photo.modified_date:
            return photo.modified_date
        
        # Try to get from path
        if hasattr(photo, 'path'):
            try:
                file_stat = Path(photo.path).stat()
                return datetime.fromtimestamp(file_stat.st_mtime)
            except:
                pass
        
        # Default to now
        return datetime.now()
    
    def _get_date_label(self, photo_date: datetime, today: datetime) -> str:
        """Get a friendly date label"""
        photo_day = photo_date.date()
        delta = today - photo_day
        
        if delta.days == 0:
            return "Today"
        elif delta.days == 1:
            return "Yesterday"
        elif delta.days <= 7:
            return f"{photo_date.strftime('%A')}"  # "Monday", "Tuesday", etc.
        elif delta.days <= 30:
            return f"{delta.days} days ago"
        else:
            # Group by month/year
            return photo_date.strftime("%B %Y")  # "October 2026", etc.
    
    def _format_exif_data(self, photo) -> str:
        """Format EXIF data as readable string"""
        parts = []
        
        if hasattr(photo, 'shutter_speed') and photo.shutter_speed:
            parts.append(f"1/{photo.shutter_speed}s")
        
        if hasattr(photo, 'aperture') and photo.aperture:
            parts.append(f"f/{photo.aperture}")
        
        if hasattr(photo, 'iso') and photo.iso:
            parts.append(f"ISO {photo.iso}")
        
        if hasattr(photo, 'focal_length') and photo.focal_length:
            parts.append(f"{photo.focal_length}mm")
        
        return " • ".join(parts) if parts else "No EXIF data"
    
    def _get_sample_data(self) -> Dict[str, List[Dict]]:
        """Return sample data when DB is unavailable"""
        return {
            'Today': [
                {'id': i, 'path': f'/sample/photo_{i}.jpg', 'exif': f'1/{500+i*50}s f/2.8 ISO 100'}
                for i in range(1, 7)
            ],
            'Yesterday': [
                {'id': i+100, 'path': f'/sample/photo_{i}.jpg', 'exif': f'1/{500+i*50}s f/4.0 ISO 200'}
                for i in range(1, 7)
            ],
        }
    
    def load_thumbnail(self, photo_path: str, size: int = 200) -> Optional[QPixmap]:
        """Load and resize thumbnail for photo card"""
        try:
            if not Path(photo_path).exists():
                return None
            
            pixmap = QPixmap(photo_path)
            if pixmap.isNull():
                return None
            
            # Scale to size while maintaining aspect ratio
            scaled = pixmap.scaledToWidth(size, Qt.SmoothTransformation)
            return scaled
        except Exception as e:
            print(f"Error loading thumbnail {photo_path}: {e}")
            return None


class MaterialGalleryController:
    """Controller to manage Material Design gallery with real data"""
    
    def __init__(self, gallery: MaterialGalleryMainWindow):
        self.gallery = gallery
        self.adapter = PhotoDataAdapter()
        self.photo_cache = {}  # photo_id -> photo_object
    
    def load_gallery(self):
        """Load all photos into gallery"""
        # Get grouped photos
        photo_groups = self.adapter.get_photos_grouped_by_date()
        
        # Clear sample data
        gallery_view = self.gallery.gallery
        gallery_view.content_layout.clear()
        gallery_view.date_sections.clear()
        
        # Add each group
        for date_label, photos in photo_groups.items():
            self.add_photo_group(date_label, photos)
    
    def add_photo_group(self, date_label: str, photos: List[Dict]):
        """Add a group of photos to gallery under date section"""
        gallery_view = self.gallery.gallery
        
        # Add section
        gallery_view.add_photo_section(date_label, photos, len(photos))
        
        # Load thumbnails and connect signals
        cards = gallery_view.date_sections[date_label]
        for card, photo_data in zip(cards, photos):
            # Load thumbnail
            if photo_data.get('thumbnail'):
                pixmap = self.adapter.load_thumbnail(photo_data['thumbnail'])
                if pixmap:
                    card.set_pixmap(pixmap)
            
            # Connect signals
            card.clicked.connect(lambda c=card, p=photo_data: self.on_photo_clicked(p))
            card.favorited.connect(lambda c=card, p=photo_data: self.on_photo_favorited(p))
            card.deleted.connect(lambda c=card, p=photo_data: self.on_photo_deleted(p))
            card.info_clicked.connect(lambda c=card, p=photo_data: self.on_photo_info(p))
            
            # Store reference
            self.photo_cache[photo_data['id']] = photo_data
    
    def connect_sidebar(self):
        """Connect sidebar navigation to app sections"""
        sidebar = self.gallery.sidebar
        
        sidebar.nav_clicked.connect(self.on_sidebar_nav_clicked)
        sidebar.settings_clicked.connect(self.on_settings_clicked)
        sidebar.support_clicked.connect(self.on_support_clicked)
    
    def connect_search(self):
        """Connect search functionality"""
        top_nav = self.gallery.top_nav
        top_nav.search_clicked.connect(self.on_search)
    
    def on_sidebar_nav_clicked(self, item_name: str):
        """Handle sidebar navigation"""
        print(f"🎬 Navigating to: {item_name}")
        
        if item_name == "Library":
            self.load_gallery()
        elif item_name == "People":
            self.load_people_view()
        elif item_name == "Duplicates":
            self.load_duplicates_view()
        elif item_name == "Folders":
            self.load_folders_view()
        elif item_name == "Detail":
            self.load_detail_view()
        elif item_name == "Search":
            self.load_search_view()
    
    def on_search(self, query: str):
        """Handle search query"""
        print(f"🔍 Searching for: {query}")
        
        if not self.adapter.db:
            print("⚠️  Database not available")
            return
        
        try:
            # Query photos matching search
            # Adapt to your actual search method
            results = self.adapter.db.search_photos(query)
            
            # Load into gallery
            gallery_view = self.gallery.gallery
            gallery_view.content_layout.clear()
            gallery_view.date_sections.clear()
            
            # Add results as single section
            photo_data_list = []
            for photo in results:
                photo_data_list.append({
                    'id': photo.id,
                    'path': photo.path,
                    'exif': self.adapter._format_exif_data(photo),
                    'thumbnail': getattr(photo, 'thumbnail_path', None),
                })
            
            self.add_photo_group(f"Search Results: {query}", photo_data_list)
        except Exception as e:
            print(f"❌ Search error: {e}")
    
    def on_photo_clicked(self, photo_data: Dict):
        """Handle photo click"""
        print(f"📷 Photo clicked: {photo_data['id']}")
    
    def on_photo_favorited(self, photo_data: Dict):
        """Handle photo favorite"""
        print(f"❤️  Photo favorited: {photo_data['id']}")
        
        if self.adapter.db:
            try:
                # Update database
                self.adapter.db.set_favorite(photo_data['id'], True)
            except Exception as e:
                print(f"❌ Error favoriting: {e}")
    
    def on_photo_deleted(self, photo_data: Dict):
        """Handle photo delete"""
        print(f"🗑️  Photo deleted: {photo_data['id']}")
        
        if self.adapter.db:
            try:
                # Delete from database
                self.adapter.db.delete_photo(photo_data['id'])
                # Reload gallery
                self.load_gallery()
            except Exception as e:
                print(f"❌ Error deleting: {e}")
    
    def on_photo_info(self, photo_data: Dict):
        """Handle photo info request"""
        print(f"ℹ️  Photo info: {photo_data['id']}")
        # Could open details panel, modal, etc.
    
    def on_settings_clicked(self):
        """Handle settings click"""
        print("⚙️  Settings clicked")
    
    def on_support_clicked(self):
        """Handle support click"""
        print("❓ Support clicked")
    
    # View loading methods (to be implemented based on your app)
    def load_people_view(self):
        """Load people/faces section"""
        print("👥 Loading people view...")
    
    def load_duplicates_view(self):
        """Load duplicates section"""
        print("🔄 Loading duplicates view...")
    
    def load_folders_view(self):
        """Load folders section"""
        print("📁 Loading folders view...")
    
    def load_detail_view(self):
        """Load detail/fullscreen view"""
        print("🔍 Loading detail view...")
    
    def load_search_view(self):
        """Load search interface"""
        print("🔎 Loading search view...")


# Example usage function
def integrate_material_design(main_window_class):
    """
    Example: How to integrate Material Design 3 into existing main window
    
    Usage:
        from existing_main_window import MainWindowQt
        
        class NewMainWindow(MainWindowQt):
            def __init__(self):
                super().__init__()
                self.material_window = MaterialGalleryMainWindow()
                self.setup_material_ui()
            
            def setup_material_ui(self):
                controller = MaterialGalleryController(self.material_window)
                controller.connect_sidebar()
                controller.connect_search()
                controller.load_gallery()
                
                # Show Material window
                self.material_window.show()
    """
    pass


if __name__ == '__main__':
    # Test adapter
    print("Testing PhotoDataAdapter...\n")
    
    adapter = PhotoDataAdapter()
    groups = adapter.get_photos_grouped_by_date()
    
    print(f"Found {len(groups)} date groups:\n")
    for date_label, photos in groups.items():
        print(f"  {date_label}: {len(photos)} photos")
        if photos:
            print(f"    Example: {photos[0]['exif']}")
    
    print("\n✅ Adapter test complete")
